# Migration final cleanup tracker

Updated November 11, 2026. This tracks the owner's final migration requests.
Prepared code is not a completed deployment. Keep the existing progress page's
phase/step format; phase 11 remains current until acceptance is reconciled.

| Task | State | Completion evidence / remaining work |
| --- | --- | --- |
| Permanently skip NAS two-factor enrollment | Complete by owner decision | Recorded in the migration ledger and live progress page version 490; no NAS authentication settings changed. This is no longer a migration requirement. |
| Remove nine stopped migration containers | Complete | Removed exactly eight assistant restore-test containers and one temporary SNMP candidate. All 49 running container identities/start times were preserved; no images, volumes or bind data removed. |
| Clean leftover Docker containers on BEN-PC | Pending inventory | Inventory running/stopped containers, Compose ownership and attached storage on the gaming PC. Identify obsolete migration/temporary copies and any retained active workload, then remove verified leftovers without deleting live data, volumes, images or torrent registrations. |
| Share the Pi's Node Exporter Full dashboard with BEN-SERVER | Complete | The same provisioned Node Exporter Full dashboard is used for both hosts. Native CPU, memory, root filesystem and physical NIC samples are verified, including after the real UPS event; all 15 Prometheus targets are Up. |
| Complete monitoring deployment after runtime checks | Complete | PRs 570 and 579 are merged; deployment 42950755758 succeeded. The corrected full affected-range deployment completed. Only its admitted SNMP exporter dependency was recreated; the other 49 running identities/start times were preserved. Both Linux checkouts were clean on main. |
| Configure Linux/NAS/UPS Grafana alerts as code | Complete; update UPS source during cable handoff | All 18 expected rules evaluated healthy/inactive after the full reload. Owner-approved single Discord - Lawson test succeeded at 03:37 UTC on November 11. Existing channels remain the only human alert route. |
| Remove old Windows dashboards and alerts | Complete | Live Grafana confirms both Windows dashboards and the retired Windows/native duplicate host rules are absent. Old nightly Windows mute schedules are deleted; measurement history is retained. |
| Remove the Caddy Overview dashboard and alerts | Complete | The live Caddy dashboard UID returns 404 and all retired Caddy alert UIDs are absent after reviewed provisioning. |
| Fix the Sunday Edge dashboard's missing data presentation | Prepared; review/deployment pending | Both workers are scraped and idle, polling empty queues. Completion/trial series have no samples in the last 24 hours. Clarify healthy idle versus missing collection; do not claim a completed workload. Verify the deployed panels and normal work separately. |
| Return UPS USB ownership from NAS to BEN-SERVER | Preparation in progress; physical move pending | Inspect existing protection, prepare the replacement local driver, NAS client protection and sole shutdown owner. Ask the owner to move the cable only when ready; verify online status afterward. Do not simulate a power outage. |
| Repair automatic application recovery after a real UPS shutdown | Fix prepared; review and installation pending | The November 11 incident confirmed an orderly UPS shutdown and the unless-stopped recovery gap. All 50 exact prior container identities were restored via native admission with zero recreation. A previous-boot manifest and one-time, power/admission-gated restore unit are prepared; nine focused tests, validation of all 50 live identities and real systemd-sandbox admission of all 39 released stacks pass. Existing power decisions remain unchanged. |
| Fix APC UPS dashboard and remove duplicate NAS UPS dashboard | Prepared consolidation; handoff verification pending | Preserve the APC dashboard URL and current readings. Verify charge/load/runtime/status after the cable move, remove obsolete handoff text and verify Homepage links. |
| Retire `nut-exporter` after UPS USB move | Pending replacement verification | Explicit owner request. Verify replacement APC metrics and power protection first; then remove the NAS-specific stack, scrape/configuration references and obsolete dashboard dependencies. |
| Remove retired `caddy/` folder | Pending reference audit | Direct Plex/Channels routes are accepted. Remove the retired proxy source and obsolete installers/deployment references. Original source disks and migration archives remain retained. |
| Audit and clean `scripts/` | In progress | Compare every candidate against CI, repository references and installed native services. Remove retired Windows/migration helpers and stale documentation/tests. Preserve active deployment, media mount/firewall, UPS, maintenance and application operations. |
| Clean leftover migration work on the NAS and reclaim space for Media | Pending inventory and final retention decision | Inventory temporary/staging files, migration recovery archives, snapshots, Recovery quota/reservations and actual physical pool use. Identify what remains necessary through final acceptance, then present exact deletion/resize scope and real capacity benefit before destructive work. Remove approved obsolete material and reduce or retire Recovery as appropriate; prioritize usable Media capacity. Do not count a thin quota reduction as physically reclaimed bytes. Preserve application/media/torrent data and existing Lazywarden. |
| Clean the Media `data/` root | In progress | Keep media and active download directories. Removed the empty `housekeeping-staging/` and `recovery-staging/` directories without deleting files. `queue-repair-archive-20261003/`, `recovery-backups/` and `recovery-hardlinks/` contain older media/recovery material; inventory sizes, hardlinks and active torrent/application references before removing or relocating them. They predate the native migration. |
| Add NAS favorite in this Windows File Explorer | Complete | NAS root pinned to Home / Quick access; Media and Recovery read access verified. Windows credentials saved in the current user's protected Credential Manager. |
| Commit all `CLAUDE.md` symlinks | Complete on remote main and both Linux checkouts | All 45 links verified as targeting adjacent `AGENTS.md`, recorded with Git symlink mode 120000, and materialized as real links on BEN-SERVER and the Pi. If a retired directory is removed, its guidance link is removed with it. Controller checkout/worktree cleanup remains part of the final repository audit. |
| Reconcile draft PRs and leave the repository clean | In progress | Obsolete draft PR 528 is closed; its clean worktree and local/remote branch are removed. Tracearr draft PR 529 remains pending local staff-login dependency verification; its compatibility patch is not active on the running container. Complete remaining migration branch/worktree/artifact cleanup and leave the canonical deployment checkout clean on main. |
| Keep the progress page updated | Current through version 491; next acceptance update pending | Version 491 is live with the existing layout, schema and history preserved. Publish the verified monitoring completion and real UPS incident/recovery with the next major checkpoint. |
| Finish representative normal-use observation | Pending | Monitor/analytics/research/checkpoint activity is accepted. Maintenance success and DFS completed work remain unobserved; idle health alone is not success. Preserve owner waivers/deferred tests. |
| Final reconciliation and owner review | Pending all required work | Verify runtime, alerts, dashboard queries, cleanup references, clean native checkout on main, and completed tracker. Then notify the owner that the full set is ready for review. |

## Review and deployment

All repository changes use reviewed pull requests and trusted main deployment.
The native deployment policy must admit new exporter wiring explicitly; do not
weaken existing stack admission. Preserve working services during cleanup.

The owner rejected additional recurring backups. Do not reintroduce them as a
completion gate. Existing Lazywarden/cloud backups remain preserved. Retain
migration archives until the new NAS cleanup inventory and explicit retention
decision establish the exact removal scope; original source disks stay intact.
Torrent data/registration removal and source-disk erasure remain outside this
cleanup.
