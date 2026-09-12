# AI Assistant sandbox seccomp profile

`seccomp-bwrap.json` starts from Moby's official `v28.3.2`
`profiles/seccomp/default.json`. It retains the default-deny policy while allowing
the unprivileged namespace, mount, and `pivot_root` syscalls required by the
Codex shared-mode Bubblewrap sandbox.

It also permits `chroot` for Chromium's unprivileged user namespace sandbox.
The syscall is not gated on the container's `CAP_SYS_CHROOT`, since the container
has no host capabilities. The kernel still enforces the capability requirement
in the calling process's user namespace.

The container still runs as a non-root user with all Linux capabilities dropped,
`no-new-privileges`, and a read-only root filesystem. Do not replace this profile
with `seccomp=unconfined` or add `CAP_SYS_ADMIN`.

When refreshing the profile for a newer Docker/Moby release, begin with that
release's official default profile, remove its conditional `clone`/`clone3`
rules, remove the listed Bubblewrap syscalls from the `CAP_SYS_ADMIN`-gated
rule, then add the final unconditional allow rule found in this profile. Preserve
the Chromium exception by removing the `includes.caps: ["CAP_SYS_CHROOT"]`
condition from the dedicated `chroot` allow entry. Keep its action as
`SCMP_ACT_ALLOW`; do not grant a host capability to satisfy the old condition.

Verify the refreshed profile with an unprivileged namespace test, a real Codex
provider request, and the Chromium smoke test using the service's Compose
configuration:

```sh
docker compose run --rm --no-deps --entrypoint node ai-assistant /app/dist/scripts/smoke-ebay-browser.js
```

Run that command from this directory after the v1.11.1-or-newer image has been
published. It uses the configured seccomp profile, non-root user, dropped
capabilities, `no-new-privileges`, read-only filesystem, and tmpfs settings. The
test must launch Chromium with its sandbox enabled, confirm that page scripts
are disabled, and verify request/response interception. Then verify a live eBay
item through `fetch_webpage` before considering the refreshed profile ready.
