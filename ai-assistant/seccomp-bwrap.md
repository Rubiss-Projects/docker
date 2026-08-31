# AI Assistant Bubblewrap seccomp profile

`seccomp-bwrap.json` starts from Moby's official `v28.3.2`
`profiles/seccomp/default.json`. It retains the default-deny policy while allowing
the unprivileged namespace, mount, and `pivot_root` syscalls required by the
Codex shared-mode Bubblewrap sandbox.

The container still runs as a non-root user with all Linux capabilities dropped,
`no-new-privileges`, and a read-only root filesystem. Do not replace this profile
with `seccomp=unconfined` or add `CAP_SYS_ADMIN`.

When refreshing the profile for a newer Docker/Moby release, begin with that
release's official default profile, remove its conditional `clone`/`clone3`
rules, remove the listed Bubblewrap syscalls from the `CAP_SYS_ADMIN`-gated
rule, then add the final unconditional allow rule found in this profile. Verify
with both an unprivileged namespace test and a real Codex provider request.
