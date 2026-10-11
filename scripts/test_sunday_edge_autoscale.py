import datetime as dt
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("autoscale", Path(__file__).with_name("sunday-edge-autoscale.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NOW = 1_800_000_000_000


def state(desired=6, low_since=None, low_desired=2):
    return dict(protocolVersion=1, desiredSlots=desired, maxSlots=8, updatedAt=NOW - 30_000,
                wakeToken="previous", lowSince=low_since, lowDesired=low_desired)


def demand(desired=2):
    return dict(protocolVersion=1, workerVersion="current", desiredSlots=desired, pending=1,
                sampledAt=dt.datetime.fromtimestamp(NOW / 1000, dt.timezone.utc).isoformat())


def resources(cpu=30, memory_gib=8):
    return dict(sampledAt=NOW, cpuCount=16, cpuPercent=cpu,
                availableMemoryBytes=memory_gib * 1024 ** 3)


class AutoscaleTests(unittest.TestCase):
    def test_resource_budget_reserves_new_quotas_on_both_systems(self):
        limits = (2, 1024 ** 3, NOW)
        self.assertEqual(m.resource_budget(resources(), resources(), *limits), 2)
        for constrained in (resources(cpu=80), resources(memory_gib=2)):
            self.assertEqual(m.resource_budget(constrained, resources(), *limits), 0)
            self.assertEqual(m.resource_budget(resources(), constrained, *limits), 0)
        self.assertEqual(m.resource_budget(resources(cpu=70), resources(memory_gib=3), *limits), 1)

    def test_missing_stale_or_invalid_resources_never_allow_additions(self):
        bad = [None, {}, {**resources(), "sampledAt": NOW - 60_001},
               {**resources(), "cpuPercent": float("nan")}, {**resources(), "cpuPercent": 101},
               {**resources(), "cpuCount": True}, {**resources(), "availableMemoryBytes": -1}]
        for sample in bad:
            with self.subTest(sample=sample), self.assertRaises((ValueError, KeyError)):
                m.resource_budget(sample, resources(), 2, 1024 ** 3, NOW)
        with patch.object(m, "command", side_effect=RuntimeError("unavailable")):
            self.assertEqual(m.admission(resources()), {"additionalSlots": 0, "reason": "RESOURCE_SAMPLE_UNAVAILABLE"})

    def test_up_immediately_down_only_after_sustained_low_demand(self):
        self.assertEqual(m.next_state(state(2), demand(6), NOW)["desiredSlots"], 6)
        self.assertEqual(m.next_state(state(), demand(), NOW)["desiredSlots"], 6)
        self.assertEqual(m.next_state(state(low_since=NOW - 300_000), demand(), NOW)["desiredSlots"], 2)
        self.assertEqual(m.next_state(state(low_since=NOW - 300_000), demand(6), NOW)["lowSince"], None)

    def test_missing_samples_cannot_prove_a_quiet_period(self):
        old = {**state(low_since=NOW - 600_000), "updatedAt": NOW - 100_000}
        self.assertEqual(m.next_state(old, demand(), NOW)["desiredSlots"], 6)
        with self.assertRaises(ValueError):
            m.next_state(state(), demand(9), NOW)

    def test_changed_downscale_recommendation_needs_its_own_quiet_period(self):
        for before, after in [(5, 2), (2, 5)]:
            with self.subTest(before=before, after=after):
                previous = state(low_since=NOW - 300_000, low_desired=before)
                result = m.next_state(previous, demand(after), NOW)
                self.assertEqual(result["desiredSlots"], 6)
                self.assertEqual(result["lowSince"], NOW)
                self.assertEqual(result["lowDesired"], after)
                # Successful samples keep the same recommendation stable for five minutes.
                for elapsed in range(30_000, 300_001, 30_000):
                    result = m.next_state(result, demand(after), NOW + elapsed)
                self.assertEqual(result["desiredSlots"], after)

    def test_baseline_reset_repairs_slot_identity_without_removing_busy_workers(self):
        for drained in (False, True):
            with self.subTest(drained=drained):
                two = dict(id="second", slot=2, version="current", idle=True, drained=False)
                five = dict(id="first", slot=5, version="current", idle=drained, drained=drained)
                one = dict(id="new", slot=1, version="current", idle=True, drained=False)
                final = [one, two] if drained else [one, two, five]
                with patch.object(m, "snapshot", side_effect=[[two, five], final]), \
                     patch.object(m, "control_write") as write, patch.object(m, "report") as report, \
                     patch.object(m, "lifecycle") as lifecycle:
                    result = m.reset_control()
                self.assertEqual(write.call_args.args[0]["desiredSlots"], 2)
                self.assertEqual(result["onlineSlots"], [1, 2] if drained else [1, 2, 5])
                self.assertEqual(result["drainingSlots"], [] if drained else [5])
                self.assertEqual(report.call_args.args[1], final)
                calls = [call.args[0] for call in lifecycle.call_args_list]
                self.assertEqual(len(calls), 2 if drained else 1)
                if drained:
                    self.assertEqual(calls[0], ["docker", "rm", "--force", "first"])
                self.assertIn("dfs=2" if drained else "dfs=3", calls[-1])

    def reconcile(self, workers, desired=2, error=None, dry=False):
        with patch.object(m, "snapshot", return_value=workers), \
             patch.object(m, "app_request", return_value=demand(desired), side_effect=error), \
             patch.object(m, "control_read", return_value=state(low_since=NOW - 300_000)), \
             patch.object(m, "admission", return_value={"additionalSlots": 2}), \
             patch.object(m, "control_write") as write, patch.object(m, "report"), \
             patch.object(m, "lifecycle") as lifecycle, patch.object(m.time, "time", return_value=NOW / 1000):
            if error:
                with self.assertRaises(RuntimeError):
                    m.reconcile(dry)
            else:
                m.reconcile(dry)
            return write.call_args_list, lifecycle.call_args_list

    def test_only_acknowledged_excess_slots_can_be_removed(self):
        workers = [dict(id=f"container{slot}", slot=slot, version="current", idle=True, drained=False) for slot in range(1, 7)]
        workers[3]["drained"] = True
        workers[4].update(drained=True, idle=False)
        writes, calls = self.reconcile(workers)
        self.assertEqual(len(writes), 1)
        self.assertEqual(calls[0].args[0], ["docker", "rm", "--force", "container4"])
        self.assertEqual(len(calls), 1)

    def test_api_failures_and_dry_runs_do_not_change_capacity(self):
        worker = dict(id="one", slot=1, version="current", idle=True, drained=False)
        self.assertEqual(self.reconcile([worker], error=RuntimeError("unavailable")), ([], []))
        self.assertEqual(self.reconcile([worker], dry=True), ([], []))

    def test_returning_demand_fills_missing_slot_while_excess_workers_drain(self):
        workers = [dict(id=f"container{slot}", slot=slot, version="current", idle=False, drained=False)
                   for slot in (1, 2, 3, 5, 6)]
        final = workers + [dict(id="container7", slot=4, version="current", idle=True, drained=False)]
        with patch.object(m, "snapshot", side_effect=[workers, final]), \
             patch.object(m, "app_request", return_value=demand(4)), \
             patch.object(m, "control_read", return_value=state(2)), \
             patch.object(m, "admission", return_value={"additionalSlots": 2}), \
             patch.object(m, "control_write"), patch.object(m, "report") as report, \
             patch.object(m, "lifecycle") as lifecycle, patch.object(m.time, "time", return_value=NOW / 1000):
            result = m.reconcile()
        self.assertEqual(lifecycle.call_args.args[0], ["docker", "compose", "up", "-d", "--no-deps",
            "--no-recreate", "--pull", "never", "--scale", "dfs=6", "--wait", "--wait-timeout", "90", "dfs"])
        self.assertEqual(result["onlineSlots"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(result["drainingSlots"], [5, 6])
        self.assertEqual(report.call_args.args[1], final)

    def test_removed_slots_are_absent_from_execution_result(self):
        workers = [dict(id=f"container{slot}", slot=slot, version="current", idle=True, drained=slot > 2)
                   for slot in range(1, 7)]
        with patch.object(m, "snapshot", return_value=workers), \
             patch.object(m, "app_request", return_value=demand()), \
             patch.object(m, "control_read", return_value=state(low_since=NOW - 300_000)), \
             patch.object(m, "admission", return_value={"additionalSlots": 2}), \
             patch.object(m, "control_write"), patch.object(m, "report"), \
             patch.object(m, "lifecycle"), patch.object(m.time, "time", return_value=NOW / 1000):
            result = m.reconcile()
        self.assertEqual(result["onlineSlots"], [1, 2])
        self.assertEqual(result["drainingSlots"], [])

    def test_blocked_resources_preserve_leases_and_prevent_missing_slot_replacement(self):
        workers = [dict(id=f"container{slot}", slot=slot, version="current", idle=False, drained=False)
                   for slot in (1, 2, 3, 5, 6)]
        with patch.object(m, "snapshot", return_value=workers), \
             patch.object(m, "app_request", return_value=demand(8)), \
             patch.object(m, "control_read", return_value=state(6)), \
             patch.object(m, "admission", return_value={"additionalSlots": 0}), \
             patch.object(m, "control_write"), patch.object(m, "report"), \
             patch.object(m, "lifecycle") as lifecycle, patch.object(m.time, "time", return_value=NOW / 1000):
            result = m.reconcile()
        self.assertEqual(result["desiredSlots"], 6)
        self.assertEqual(result["onlineSlots"], [1, 2, 3, 5, 6])
        lifecycle.assert_not_called()

    def test_guard_steps_to_eight_and_budgets_missing_slots_before_growth(self):
        for current, slots, desired in [(2, (1, 2), 4), (6, tuple(range(1, 7)), 8), (6, (1, 2, 3, 5, 6), 7)]:
            workers = [dict(id=str(slot), slot=slot, version="current", idle=False, drained=False) for slot in slots]
            with self.subTest(current=current, slots=slots), \
                 patch.object(m, "snapshot", return_value=workers), \
                 patch.object(m, "app_request", return_value=demand(8)), \
                 patch.object(m, "control_read", return_value=state(current)), \
                 patch.object(m, "admission", return_value={"additionalSlots": 2}), \
                 patch.object(m, "apply_state", return_value=workers) as apply, \
                 patch.object(m.time, "time", return_value=NOW / 1000):
                result = m.reconcile()
            self.assertEqual(result["desiredSlots"], desired)
            self.assertEqual(apply.call_args.args[2], 2)

    def test_partial_replacement_obeys_admission_and_physical_cap(self):
        workers = [dict(id=str(slot), slot=slot, version="current", idle=False, drained=False)
                   for slot in (1, 2, 5, 6, 7, 8)]
        with patch.object(m, "control_write"), patch.object(m, "report"), \
             patch.object(m, "snapshot", return_value=workers), patch.object(m, "lifecycle") as lifecycle:
            m.apply_state(state(4), workers, 1)
        self.assertIn("dfs=7", lifecycle.call_args.args[0])
        with patch.object(m, "control_write"), patch.object(m, "report"), \
             patch.object(m, "snapshot", return_value=workers), patch.object(m, "lifecycle") as lifecycle:
            m.apply_state(state(4), workers, 4)
        self.assertIn("dfs=8", lifecycle.call_args.args[0])

    def test_slow_drains_cannot_use_expired_resource_admission(self):
        workers = [dict(id=str(slot), slot=slot, version="current", idle=True, drained=slot == 8)
                   for slot in (1, 2, 8)]
        with patch.object(m, "control_write"), patch.object(m, "report"), \
             patch.object(m.time, "time", return_value=NOW / 1000), patch.object(m, "lifecycle") as lifecycle:
            m.apply_state(state(4), workers, 2, NOW - 1)
        self.assertEqual([call.args[0] for call in lifecycle.call_args_list], [["docker", "rm", "--force", "8"]])

    def test_growth_rechecks_deadline_after_slow_maintenance_setup(self):
        docker_command = ["docker", "compose", "up", "-d", "--scale", "dfs=8"]
        for maintenance_ms in (1_000, 61_000):
            with self.subTest(maintenance_ms=maintenance_ms), patch.object(m, "command") as command:
                m.lifecycle(docker_command, admission_valid_until=NOW + 60_000)
                wrapper = command.call_args.args[0]
                guarded = wrapper[wrapper.index("--") + 1:]
                self.assertEqual(guarded[:2], [m.sys.executable, "-c"])
                with patch.object(m.sys, "argv", ["-c", *guarded[3:]]), \
                     patch.object(m.time, "time", return_value=(NOW + maintenance_ms) / 1000), \
                     patch.object(m.subprocess, "call", return_value=0) as docker, patch("builtins.print"):
                    if maintenance_ms < 60_000:
                        with self.assertRaises(SystemExit) as result:
                            exec(guarded[2], {})
                        self.assertEqual(result.exception.code, 0)
                        docker.assert_called_once_with(docker_command)
                    else:
                        exec(guarded[2], {})
                        docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
