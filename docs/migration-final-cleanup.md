# Migration final cleanup tracker

Updated November 11, 2026. This tracks the owner's final migration requests.
Prepared code is not a completed deployment. Keep the existing progress page's
phase/step format; phase 11 remains current until acceptance is reconciled.

| Task | State | Completion evidence / remaining work |
| --- | --- | --- |
| Permanently skip NAS two-factor enrollment | Complete by owner decision | Recorded in the migration ledger and live progress page version 490; no NAS authentication settings changed. This is no longer a migration requirement. |
| Remove nine stopped migration containers | Complete | Removed exactly eight assistant restore-test containers and one temporary SNMP candidate. All 49 running container identities/start times were preserved; no images, volumes or bind data removed. |
| Share the Pi's Node Exporter Full dashboard with BEN-SERVER | Prepared; review/deployment pending | Add the pinned native exporter and scrape target; admit its exact wiring, start it, and verify real host CPU/memory/filesystem/NIC metrics in the existing dashboard. |
| Configure Linux/NAS/UPS Grafana alerts as code | Prepared; review/deployment pending | Thirteen focused Prometheus checks pass. Verify deployed rule evaluation and delivery through existing Grafana channels; no new direct NAS email or messaging destination. |
| Remove old Windows dashboards and alerts | Prepared; review/deployment pending | Remove obsolete dashboards, explicitly delete old rule UIDs and remove retired nightly Windows mute schedules. Preserve measurement history. |
| Remove the Caddy Overview dashboard and alerts | Prepared; review/deployment pending | Dashboard removal and explicit alert deletion entries are prepared. Verify they disappear from live Grafana. |
| Fix the Sunday Edge dashboard's missing data presentation | Prepared; review/deployment pending | Both workers are scraped and idle, polling empty queues. Completion/trial series have no samples in the last 24 hours. Clarify healthy idle versus missing collection; do not claim a completed workload. Verify the deployed panels and normal work separately. |
| Return UPS USB ownership from NAS to BEN-SERVER | Preparation in progress; physical move pending | Inspect existing protection, prepare the replacement local driver, NAS client protection and sole shutdown owner. Ask the owner to move the cable only when ready; verify online status afterward. Do not simulate a power outage. |
| Fix APC UPS dashboard and remove duplicate NAS UPS dashboard | Prepared consolidation; handoff verification pending | Preserve the APC dashboard URL and current readings. Verify charge/load/runtime/status after the cable move, remove obsolete handoff text and verify Homepage links. |
| Retire `nut-exporter` after UPS USB move | Pending replacement verification | Explicit owner request. Verify replacement APC metrics and power protection first; then remove the NAS-specific stack, scrape/configuration references and obsolete dashboard dependencies. |
| Remove retired `caddy/` folder | Pending reference audit | Direct Plex/Channels routes are accepted. Remove the retired proxy source and obsolete installers/deployment references. Original source disks and migration archives remain retained. |
| Audit and clean `scripts/` | In progress | Compare every candidate against CI, repository references and installed native services. Remove retired Windows/migration helpers and stale documentation/tests. Preserve active deployment, media mount/firewall, UPS, maintenance and application operations. |
| Commit all `CLAUDE.md` symlinks | Committed on feature branch; merge pending | All 45 existing controller links verified as targeting adjacent `AGENTS.md`; recorded with Git symlink mode 120000. If a retired directory is removed, its guidance link is removed with it. |
| Keep the progress page updated | Current through version 490 | Existing phases/steps and history preserved. Publish verified major state changes; do not change layout or add another progress system. |
| Finish representative normal-use observation | Pending | Monitor/analytics/research/checkpoint activity is accepted. Maintenance success and DFS completed work remain unobserved; idle health alone is not success. Preserve owner waivers/deferred tests. |
| Final reconciliation and owner review | Pending all required work | Verify runtime, alerts, dashboard queries, cleanup references, clean native checkout on main, and completed tracker. Then notify the owner that the full set is ready for review. |

## Review and deployment

All repository changes use reviewed pull requests and trusted main deployment.
The native deployment policy must admit new exporter wiring explicitly; do not
weaken existing stack admission. Preserve working services during cleanup.

The owner rejected additional recurring backups. Do not reintroduce them as a
completion gate. Existing Lazywarden/cloud backups, migration archives and old
source disks remain preserved. Torrent data/registration removal and source-disk
erasure remain outside this cleanup.
