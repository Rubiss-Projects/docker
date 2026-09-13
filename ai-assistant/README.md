# AI Assistant

The service pins `v1.12.0` and runs in shared security mode. Schedules and run
history persist in the existing `ai-assistant-data` volume.

eBay item lookups use a fresh Chromium session to establish anonymous site
cookies and retrieve current auction facts. JavaScript, subresources, downloads,
and redirects are blocked. Chromium retains its sandbox; the seccomp profile
permits its user-namespace `chroot` while host capabilities remain dropped.

General research can use hosted search/article opening and `fetch_webpage`, which
supports RSS/Atom and large articles with continuation chunks. Sparse script pages
and HTTP 403 can use a general anonymous Chromium fallback; `mode=browser` selects
it explicitly. JavaScript and public GET/HEAD data requests render content through
a local proxy that validates and pins public DNS for every destination. Private
networks, saved accounts, POST requests, WebSockets and service workers remain
unavailable. Shared-mode shell networking remains restricted.

Both browser paths run in the `ai-assistant-browser` helper, capped at 1 GiB total
memory with no additional swap and two concurrent browsers. It has no bot secrets,
provider state or data volumes. Its control API is on a private network shared only
with the assistant; no port is published. A separate egress network permits public
website access. The helper refuses startup without its hard memory limit, and
`depends_on` waits for its health check before starting the assistant.

Individual source failures stay in schedule diagnostics. Discord receives a concise
sourced update with a short caveat when coverage is incomplete. Previous verified
summaries retain their timestamps and are supplied as stale historical context.

Schedules support optional `start_at` and `end_at` dates on creation and editing.
Use `YYYY-MM-DD HH:mm` in the schedule timezone or an ISO date-time with an
explicit offset. The start is inclusive and the end is exclusive; `none` clears
either date when editing. Command registration runs automatically on startup.

`DISCORD_SUPPRESS_EMBEDS=true` keeps the bot's text replies and scheduled messages
compact by hiding automatic link previews. Links remain clickable and uploaded
files are still delivered. Existing Discord messages are not changed. Set the
variable to `false` and recreate the container to restore previews on new replies.

Scheduling is enabled for the shared server `93904174068011008`. Its `@admin`
role (`93904984583704576`) can create message and AI schedules and manage
schedules in that server. Other Discord roles receive no scheduling rights.
The existing explicit bot administrator retains operator access and also holds
this role. Discord Administrator permission alone does not grant scheduling.

`rights.json` is mounted read-only outside provider workspaces. Its
`server-admin` preset grants message scheduling and schedule management; the
explicit `schedule.ai.create` capability also allows unattended AI runs using
the configured provider tools and integrations. These grants do not enable
workspace, MCP, or global bot administration.

Rights-file changes require a container restart. Current role membership and
channel permissions are checked before scheduled execution and delivery.
Default limits are a 15-minute minimum interval, 10 tasks per user, 50 per server,
and two concurrent runs. Use `/schedule` to create or manage tasks; enabling
the service does not create or send any scheduled messages.

Deployment allows an 11-minute shutdown grace period for active scheduled runs.
Keep this above `SCHEDULE_AI_TIMEOUT_MS` if that inference limit is increased, and
avoid short command-line stop timeout overrides during service updates.
After an unclean restart, the scheduler waits for the previous lease, retries
interrupted generation under the original occurrence, and resumes saved output
after its last acknowledged message. Generation starts afresh, so provider tool
effects can repeat. Ambiguous sends stay recorded for inspection without disabling
future occurrences. Schedules paused solely by the old restart recovery are
repaired automatically; explicit pauses, edits, permissions, and date bounds remain
respected.
