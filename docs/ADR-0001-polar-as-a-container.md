# ADR-0001 — Polar runs as a published container

Status: accepted (CP-34 of the library's evaluation). External ADR — this
repo's decision, recorded here; the library's charter references it.

## Context

The estate has three legs. Two were always containers with compose files
(Forgejo; the MCP service). The third — Polar's rollout server and
gateway, plus the library's receiver — ran from `vendor/polar/.venv`
inside a checkout of the library repo: exactly the seam the library's
CP-32 stranger test measured a consumer tripping over (F-45: the serve
printout's Polar commands point at a venv a pip-install consumer does not
have). A demo whose promise is "one bootstrap command" cannot end with
"now clone a second repo and build a venv".

Options considered: **(a)** a container carrying Polar and the library's
wheel, composed beside the other two; **(b)** the bootstrap clones the
library repo and builds the venv — cheaper to write, but it reintroduces
the two-repo dance that publishing to PyPI was meant to end; **(c)** a
documented manual step — honest, and leaves the hard part exactly where
CP-32 found it.

## Decision

Option (a), taken on measurement, not on preference. `estate/polar.Dockerfile`
builds `ghcr.io/mhganainy/gsj-polar:<polar-sha8>-gsj<lib-version>`; the
demo's compose runs it three times (rollout server, gateway, receiver),
one process per service. What was measured on the built image
(2026-08-18, Docker 28.5.1/macOS + the estate box):

- **Polar installs from public artifacts alone.** `vendor/polar/` in the
  public library repo is the pinned tree (`POLAR_SHA` f0e8343a) with
  patches P1–P3 already applied; `pip install` of that directory into
  `python:3.12-slim` resolves (fastapi 0.141.1, uvicorn 0.52.3, pydantic
  2.13.4 at build time — Polar's bounds are floors, so the build records
  what it resolved). No history, no submodules, no venv.
- **The wheel gets in from PyPI, pinned** (`gsj-harness-rollout-server==0.1.2`,
  the release cut for this CP; `==0.1.3` from library CP-61, `==0.1.7` from
  library CP-81 — the image tag tracks the release, the library's A-28),
  into the SAME interpreter. `import_path`
  then resolves trivially: `polar.agent.factory` imports
  `gsj_rollout.pi_harness:PiHarness` from shared site-packages —
  measured `issubclass(PiHarness, BaseHarness) == True` with no
  `PYTHONPATH` at all. A-14's "Polar's venv hosts gsj_rollout" realized
  as one container environment.
- **Both processes boot and find each other by DNS.** With
  `polar.rollout.host: 0.0.0.0` and `public_url: http://polar-rollout:8080`
  in the generated config, the gateway registers over the compose network:
  rollout `/health` → `{"status":"ok","nodes":1}`. (Measured the failure
  first: without `public_url`, Polar defaults the registration target from
  `host:port` and the gateway dials `127.0.0.1:8080` inside its own
  container — the generated config exists to make that mistake
  unmakeable.)
- **Episode containers start as siblings** through the mounted
  `/var/run/docker.sock` (measured: `docker run` from inside the image).
  Polar's `DockerRuntime` shells out to `docker create/start/exec/cp/rm`
  and moves file content by `docker cp` — no host-path-coupled content
  mounts for our harness. The one bind-mount it does make (the per-session
  dir) is handled by path identity: the gateway service mounts the host
  sessions dir at its own host path and points `TMPDIR` there, so the
  daemon-side mount resolves to the same bytes — and session logs are
  host-visible for free.
- **`GSJ_PINS_PATH` reaches both law-6 legs** as a compose environment
  value (`/estate/pins.gsj.json`, the bootstrap-derived estate pins) on
  the gateway and the receiver — and the printed submit command carries
  the same variable for the trainer leg.

## Consequence

"One command" is true: the stranger's host needs Docker and the pip-installed
library, nothing else of ours by path. The costs are owned: the image's
Polar dependency versions are resolved at image build (floors, not a
lockfile) — pinned in practice by pinning the *image*; the maintainer
rebuilds and republishes on every library release (`LIB_REF`/`LIB_VERSION`
build args); and the sandbox image is pulled at bootstrap, not at first
episode, so a broken registry path surfaces before an episode is spent.
Option (b) remains the documented fallback for a host that cannot run
registries at all — the F-45 printout in the library names it.


CP-85 (2026-09-05): after PyPI 0.1.8 publication, recut with
`LIB_REF=v0.1.8` / `LIB_VERSION=0.1.8` as `f0e8343a-gsj0.1.8`, and move the
host floor to 0.1.8. The core submit implementation is unchanged, but the
image carries the wheel’s changed estate/pipeline payload too. A-28’s
release duty requires both platforms to carry that release. The read-only
`.env` mount and automatic submit fallback remain the same contract.

Published index `sha256:30e9d940bc55f815bb291d78ceba5cbf062616d6b4b29501dd7d0073c7de98a8`:
- linux/amd64 `sha256:b6a74e33a4566d9d0efd3bc36ec7cd2dad6c22df369b2be6150b4425d719a82a`
- linux/arm64 `sha256:7f5898b7eee1bc24b6990203534c2d227e0527e6bbe31d5fca6756580f18c902`

Anonymous index/child retrieval and container import checks passed for both
platforms, including version 0.1.8, the exact phase-2 estate payload and
PiHarness’s BaseHarness relationship. The fresh-clone arm64 run used the
published image and a fresh PyPI host install: up 42.682 s, preflight passed,
row-2 submit accepted in 8.955 s, read/export and empty quarantine, down
3.550 s. The read-only `.env` mount supplied submit’s named token without
exporting it. Session `sk-polar-7fb2e7b0-6d5a-4cf3-8c83-b11ac0438fdb` had
two turns, one case search, 170 trainable tokens, no deliverable; independent
validation found no provenance violations. This does not establish task quality.
