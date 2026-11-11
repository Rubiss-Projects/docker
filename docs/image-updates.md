# Image updates

## Policy

Use `publisher/image:tag@sha256:digest` for every Compose image and Dockerfile base.
The tag tells Dependabot which release or supported channel to follow; the digest
fixes the exact content Docker runs. A digest prevents a changed tag from silently
changing a deployment. It does not certify that a newly published image is safe.

Prefer comparable stable version tags. For LinuxServer use its three-part numeric
aliases, such as `sonarr:4.0.20`, not `version-4.0.20.3014`. Dependabot's stable-tag
heuristic compares against `latest`; four-part aliases can be misclassified as
prereleases, while tags containing build hashes or distro revisions may only get
digest refreshes for the old release.

Use publisher-supported channels where numeric tags do not work reliably:
`uptime-kuma:2`, `timescaledb-ha:pg18`, PostgreSQL `14`, Redis `8-alpine`, and the
existing Java-specific Minecraft channels. Always include the digest. Database
major and Java runtime changes need deliberate compatibility/migration review.
Timescale extension migrations are performed by the deployment helper after a
database backup; updating its container alone leaves installed SQL extensions old.
The workflow loads that helper from the trusted deployment commit before the
helper updates the canonical checkout, including on its first deployment.

Dependabot checks run each Saturday, staggered from 06:00 through 10:10
America/Chicago. Both Dockerfiles have `docker` entries; Compose-only checks do not
inspect their `FROM` lines. Private Sunday Edge images retain the configured GHCR
registry credentials. n8n uses the publisher's direct Docker Hub repository after
repeated HTTP 429 failures through docker.n8n.io. Staggering reduces request bursts
but cannot eliminate registry quotas; investigate failed or missing weekly jobs.

PR validation runs `python3 scripts/check_image_pins.py` to enforce pins, stable
LinuxServer aliases, and weekly coverage. Existing Dependabot queue rules still
require passing PR checks and the previous deployment, and hold major version
changes for review. Weekly checks do not guarantee that every PR deploys that day.
The PR workflow only classifies eligibility. The main-push/hourly queue enables
one update at a time, skips updates with failed checks, and leaves those PRs open
for repair. Pending checks keep their queue position. Digest-only updates may
appear as unchanged version tags or as backtick-wrapped hexadecimal hashes.
New app releases after a check, publisher image build delays, and beta release
notifications can legitimately appear before the next stable image update.

Game server downloads and Homebridge plugins installed inside containers are also
separate from the container image; image digest protection does not cover them.

n8n version changes also require its publisher GitHub release to be non-draft
and non-prerelease. Numeric beta tags must not bypass the stable-release policy.
