# Staff login compatibility

Tracearr 3.1.3 can retain a mixed-case local owner/admin username or email after Plex synchronization. Better Auth lowercases a password sign-in identifier, while the deployed adapter compares the saved value exactly. A valid saved password then fails because the account lookup finds no row.

`patch-login-case.mjs` resolves a unique owner/admin identifier case-insensitively, then passes its saved spelling through the existing adapter and role restriction. It preserves other lookup conditions and account data. Zero or multiple staff matches fail closed. Member identities cannot supply the lookup value. Email matching changes only for password sign-in; OAuth email matching is unchanged. Password verification, rate limiting, session hooks and logout remain upstream behavior.

The patch accepts only the reviewed 3.1.3 authentication-module SHA-256 and its exact patched output. Image updates must review this compatibility step; an unknown or modified module refuses startup. Remove the patch when an upstream fix has been verified against retained mixed-case identifiers and staff/member collisions.

The default `docker-compose.yml` is unchanged. `compose.login-compat.yml` describes the opt-in command and mount delta. It retains the image entrypoint, existing Seerr patch, loopback port, images, resources, environment, networks and state volumes. Its extra read-only bind refuses missing host files.

On BEN-SERVER, first admit this exact command and read-only source bind in the root-controlled native policy. Run the existing native adapter's admission before activation. Recreate only the existing Tracearr app with the adapter's `--no-deps --pull never` operation; keep the database, Redis, images and accepted volumes unchanged. Never run the standalone override as a main-server deployment or start a second application owner.

Verify one sign-in by the existing owner email using the saved local credential, authenticated owner identity, sign-out and rejection of the old cookie. Do not reset credentials or normalize stored account fields to make a test pass. Preserve Plex login and session history. If startup or acceptance fails, restore the previously admitted command/bind and recreate only the app against the same current state.

Run `test-login-case.mjs` in the pinned image with `/compat` bound read-only to this directory and `--network none --entrypoint node`. It verifies the actual transformed wrapper with recording adapters and real Drizzle SQL construction, without starting the application or accessing a database. Separate private migration evidence covers nine actual HTTP login, identity, logout and role/ambiguity cases in an isolated restored database; sensitive account data and credentials are not repository fixtures. The fixture result does not establish live ingress, polling, playback, cold Redis recovery or a fresh final-state handoff.
