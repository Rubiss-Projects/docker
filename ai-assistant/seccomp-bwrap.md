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

## Native Linux AppArmor

Native Docker also enforces AppArmor. The seccomp syscall allowances do not
override its mount policy. `apparmor-bwrap` derives from Moby's container policy
at [6049e400](https://github.com/moby/profiles/blob/6049e40058759e8a1673ac1090ec6a7e36b9c9bd/apparmor/template.go),
permitting nested mounts and `pivot_root` for these three containers. It retains
the process, procfs, sysfs and network restrictions. Kernel capability checks
still deny mounting from the outer container namespace; all host capabilities
remain dropped.

Install the named profile and its loader before using `docker-compose.native.yml`:

```sh
sudo install -m 644 apparmor-bwrap /etc/apparmor.d/ai-assistant-bwrap
sudo install -m 644 native-ai-assistant-apparmor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now native-ai-assistant-apparmor.service
```

The loader runs before Docker on boot. Docker wants this unit but does not require
it: a profile-load failure holds the affected assistant containers without
preventing unrelated services from starting. Do not change the global
`docker-default` profile, disable AppArmor, grant `SYS_ADMIN`, or disable seccomp.

The native override adds only the named AppArmor setting. During migration, apply
that setting to the **accepted native compiled inputs**, preserving their volumes,
credentials, images, networks and resource limits. The Windows base Compose file
alone is not a replacement for those native inputs. Recreate only the three
assistant services after checking active work and retaining their current inputs.

Validate profile syntax with the native parser and verify Compose preserves the
existing security settings. Test the deployed Codex sandbox command with an
isolated, networkless helper using the same image, UID, seccomp and dropped
capabilities, plus an empty executable scratch home. The default profile should
reproduce the mount denial; the named profile must execute `/bin/true`. Verify
outer-namespace mounts remain denied. Then require a real provider response and
Discord conversation acceptance; a process-only healthcheck is insufficient.
