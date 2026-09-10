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

CP-91 (2026-09-06): after PyPI 0.1.9 publication, recut with
`LIB_REF=v0.1.9` / `LIB_VERSION=0.1.9` as `f0e8343a-gsj0.1.9` and raise
both the host floor and its remedies to 0.1.9. A-28 applies because the
image carries the changed corpus-contract v3 and CP-90 estate payloads.
The MCP 0.5.0 and sandbox image payloads are unchanged.

The generated thirty now live in `<corpus>/decisions/`: the library
validates them, and `up` writes `decisions.lock.json` and verifies the
served drop. An external `<corpus>-decisions/` remains the fallback;
two populated drops refuse before estate work. The empty override for
an inside drop clears an earlier recorded external selection. The
bootstrap also creates its owned `work/runs/` before invoking the estate:
0.1.9 requires an existing runs root (CP-90 G-03), so this one-directory
addition is required by a fresh clone.

Published index `sha256:78d69417dc673125ae38f86387ee4e7d0cca308081e21ed97a95e56d1bddc968`:

- linux/amd64 `sha256:77c3c09f8b733ed23507b40d35219a0df249e35089f57b2686acd59325ab97da`
- linux/arm64 `sha256:fc075348cbdf994d44d028295a399596d27b4c377811b10e4a6a216ff1e21e8c`

Anonymous index/child reads and container checks passed on both platforms:
version 0.1.9, release source `4ac4e3cb32a9a1e18d52fc4e302ef5df5cb3ce04`,
exact packaged estate (`75dfa5ce…`) and pipeline (`a291ec56…`) bytes, and
PiHarness subclassing BaseHarness. Each platform also passed the actual
CLI.submit HTTP-byte proof with a mounted synthetic `.env`; its intentional
503 sink checks transport. The first build hit a PyPI download timeout;
one retry of the unchanged recipe completed and published both platforms.

A fresh public clone plus this patch used a scratch PyPI 0.1.9 venv outside
all repos. Generate/validate passed (30 decisions, 313 units; four rows),
`--force` reproduced the generated bytes, and five disposable routing cases
passed, including the inward migration command with spaces in its paths.
The existing reader suite passed 28/28. Live up took 42.248 s; the run
record selected `decisions_source: corpus`, and the lock and service agreed
on 30 files and hash `b414c670…`. Preflight took 9.213 s, row-2 submit
16.183 s, followed by read/export/empty quarantine and independent
validation with no findings. Checked down took 4.718 s; all five demo
containers and its network were removed, restoring the original inventory.

The episode used real CPU-only Qwen3-0.6B, 596,049,920 float32 parameters,
through the release proof's scratch PyTorch HTTP adapter. Preflight named
its missing tool parser and the API's sampling-attestation limit. Session
`sk-polar-f8d6b205-2645-4f68-92e9-f7dce552f843` was accepted: orchard@2,
one turn, zero actual tools, 23 trainable tokens, finish `stop`, no
deliverable. The model emitted a literal tool call as text. This proves
published-artifact boundary/provenance behavior; it does not establish
answer quality or functioning tool-call parsing. No GPU or H200 was used.


CP-93 (2026-09-07): the 0.1.10 wheel was published on PyPI at
2026-09-07T12:03:19.944176Z; demo edits began at 12:04:39Z. The host floor,
remedies and image now select 0.1.10. A-28 requires this recut because the
image carries CP-92's changed estate module: native-platform advice, split
pull refusals, partial-run status, seven-verb help and the four pins-page
warning URLs. The existing build recipe used public `LIB_REF=v0.1.10` and
PyPI `LIB_VERSION=0.1.10`, completed on its first attempt and published
`ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.10` for both platforms.

Published index `sha256:ed35bc967693e55fff4bc4e1918aa0e7341c7b21a3abb0de940b9961c2f445f6`:

