# Opt-in login compatibility preparation

Tracearr 3.1.3 can retain a mixed-case local owner/admin username or email after Plex synchronization. Better Auth lowercases a password sign-in identifier, while the deployed adapter compares the saved value exactly. A valid saved password then fails because the account lookup finds no row.

`patch-login-case.mjs` resolves a unique owner/admin identifier case-insensitively, then passes its saved spelling through the existing adapter and role restriction. It preserves other lookup conditions and account data. Zero or multiple staff matches fail closed. Member identities cannot supply the lookup value. Email matching changes only for password sign-in; OAuth email matching is unchanged. Password verification, rate limiting, session hooks and logout remain upstream behavior.

The patch accepts only the reviewed 3.1.3 authentication-module SHA-256 and its exact patched output. Image updates must review this compatibility step; an unknown or modified module refuses startup. Remove the patch when an upstream fix has been verified against retained mixed-case identifiers and staff/member collisions.

The default `docker-compose.yml` is unchanged. `compose.login-compat.yml` is an **uninstalled opt-in candidate**, to be selected explicitly after review and the migration's runtime and single-writer release gates. It retains the image entrypoint, existing Seerr patch, loopback port, images, resources, environment, networks and state volumes. Its extra read-only bind refuses missing host files. Do not enable it on the Windows production stack merely because validation passes.

For an already admitted isolated deployment, merge the base file and this override explicitly with `-f docker-compose.yml -f compose.login-compat.yml`. This file alone does not prepare state or authorize starting a second production identity.

Run `test-login-case.mjs` in the pinned image with `/compat` bound read-only to this directory and `--network none --entrypoint node`. It verifies the actual transformed wrapper with recording adapters and real Drizzle SQL construction, without starting the application or accessing a database. Separate private migration evidence covers nine actual HTTP login, identity, logout and role/ambiguity cases in an isolated restored database; sensitive account data and credentials are not repository fixtures. The fixture result does not establish live ingress, polling, playback, cold Redis recovery or a fresh final-state handoff.
