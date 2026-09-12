# AI Assistant

The service pins `v1.9.0` and runs in shared security mode. Schedules and run
history persist in the existing `ai-assistant-data` volume.

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