- linux/amd64 `sha256:a089133953a7de712e387e8f8c12c17fa924a055f6bc96e8366c3915b781012d`
- linux/arm64 `sha256:f79c10546a7debef9f0e25ffb666b4eba4eb04d3096a38d9acd4a11c692ea503`

Both child manifests were read anonymously and both images were pulled
using an empty Docker authentication configuration. Both platform containers
report 0.1.10 and release source
`f2537e7f13aa474644f8241cb2e410c8d5cc6044`; their packaged estate and pipeline
hashes equal the independently installed public PyPI wheel. PiHarness
subclasses BaseHarness, the installed estate classifies the stranger's
whiteout and EOF errors correctly, and its sandbox cure names the native
platform. MCP 0.5.0 and the sandbox pin carry unchanged payloads.

F-86 closes with the bootstrap's split pull refusal and actual Alpine run
preflight; F-85 (c) closes with the help sentence naming the library flag's
owner and answers-file route. The library classifier was the existing
candidate; the small local helper retains its decisions so Docker checks
and a no-record down remain available before importing the library.
Fourteen pull cases agree with the installed library, three smoke paths
pass, a real unreachable-registry pull refuses with the retained download
advice, and the existing demo suite passes 28/28. Historical 0.1.9 corpus
contract claims remain true. The release's final acceptance gate uses a
fresh public clone of this commit, the published image and real CPU
inference; its accepted/read result belongs to the CP-93 release evidence.

CP-95 (2026-09-07): the 0.1.11 wheel was published on PyPI at
2026-09-07T19:13:39.392296Z; demo edits began at 19:18:26Z. The host floor,
remedies and image now select 0.1.11. A-28 requires this recut because the
image carries CP-94's changed estate module: `status` in three states
(ACTIVE via the run lock, incomplete corrected against the daemon,
complete), the sandbox image checked before any container is pulled or
created, the pull heartbeat, the pins line naming the approved sets left
empty, and help on the four `up` flags and `--runs-dir`. The existing build
recipe used public `LIB_REF=v0.1.11` and PyPI `LIB_VERSION=0.1.11`,
completed on its first attempt (288 s for the export and push) and
published `ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.11` for both
platforms.

Published index `sha256:40cb348459c7b5c727d28bbcfa7f965c6c07333222eb7b0532e06b9b61440b2e`:

- linux/amd64 `sha256:bc968fc0b109a86bbc1e8adff948d363898fb29a15ce255a7121a27e88d7cc43`
- linux/arm64 `sha256:43fe5efae4a55b70fc6f0f14b32b0e46b63e049c45712adfb1b12172f0a3256c`

Both child manifests were read anonymously and both images were pulled
using an empty Docker authentication configuration. Both platform containers
report 0.1.11 and release source
`3f7334b835b4514248c37b3954643fb4040974b8`; their packaged estate
(`e0102bd6…`) and pipeline (`a291ec56…`) hashes equal the independently
installed public PyPI wheel. PiHarness subclasses BaseHarness, and the
installed estate carries `lock_held`, `status_active`, `check_daemon`,
`host_rx_bytes`, the heartbeat in `image_pull` (60 s default) and
`empty_sets` in `pins_g1_check`. MCP 0.5.0 and the sandbox pin carry
unchanged payloads and were not recut.

F-87 and F-92 stay parked on `read.py`'s export format bump
(`gsj-demo-episode-export/3`), which this floor bump does not make; no row
is minted. The release's final acceptance gate uses a fresh clone of this
commit, the published image and the Mac's vllm-metal reference engine; its
accepted/read result belongs to the library's CP-95 release evidence.

