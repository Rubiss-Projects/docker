import tempfile
import unittest
import sys
import time
from pathlib import Path
from unittest.mock import patch

from snapshot import bounded_command, collect, read, snapshot, trace_io


class SnapshotTest(unittest.TestCase):
    @patch('snapshot.snapshot', return_value={'pid': 232})
    @patch('snapshot.time.sleep')
    @patch('snapshot.trace_io')
    def test_default_collection_never_attaches(self, trace, sleep, sample):
        result = collect()
        trace.assert_not_called()
        self.assertEqual(len(result['samples']), 3)
        self.assertEqual(result['linuxTrace']['status'], 'disabled')

    def test_command_deadline_and_forced_stop(self):
        started = time.monotonic()
        result = bounded_command([sys.executable, '-c',
            'import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(20)'], 0.2)
        self.assertEqual(result['stopReason'], 'duration_limit')
        self.assertIsNotNone(result['exitCode'])
        self.assertLess(time.monotonic() - started, 2)

    def test_output_bound(self):
        result = bounded_command([sys.executable, '-c', 'print("x" * 100000)'], 2, 1024)
        self.assertEqual(result['stopReason'], 'output_limit')
        self.assertEqual(len(result['text']), 1024)

    @patch('snapshot.shutil.which', return_value='/usr/bin/strace')
    @patch('snapshot.read', return_value='transmission-da\n')
    @patch('snapshot.attached_threads', return_value=[232])
    @patch('snapshot.bounded_command')
    def test_existing_tracer_not_disturbed(self, command, attached, read_proc, which):
        self.assertEqual(trace_io(232)['status'], 'unavailable')
        command.assert_not_called()

    @patch('snapshot.shutil.which', return_value='/usr/bin/strace')
    @patch('snapshot.read', return_value='transmission-da\n')
    @patch('snapshot.attached_threads', return_value=[])
    @patch('snapshot.bounded_command', return_value={
        'exitCode': 0, 'text': 'pread64(0x1, 0x2, 0x3, 0x4) = 0x3\n > Operation not permitted'})
    def test_unwind_failure_not_claimed_as_stack(self, command, attached, read_proc, which):
        self.assertEqual(trace_io(232, stacks=True)['status'], 'unavailable')
        arguments = command.call_args.args[0]
        self.assertIn('raw=all', arguments)
        self.assertNotIn('--kill-on-exit', arguments)

    def test_missing_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(snapshot(Path(directory))["error"], "daemon_not_found")

    def test_bounded_read_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample"
            path.write_text("x" * 4096)
            self.assertEqual(len(read(path)), 2048)
            self.assertEqual(read(path / "missing"), {"error": "NotADirectoryError"})

    def test_descriptor_paths_without_reading_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / "123"
            task = proc / "task" / "124"
            task.mkdir(parents=True)
            (proc / "comm").write_text("transmission-da\n")
            (task / "wchan").write_text("p9_client_rpc")
            (task / "syscall").write_text("74 0x9 0 0 0 0 0")
            (proc / "fd").mkdir()
            (proc / "fd" / "9").symlink_to("/does-not-exist/media.mkv")
            result = snapshot(Path(directory))
            self.assertEqual(result["threads"][0]["syscall"].split()[0], "74")
            self.assertEqual(result["fds"]["9"], "/does-not-exist/media.mkv")
            self.assertEqual(result["threads"][0]["stack"], {"error": "FileNotFoundError"})


if __name__ == "__main__":
    unittest.main()
