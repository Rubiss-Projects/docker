# QNAP SNMP collector

Read-only NAS telemetry for the [QNAP dashboard](https://grafana.benlawson.dev/d/qnap-nas).
Prometheus polls `192.168.50.91` every 60 seconds through this container on
`proxynet`. No host port is published. The HTTP health check and Kuma monitor
check the exporter; the dashboard's collection indicator checks the NAS scrape.
Neither starts disk tests or controls NAS power.

## Credentials and NAS settings

QuTS hero h6.0.2.3591 build 20260819 uses SNMPv3 `authPriv`, HMAC-SHA
authentication and its fixed CBC-DES privacy setting. AES is not offered in
this firmware's SNMP form. Use the dedicated SNMP identity, no trap destinations,
and no WAN forwarding for UDP 161. This form has no per-source access control.

`config/auth.yml` expands `QNAP_SNMP_USERNAME`, `QNAP_SNMP_AUTH_PASSWORD` and
`QNAP_SNMP_PRIV_PASSWORD` from `.env.secret`. That file must remain git-crypt
encrypted in Git. Missing credentials fail exporter startup. The optional
Compose overlay supports public CI validation; it is required at runtime.
Do not add stock `public_v2` credentials or put passwords in scrape URLs.

## Generated modules

`config/snmp.yml` was generated from this NAS's downloaded **NAS.mib** on
2026-11-10, using official snmp_exporter **v0.31.0**, commit
`181b59e7748732516e761b27c308794f2470d4bc`, matching the deployed exporter.
The original sensor/interface modules are unchanged. This is the QuTS hero `QTS-MIB`
under enterprise **55062**, not the older QTS EX metrics. Change `generator.yml`
and regenerate; do not hand-edit the runtime file.

Download the NAS MIB from **Control Panel → Network & File Services → SNMP**.
Place it in a temporary `mibs/QTS-MIB` file alongside the minimal dependencies
below. The standard MIBs come from [Net-SNMP v5.9](https://github.com/net-snmp/net-snmp/tree/v5.9/mibs),
with [IANA interface types](https://www.iana.org/assignments/ianaiftype-mib/ianaiftype-mib).
The vendor MIB is downloaded locally rather than redistributed in this repository.

| File | SHA-256 used at activation |
| --- | --- |
| QTS-MIB | `0cf58b39ad5c17737a2237f7e9d0a5359d8063d50a72acadd8e74ebe807a8fe9` |
| IANA-IFTYPE-MIB.txt | `c676192edc492eb068c3aa2755991c34c061e103ddd12e6653795b3813b82a59` |
| IF-MIB | `a41d2d0414bd6e1b3249257d0d035ea11554624c525b830f6910195b72b0c297` |
| SNMPv2-CONF | `b3e90ba682e10c76f6de90e65a0013143f0ec531b0ed546b2b8aa5ad5c0001eb` |
| SNMPv2-MIB | `b4f8ef130f580b86d2b6bc890564e46100785f589431df76954e878a7b166e11` |
| SNMPv2-SMI | `ece2355fc8b6140af702f86d77bd3f7398d80375fc6278c3e30ff3a31b53e0b7` |
| SNMPv2-TC | `c1379575e6a0ad25b2d7da68294153c1fd79750827376f2aa6323d072d73f0b8` |

Build the generator from the exact release using its
[Dockerfile and instructions](https://github.com/prometheus/snmp_exporter/tree/v0.31.0/generator).
With this repository's generator input copied into the temporary working directory:

```sh
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges -v "$PWD:/opt" nas-migration-snmp-generator:v0.31.0 --fail-on-parse-errors generate
```

Generation must complete without parse errors or missing objects. Review the
output before replacing `config/snmp.yml`. The current output has 19 metric
definitions; SHA-256 is
`d15d80eef06e282a59d63421b91ae602e0ae0fb6de5c5ca16561e2cc5b6d37b4`.
Keep runtime and generator versions aligned when updating either.

## Verified readings and interpretation

First successful poll on 2026-10-17 matched Hardware Information: system 34°C,
SATA Bays 1/2 at 41°C/39°C, and Bay 3 temperature unsupported (`-1` in SNMP).
CPU temperature and fan RPM vary between polls and matched the native ranges.
`systemCPU_Usage` is numeric percent. `systemTotalMem` reported 8,105,119,744
bytes, agreeing with Resource Monitor's 7.55 GiB usable; available memory gave
approximately 16.7% used, matching its utilization display. The generator
overrides QNAP's Counter64 memory declarations to **gauges**.

Temperature charts exclude values `<= 0`; this also removes the two unused
`HERO` enclosure rows reporting zero. Missing readings remain gaps. Drive status
is displayed as the exact NAS-reported text, not a qualification result.
`diskStatus` is an information metric: its sample value `1` is not a health code.

| Physical bay | Native SNMP diskID | Serial verified against NAS inventory |
| --- | --- | --- |
| 1 | 3 | ZR90KK6H |
| 2 | 4 | ZR90KJ5M |
| 3 | 5 | K3S069D7 |
| 4 | 6 | K3S04HPB |

SNMP diskID includes M.2 slots; diskIndex is a table index. Neither is used
directly as a SATA bay. Prometheus labels the verified ID **and** serial pairs
above. A moved or replacement drive remains `bay="unmapped"` until its identity
is verified and the mapping updated. The original faulty Bay 3 drive
`ZR90KN6W` was replaced; its failure history remains in the migration evidence.
The November 10 native health inventory and live SNMP samples agree on all four
current ID/serial pairs and temperatures (42/42/41/40°C at the comparison).

The active NIC is **eth2 / ifIndex 4**, reporting 10,000 Mbit/s and operational
state 1. Throughput uses IF-MIB Counter64 octets × 8, not packet counters.
Grafana's minimum query step is one minute so rate windows cover at least four
polls. Network charts need two successful samples before a rate appears.

The `qnap_storage` module collects pool capacity/free/status and shared-folder
capacity/free/status. Byte-valued capacity levels override the MIB's Counter64
wire type to gauges. A read-only candidate poll on November 10 matched a fresh
native API capture: pool capacity 40,475,771,797,504 bytes and unallocated space
13,795,461,814,240 bytes, with state 0 (Ready). This is **pool allocation**,
including reservations and thick allocations, not file payload usage.

Media's quota is 30,500,000,000,000 bytes and Recovery's is 4,398,046,511,104
bytes. Their available-space samples differed from the later native capture by
only 288 bytes. These are shared-folder quota values: do not sum them to infer
physical pool utilization. Public's dynamic capacity is intentionally excluded
from the quota charts. The dashboard keeps pool and shared-folder figures apart,
gates them on successful collection and leaves failed/missing scrapes unavailable.
`sharedFolderStatus` is an information metric; its sample value 1 is not a health
code. Pool status retains the raw integer. Only 0 is labelled Ready, as verified
against this NAS. The MIB describes conflicting QTS and QuTS hero enumerations;
unverified nonzero states remain numeric in a neutral color until reconciled
with the native API. Do not infer a named operation or healthy state from them.

Erase/scan percentages stay on the separate
[migration progress page](https://nas-linux-migration-field-guide-2026.rubiss89.chatgpt.site/progress).
The existing Prometheus retention is 15 days; earlier private scan evidence is
not backfilled into this time series database.

## Deployment and validation

Use the repository PR/review workflow. The deploy helper orders this exporter
before Prometheus and waits for its HTTP health check. It deliberately does not
restart Prometheus merely because the exporter changed.
After deploying Prometheus it validates the mounted configuration, sends HUP
inside the container, and confirms a new successful reload through the runtime
API, so config-only changes take effect. After deploying this
exporter it invokes SWAG's Kuma sync script without restarting SWAG.

The deployment runner does not start previously stopped/new stacks. For first
activation, explicitly bootstrap this service from WSL under the existing
`/tmp/docker-compose-ops-deploy.lock.d` flock; do not enable the global
start-stopped flag. A validated candidate can run from an isolated worktree
before the reviewed merge; normal deployment then recreates it using the
canonical checkout. Leave `/mnt/e/Docker` clean on `main`.

```sh
docker compose --env-file .env --env-file .env.secret config --quiet
docker compose --env-file .env --env-file .env.secret up -d --wait
docker exec snmp-exporter wget -q -T 45 -O - 'http://127.0.0.1:9116/snmp?target=192.168.50.91&auth=qnap_v3&module=qnap,qnap_interfaces'
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

After deployment, verify `up{job="qnap-snmp",instance="qnap-nas"} == 1`,
the serial/bay mapping and every Grafana query against fresh samples. Confirm
invalid disk temperatures stay absent. A future replacement must stay unmapped
until its native ID and serial have been reconciled; never reuse a bay label by
table position alone. Compare the storage figures with the native API after
firmware or quota changes. Run `python3 snmp-exporter/test_storage_queries.py`
to evaluate the dashboard's actual queries against the accepted sample and prove
that failed or missing collection produces no values.
No user-data storage or active test is changed by these checks.

To roll back collection, remove the scrape job through a PR, then stop only
this exporter. Do not interrupt the NAS or its qualification jobs.