CP-97 (2026-09-08): the 0.1.12 wheel was published on PyPI at
2026-09-08T15:19:35.214965Z; demo edits began at 2026-09-08T15:21:01Z (the stamp the patch
script wrote, not memory — the CP-95 record's minute was wrong). The host
floor, remedies and image now select 0.1.12. A-28 requires this recut
because the image carries CP-96's and CP-97's changed estate module: the
gateway-host probe by `docker exec` into the run's own retrieval container
(a probe that cannot run degrades with the cure named instead of aborting
one file short of `rollout.yaml`), every readiness wait on the process's
clock with the measured wait printed beside the budget, the collection
being built on the poll line, `verify`'s skips counted apart, the pull
heartbeat naming the layer phase, the storage-driver warning, and
`pins.skeleton.json` written beside `rollout.yaml` with the G6 tail and
end-of-turn id measured from the engine (library ADR-0042). The existing
build recipe used public `LIB_REF=v0.1.12` and PyPI `LIB_VERSION=0.1.12`
and published `ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.12` for both
platforms.

Published index `sha256:f9f2e2171d278690746b1c31878d7aa989d474fd4e1452c70653110a8a6e07c5`:

- linux/amd64 `sha256:bb73342ec082f02e90698636d17c6bbd4715ad970ed0418bd543570af66608a1`
- linux/arm64 `sha256:17390699984486b1093d769833169acba8eb0258be973fe5a7de2d77062c118a`

Both child manifests were read anonymously and both images were pulled
using an empty Docker authentication configuration. Both platform
containers report 0.1.12 and release source `3ac3fcdac1c31a518303f8384efb37fc76d26e0f`; their packaged
estate (`eed44912…`) and pipeline
(`a291ec56…`) hashes equal the
independently installed public PyPI wheel. PiHarness subclasses
BaseHarness, and the installed estate carries `probe_dial`,
`reap_container`, `measure_tail`, `pins_skeleton`, `refuse_skeleton_pins`,
`choose_end_of_turn`, `verify_headline` and `pull_phase_summary`, with the
skeleton's name and format, the reaper's and the sleep-skew bounds, the
`docker exec` dial, the monotonic wait and the `{{.Driver}}` read. MCP
0.5.0 and the sandbox pin carry unchanged payloads and were not recut. What
this demo does not take from 0.1.12: `read.py` is untouched, so F-87 and
F-92 stay parked on the export format bump — this sitting is a floor bump
and an image cut, not the one that opens `read.py`.

CP-100 (2026-09-09): the 0.1.13 wheel was published on PyPI at
2026-09-09T03:44:57.425296Z; demo edits began at 2026-09-09T03:49:08Z (the stamp the patch
script wrote, not memory). The host floor, remedies, `polar.Dockerfile`
default and both `docker run` recipes now select 0.1.13. A-28 requires this
recut because the image carries CP-98's and CP-99's changed estate module:
the reaper reads *removed* off the CLI's stdout so its 30 s bound engages on
a name the daemon has not created yet (CP-96 read an exit code that is 0 for
a missing name too), and the gateway-host probe's label now means what it
says — it binds a sentinel that answers a per-run nonce, dials every
candidate from a container on the run's network AND from this host, and
accepts only the candidate that returns the nonce on both legs, recording
per candidate what answered each leg in `run.json`; `host.docker.internal`
is appended rather than inserted first on nothing but resolving; a gateway
port this process cannot bind is reported UNMEASURED, naming the port and
`--gateway-host`, instead of measured against somebody else's listener; a
`docker exec` that could not start the interpreter is a failure (exit 127
with the message on stdout) rather than silence; six sites that wrote a
measurement's word over an inference say what they are; the storage-driver
warning carries a controlled pair's numbers instead of an inferred
`~13 GB per container`; and the pins skeleton says when the pins in force
already cover this corpus. **This cut also ends a mixed state**: this repo's
`bootstrap.py` took the reaper fix at CP-99 (`f917295`) while the pinned
image still carried 0.1.12's `estate.py`, so a demo-door reader would have
run this repo's new code over the library's old code inside one image.
The build recipe used public `LIB_REF=v0.1.13` and PyPI `LIB_VERSION=0.1.13`
and published `ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.13` for both
platforms.

Published index `sha256:f4a4cb2fcc5a1af185857b0bb3436420e3f551cedf499d14c228ec1358e2c4b7`:

- linux/amd64 `sha256:cac4322266147b1efef2364d2395fca935702b5be37644cf120f0bf7142cc55d`
- linux/arm64 `sha256:17abd169f7e18a2ac6f650c36b17467f3e91b084c2548cefb8f756a3986afa6e`

Both child manifests were read anonymously and both images were pulled using
an empty Docker authentication configuration. Both platform containers report
0.1.13 and release source `91f99fd7fba073557ed8234aecbbe2b5275ab83a`; their packaged
estate (`e3d3d8d6…`) and pipeline
(`a291ec56…`) hashes equal the independently installed
public PyPI wheel's, byte for byte. PiHarness subclasses BaseHarness, and the
installed estate carries `host_dial`, the nonce sentinel and its three
verdicts (`our sentinel` / `a foreign listener` / `nothing`), the appended
`host.docker.internal`, the EADDRINUSE UNMEASURED branch, the exec-127 guard
(`proc.returncode != 0 and not results`), the reused-measurement source
label, the re-measured `vfs` numbers with no `minutes per create` anywhere
and `~13 GB per container` only in the comment that retires it, the
conditional skeleton (`NOT NEEDED on this estate`, `NOT DERIVED YET in THIS
file`), no `#your-pins's derive_my_pins.py` anchor, and a `reap_container`
that reads *removed*. MCP 0.5.0 and the sandbox pin carry unchanged payloads
and were not recut. What this demo does not take from 0.1.13: `read.py` is
untouched, so F-87 and F-92 stay parked on the export format bump — this
sitting is a floor bump and an image cut, not the one that opens `read.py`.

CP-102 (2026-09-09): the 0.1.14 wheel was published on PyPI at
2026-09-09T15:26:57.092411Z; demo edits began at 2026-09-09T15:27:53Z (the stamp the patch
script wrote, not memory). The host floor, remedies, `polar.Dockerfile`
default and all three `docker run` recipes (step 1b's is CP-101's) now select
0.1.14. A-28 requires this recut because the image carries CP-101's changed
estate module: `up`'s `== run <name> ==` footer is conditional on the same
fact its pins line tests, so on an estate whose pins in force cover the
corpus — this demo's, once `bootstrap.py` has derived G1/G2 — the skeleton
row says `G1/G2 EMPTY in it — NOT NEEDED on this estate: /p/pins.gsj.json already carries them (#your-pins is for a corpus or model those pins do not cover)`
where 0.1.13 said `G1/G2 EMPTY until an inspected quarantined episode supplies them (#your-pins reads it)`
twenty lines under a pins line claiming the opposite (a round-six reader of
this README filed the pair). `gsj_rollout/` itself is byte-identical to
0.1.13's but for the version literal. The build recipe used public
`LIB_REF=v0.1.14` and PyPI `LIB_VERSION=0.1.14` and published
`ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.14` for both platforms.

Published index `sha256:9526f3f7090c4295752f36ff9766e1ae1358e02bfa38e553f8c507c26ea5e356`:

- linux/amd64 `sha256:a7a498ab1b44f667198a6062a767d8a539f994933c1af8d52b6e6b8fd146b987`
- linux/arm64 `sha256:dab8d7bf8aa667ded3ac9a05d39d7f065e198e05777b1929b20d795f9c2e5f43`

Both child manifests were read anonymously and both images were pulled using
an empty Docker authentication configuration. Both platform containers report
0.1.14 and release source `8fb720729fb59b555d093e4441e89e4eba4d0a61`; their packaged
estate (`c77d4f2f…`) and pipeline
(`a291ec56…`) hashes equal the independently installed
public PyPI wheel's, byte for byte. PiHarness subclasses BaseHarness; the
installed estate carries `skeleton_footer_row` with both branches (called in
the container with `covered=True` and `covered=False`, the two lines above),
and every CP-98/CP-99 seam CP-100 listed is still present (`host_dial`, the
nonce sentinel's three verdicts, the appended `host.docker.internal`, the
EADDRINUSE UNMEASURED branch, the exec-127 guard, the reused-measurement
label, the conditional skeleton, a `reap_container` that reads *removed*).
MCP 0.5.0 and the sandbox pin carry unchanged payloads and were not recut.
The fresh clone's episodes on this image: recorded in the library's printed CP-102 report — the clone is of this commit, run before the push. What this demo does not
take from 0.1.14: `read.py` is untouched, so F-87 and F-92 stay parked on the
export format bump — this sitting is a floor bump and an image cut, not the
one that opens `read.py`. And what the LIBRARY does not carry at 0.1.14, so
that this record does not imply it: `pi_harness.py`'s `| tee` still makes a
pipeline's exit the step's (library row 110 — routed around on the library's
pages with `-e TMPDIR`, which this demo's compose has always set, so door A
never meets it), and `cli.py`'s serve NOTE still names only a `<checkout>`.

CP-105 (2026-09-10): the 0.1.15 wheel was published on PyPI at 2026-09-10T18:37:45.254945Z; demo edits began at 2026-09-10T18:45:29Z (the stamp
the patch script checked, not memory). The host floor, remedies, `polar.Dockerfile` default and all four
`docker run` recipes now select 0.1.15. A-28 requires this recut because the image carries CP-104's changed
estate module — round seven's `up`: the rows `--row N` addresses listed under the taskbank line of the
`== run <name> ==` block (the block `bootstrap.py` echoes), the pull heartbeat's tally age, a cut transfer told
to re-run, and in the tool's own output this script mutes, the pullable image named and every printed command
carrying `--runs-dir`, `--corpus` and the interpreter. `gsj_rollout/` itself is byte-identical to 0.1.14's but
for the version literal. The build recipe used public `LIB_REF=v0.1.15` and PyPI `LIB_VERSION=0.1.15`.

**The order was the library's ADR-0043** — the image before the front door: the library's release commit stayed
off its `main` until this image answered an anonymous reader, so the README, the guide pages and the page `up`'s
NOTE links to never named a tag that did not resolve; the window left is the one bound to the wheel itself,
PyPI publication (2026-09-10T18:37:45.254945Z) to the first anonymous 200 on the tag (2026-09-10T18:53:08+00:00).

Published index `sha256:24cbe2eaf52b8f43b5617398a46bdb346dd2076c7e25c7fe76af25cc34d4c47d`:

- linux/amd64 `sha256:cb8786d4b6547f4ff50b4d13449a0f0d02d0fb74aeefae18126a4e2d19513bdf`
- linux/arm64 `sha256:786092901cecf3f7ef87d8f4c91219d7846797d64d8c6327f0d3b9f7befe3a2c`

Both child manifests were read anonymously and both images were pulled using an empty Docker authentication
configuration. Both platform containers report 0.1.15 and release source `d3f7120bd3bf40e7ba94d7bdcf00378a38ac07fd`; their
packaged estate (`e6598eeb…`) and pipeline
(`a291ec56…`) hashes equal the independently installed public PyPI
wheel's, byte for byte, and CP-104's seams are inside (`polar_image_ref()` names this tag, `bank_rows_lines`,
the `transfer` kind). MCP 0.5.0 and the sandbox pin carry unchanged payloads and were not recut.
The fresh clone's episodes on this image — step 1b's fence (row 3, t=4) and the t=2 triple, by the README's own
install line — are recorded in the library's printed CP-105 report: the clone is of this commit, run before the
push, so its session ids cannot be written into it. What this demo does not take from 0.1.15: `bootstrap.py`'s failed-derivation path
(F-122, F-123) and its own heartbeat (F-128) wait on the next `bootstrap.py` lift, and F-87, F-92 and F-120 on
the `read.py` export bump; and what the LIBRARY does not carry at 0.1.15: row 110's `| tee` status, row 108's
`cli.py` NOTE, and row 112's residue.
