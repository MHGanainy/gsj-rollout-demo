# gsj-rollout-demo

From **your documents** to **a running rollout estate** — one command.
From an episode to **a trajectory you can actually read** — one more.

This is the demo for [gsj-harness-rollout-server](https://github.com/MHGanainy/gsj-harness-rollout-server):
the rollout server that takes a task `(case, timestep, prompt)`, runs an
agent in an isolated sandbox with temporally-scoped retrieval, and emits a
training-ready trajectory. You bring three things — documents in the
contract's shape, a `config.yaml` naming your inference endpoint, and that
endpoint itself; one command derives everything else and stands the estate
up, and one submit later you are reading what the agent did in it. Since
library CP-81 the worked example also brings **thirty decisions** — court
decisions written to bear on its two cases, in the XML the library's
decisions surface parses — so the agent's second retrieval tool returns
precedent worth citing, and the transcript shows whether it cited:

```
 you bring                     one command                     what you get
 ─────────                     ───────────                     ────────────
 your corpus   ─┐
 (documents)    │  ./bootstrap.py up     docker run … submit   ./read.py show
 config.yaml   ─┼─────────────────────▶ ─────────────────────▶ ────────────────
 (three values) │  a running estate:     one episode:          the trajectory:
 your inference─┘  validated corpus,     a sandboxed agent     every turn, every
 endpoint          5 containers,         works the task        tool call, the
                   derived pins          against your          cutoff checked —
                                         endpoint              ready to train on
```

(The [`-examples` repo](https://github.com/MHGanainy/gsj-harness-rollout-server-examples)
is the other half: it shows a **trainer** how to train against an estate
that already exists. *This* repo is for the person who has to get the
estate — and wants to see what the agent did in it.)

**What an accepted episode is — and is not.** "Training-ready" above names the
trajectory's shape: token ids, a loss mask and the captured logprobs, the form
a trainer consumes. What acceptance proves is provenance: the cutoff held (the
checkout and every retrieved page at or before the timestep), the pinned
system prompt, skill cards, tool roster and thinking-mode tail were checked,
and the trajectory was reconstructed by the builder the library measured
faithful against its golden reference. It does not grade the episode —
acceptance checks provenance, not task success (below); it does not record the
sampling policy — pi sends no sampling parameters, so whatever your endpoint
defaults to *is* the policy, and no OpenAI-compatible API reports it; and it
carries no reward — every callback's `reward` is `null`. What the library has
and has not trained is on
[its front page](https://github.com/MHGanainy/gsj-harness-rollout-server#readme).

## Quickstart

Everything below this block is the measured detail behind it. **Two
preconditions**, both worth checking before you start:

- `docker run --rm alpine true` **exits 0**. A daemon that answers `docker info`
  and even pulls images can still be unable to *start* one — the pull is not the
  check, the run is (two stranger runs died there).
- Python >= 3.12, git, and Docker's `docker compose` plugin (Compose V2, the Go
  plugin — not the legacy `docker-compose` v1).

```bash
mkdir -p gsj-demo && cd gsj-demo                 # the venv lands here, the clone beside it
python3 -m venv .venv && . .venv/bin/activate    # PEP 668 systems refuse a bare pip install
pip install --timeout 120 --retries 5 'gsj-harness-rollout-server>=0.1.17' pyarrow
git clone https://github.com/MHGanainy/gsj-rollout-demo && cd gsj-rollout-demo
# a new shell later? `. ../.venv/bin/activate` here first — the scripts need the venv's PyYAML

./synthetic/make_corpus.py                       # the worked corpus + thirty decisions
cp config.yaml.example config.yaml               # fill in three values (corpus, base_url, model)
./bootstrap.py validate && ./bootstrap.py up     # the estate
```

Then submit one episode and read it — the walkthrough's
[step 1](#walkthrough-an-episode-submitted-and-read) prints the command with your
own paths in it. Budget for the **image pulls**, which dominate a cold first run
on a slow pipe: four images, **~1.8 GB compressed on the wire**, of which the
retrieval service alone is ~1.35 GB, and ~4–6 GB on disk after extraction (the
disk figure depends on the daemon's image store — the bullet below).

## What to expect, measured

The numbers below are measured, not estimated — most on one from-nothing
run (library CP-36, the *stranger run*: a fresh clone, a fresh venv,
anonymous image pulls, an Apple Silicon Mac, no prior state) against the
reference stack — vLLM serving `Qwen/Qwen3-0.6B` host-local, the
two-case synthetic corpus; where a number comes from another checkpoint,
it says so. The CP-nn stamps name checkpoints of the library's measured
record. The public checkpoint account is in the library's
[tracked charter §7](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/CHARTER.md#7-gap-register).
Full reports and ADR files are private working-tree records under the
CP-48 decision; a public clone carries the charter, code and test evidence.
Wrong expectations make a working system read as broken — the trainer
repo learned that as
[its finding F-18](https://github.com/MHGanainy/gsj-harness-rollout-server-examples/blob/main/FINDINGS.md)
— so: what this costs, and what is normal.

- **Install**: clone 1.7 s; venv + `pip install` from PyPI **≈ 40 s
  cold** (measured at library CP-81; two strangers on 2026-09-06 (UTC)
  measured 36.6 s and 63.3 s on slow pipes) — 5.5 s at library CP-61 on a
  fast pipe (cache state not recorded). **On a slow pipe the install line
  fails outright** before anything else has run: pip's default 15 s read
  timeout dies mid-way through pyarrow's 46.8 MB wheel with a thirty-line
  `ReadTimeoutError` traceback and no retry hint (round four, 2026-09-07:
  two strangers, at 6.7 MB and 15.7 MB in). **It does not always say
  "timeout"**: when the 15 s expires during the *resolver's* metadata
  fetch instead of a wheel download, pip reports `Could not find a
  version that satisfies the requirement pydantic … (from versions:
  none)` — a network fault that names a dependency and reads like a
  broken package (round five: two more strangers lost their first
  install, one to each signature; cost of the second, one wrong
  diagnosis). The cure is pip's own, for both:
  `pip install --timeout 120 --retries 5 'gsj-harness-rollout-server>=0.1.17' pyarrow`
  — the same command with two flags; an unchanged retry also recovers when
  the drop was transient. `docker pull` has three bullets of this guidance
  below; the install needed one. You bring Docker with the `docker compose`
  plugin (Compose V2 or later), Python >= 3.12 and git — the exact
  prerequisite line is in "Run it" below.
- **Disk, and the wire — two different numbers.** **~1.8 GB compressed on
  the wire** — the one that governs the clock — measured from the four images'
  registry manifests at library CP-104 (1.79 GB for `arm64`, 1.84 GB for
  `amd64`), and the retrieval service is **1.34–1.38 GB of it, about three
  quarters in one image**. On disk, after extraction, the same images are
  **~4.05 GB** as a Linux daemon's classic `overlay2` store accounts them
  (`docker system df` read 4.061 GB for two round-seven strangers, the
  retrieval service 2.65 GB of it) and **~6 GB** in Docker Desktop's containerd
  image store (`docker info` names its driver `overlayfs`; library CP-61
  measured the daemon growing 5.4 GB for four images listed at 6.1 GB, and
  this workstation lists them at 6.8 GB at CP-104). This bullet called 4.05 GB
  "compressed on the wire" and 2.65 GB "44% of the total" through library
  CP-103 — a disk figure under the wire's label, and a share of neither total
  (2.65 of 4.05 is 65%; 44% is 2.65 of Desktop's 6.1); two round-seven readers
  caught it, one from the manifests and one by dividing. `docker system df` is
  the accounting check once the pulls are done — it counts an image only when
  it is complete, which is why it is no progress meter (the pull bullets
  below). A round-six stranger extrapolated "on the order of a day" from the
  disk figure before correcting itself; plan a link by the wire figure.
  `work/` after one episode: 10–14 MB. **On a copy-on-create driver
  (`vfs`) the figure is a different order of magnitude**: every container is
  a full copy of its image, not a layer over it. Round five measured it
  against an `overlay2` control — same door, same corpus, same row, the
  driver the only difference: **31 G of data root against 8.4 G** for the
  same 4.061 GB of images (3.7×, and 7.6× the images' own size here; the
  other door's `vfs` container measured 7.5×, 27 G for 3.588 GB), and the
  episode's **sandbox init taking 19.4 s against 1.1 s** — the 731 MB
  harness image being copied is the only plausible tenant of that delta. On a *loaded* host it is worse than a ratio: round four
  blew Polar's 600 s sandbox-create budget here twice and measured ~60 GB
  of root-filesystem growth for what the daemon accounted as 3.7 GB of
  images. (Round four's "~13 GB per sandbox container" was inferred from
  that one host and is retired — the ratios above are what two controlled
  pairs actually measured.) **`up` prints this only when it finds a
  copy-on-create driver**: since library CP-96 it reads the driver from its
  first `docker info` and warns, priced to the pair above since library CP-99 —
  so on `overlay2`, the good case, you correctly see **no driver line at all**
  and there is nothing to do. (Round six: four strangers, all `overlay2`, zero
  warnings; one of them went looking for the line this README had promised
  unconditionally and filed its absence.) Check yours with `docker info
  --format '{{.Driver}}'`; this README's `vfs` cure below is priced accordingly.
- **`up`, cold on an empty docker host: ~4 min on the measured run, ~2.5 min where every image pulls natively; 80 s from a fresh clone where the images are already present** (measured at library CP-81: clone 0.1 s, venv + `pip install` from PyPI — the cold install figure quoted under **Install** above — `make_corpus.py` 0.05 s, `validate` 1.4 s, `up` 38 s — the estate, the corpus, and the thirty decisions embedded) — one uninterrupted
  from-nothing run (library CP-61, Apple Silicon, fast pipe): ~90 s of
  image pulls, then the library's bring-up (Forgejo, the owner and its
  tokens, the scaffold, the retrieval service's first embed — 28 s
  natively — the taskbank, the round-trip verify — 126 s of it on that run,
  with Forgejo's first start, the scaffold and the verify running under
  emulation because its image had to be loaded out-of-band as an amd64
  copy (F-78); 42 s of it with a native Forgejo), then the Polar leg. Warm
  re-run: **~13 s**; after `down`: ~35 s.
- **One episode, end to end: ~20–40 s** against a host-local 0.6B engine
  (measured at CP-36: 22.5 s thinking-off, 38.6 s thinking-on; at CP-61,
  on the estate the library's bring-up stood up: 21 s thinking-off). The
  ceiling, stated: a session is cut off by the library at 900 s (its
  `timeout_seconds` default) — a small model that loops on a tool error
  burns all of it (measured at CP-61: the 0.6B model's skill-card row ran
  463 turns of `read /workspace` → `EISDIR` before being stopped; the
  receiver quarantined it as `ADM1:status_not_completed`), and that is the
  floor model, not the estate.
- **Platform fact 1 — Apple Silicon / ARM works, said out loud.** All
  four images run natively: `gsj-mcp-service` publishes
  `linux/amd64` + `linux/arm64` under one tag since library CP-61's 0.4.0
  (this checkout pins `0.5.1`, with behavior-preserving Starlette response
  helpers and the decisions surface from `0.5.0`; historically, the amd64
  predecessor ran ~2 min under emulation for the first embed and the native
  first embed measured 22 s), `gsj-pi-harness:pi0.83.0-3` since
  library CP-64 (republished as a two-platform index under the same
  pinned tag, the amd64 child byte-unchanged), and `gsj-polar` always
  did. History, for anyone reading an old trace: before library CP-64 an
  ARM docker refused the sandbox's amd64-only manifest rather than
  emulating (measured at library CP-36, F-54), so the bootstrap pulled it
  `--platform linux/amd64` explicitly and the per-episode sandbox ran
  under emulation — episode speed unaffected even then, since the agent
  talks to your endpoint over HTTP. That cure retired with the arc.
- **Platform fact 2 — a non-Qwen endpoint works; the serve argv is yours
  to write only when you serve the model.** `up` derives the model-bound
  pins from your endpoint's own template render, automatically (G6's tail
  and the end-of-turn id; G1/G2 from your corpus); what nobody can derive
  over an API is the serve command — the tool-call parser and the sampling
  pins are flags only the server's operator can set. Two cases, and the
  README used to name only the first: **you serve the model** — pin the
  sampling defaults there (`--generation-config`) and treat the argv as
  part of the estate's provenance; **you were handed a URL** by a platform
  team (the normal case, and round three's four strangers' case) — you
  cannot pin anything, the policy is *unknown*, and `up` records it as
  such in `work/estate/pins.gsj.json` (`provenance.engine.sampling_policy`,
  `coverage.sampling_policy`) — see "The borrowed endpoint" and "What an
  acceptance covers" below. [docs/MODEL-SURFACE.md](docs/MODEL-SURFACE.md)
  walks the whole surface; the first non-Qwen episode
  (Llama-3.1-8B-Instruct, CP-38) derived at `up`, preflighted all-ok, and
  was accepted; round three (2026-09-07) added `qwen3.6-27b` on a borrowed
  endpoint, twice, both accepted.
- **Normal, not broken.** An empty quarantine is normal — the reference
  stack measured 72/72 accepted at library CP-32, this demo's smoke 1/1.
  A small model hitting the 8,192-token generation cap is labelled, not
  silent: `submit` counts it on the `length-terminated: N/M` line it prints
  after every run (`0/1` is a clean run — the N is the signal) and `show` marks
  the truncation twice — such an episode *qualified*, and whether to
  train on it is the trainer's call. Degenerate episodes are the 0.6B
  floor model being itself, honestly rendered: an early smoke episode
  read `AGENTS.md` seventy times and wrote nothing, and the transcript
  collapses the repetition and says NO deliverable was written.
  Acceptance checks **provenance, not task success**. Two lines you would
  only ever have seen on a stale library 0.1.3 install (cured at the
  library's CP-62, shipped in 0.1.4 — this demo's floor moved 0.1.4 → 0.1.6 → 0.1.7 → 0.1.8 (library CP-85) → 0.1.9 (library CP-91) → 0.1.10 (library CP-93) → 0.1.11 (library CP-95) → 0.1.12 (library CP-97) → 0.1.13 (library CP-100) → 0.1.14 (library CP-102) → 0.1.15 (library CP-105) → 0.1.16 (library CP-106) → 0.1.17 (estate/lock-reader refactoring)): a false `pins —
  WARNING: 1/1 skill card(s) are not in the packaged approved set (G1)`
  (0.1.3 checked the library's *packaged* pins, not the ones this script
  derives for your corpus; library wishlist 51 (c)) and `ports — 8080 is
  busy on this host; using 8081` (0.1.3 scanned host ports for a Polar
  that runs in containers here). On 0.1.4 the G1 check reads the named
  set and `polar_leg: container` scans nothing — neither line prints.
- **Historical: the bring-up refusing at the Forgejo image** — with
  library 0.1.3 (the floor before 0.1.4), `docker compose up forgejo`
  failed with `manifests/sha256:… not found`: codeberg's registry dropped
  the platform manifests of `forgejo:16.0.2` — the tag 0.1.3's bring-up
  pins — while still serving its index (measured 2026-08-30, twice;
  F-78, library wishlist 52 — closed at library CP-62). From 0.1.4 the
  bring-up pins `16.0.3` (measured pullable) and pulls it itself — a
  fresh `./bootstrap.py up` needs no mirror step — and if a registry
  event ever takes that tag too, `./bootstrap.py up --forgejo-image
  <ref>` names any live reference (the mirror's
  `code.forgejo.org/forgejo/forgejo:16.0.3`, a `name@sha256:…`),
  forwarded to the bring-up verbatim. **The cure for anyone still on
  0.1.3** needs no second host: the Forgejo project's mirror serves the
  very same image (`code.forgejo.org/forgejo/forgejo:16.0.2` — the same
  index digest `sha256:2fdfe28b…`, both platforms, measured), so

  ```bash
  docker pull code.forgejo.org/forgejo/forgejo:16.0.2
  docker tag  code.forgejo.org/forgejo/forgejo:16.0.2 codeberg.org/forgejo/forgejo:16.0.2
  ./bootstrap.py up            # a CP-62-era bootstrap finds the image present and does not pull
  ```

  is byte-identical to what codeberg served (not a re-tag of another
  version — that would lie about provenance). This checkout's bootstrap
  floors the library at `>=0.1.16` and refuses before the recipe would
  matter — for it, the upgrade IS the cure; the recipe is for the demo
  checkout of the same era (`git checkout 13d579e`).
- **Two pull outcomes that are not a missing manifest** (the 2026-09-06 (UTC)
  stranger rounds hit both; `bootstrap.py`'s pull-failure text names only
  the download-side causes today — an unreachable ghcr.io, a dropped
  platform manifest — and prescribes an out-of-band load, so read the
  docker error above it, which is authoritative): (1) a pull that prints
  `Retrying in N seconds` per layer and ends `unexpected EOF` is a
  **transport failure** — re-run `./bootstrap.py up` (idempotent: the
  daemon resumes from the layers it kept — on the re-run it re-announces every
  layer as `Pulling fs layer` and the kept ones report `Download complete`
  within seconds, a resume that reads like a restart: round seven's a2
  finished the retrieval image in 16 min on the re-run after 24 on a killed
  attempt; a stranger's cold pull of the
  retrieval image retried two layers for 48 min on a slow pipe before
  failing this way — 52 min of `up` in all);
  (2) a pull that downloads every layer and then fails `failed to
  extract layer … operation not permitted` (whiteouts) or `failed to
  mount … fstype: overlay … invalid argument` means **the daemon's
  storage cannot write here** — the registry answered; `docker run --rm
  alpine true` is the check (a plain `docker pull debian:stable-slim`
  succeeds on such a daemon, so a pull proves nothing), the cure is the
  daemon (a nested daemon needs its data root on a volume, `-v
  /var/lib/docker` — prefer this: `vfs` also cures it but costs a full
  image copy per container: 3.7× the disk and a 17× slower sandbox create
  measured against an overlay2 control (round five), and on a busy host it
  blows Polar's 600 s sandbox-create budget outright — round four), and
  `docker save/load` fails on the very same layers.
- **The pull that is healthy and silent** (measured 2026-09-07, round
  three: one stranger saw **21 minutes without a line** on a working pull
  of the retrieval image at ~155 KB/s and had the `docker pull` PID in hand,
  "one keystroke from killing it"; the whole image took 45 min on that pipe;
  another stranger's took 39). `docker pull` prints a line only when a
  layer *changes state*, so a single large layer on a slow pipe prints
  nothing until it lands — the "~4 min" above is a fast pipe. Since
  library CP-94 `up` prints a heartbeat once a minute during a pull
  (elapsed time, and whether this host received bytes in the last minute),
  and `./bootstrap.py status` says `ACTIVE` while an `up` runs. **Since
  library CP-96 the heartbeat also names the layer phase** — `N/M layers
  complete`, then whichever of `K extracting`, `K downloaded, waiting to
  extract` and `J downloading` apply, in that order (a round-seven reader met
  the third and checked it against this sentence) — and says when **no bytes
  are expected**: after every layer prints `Download complete` the daemon
  extracts, which moves the disk and not the pipe; round four's heartbeat
  said "26.0 KiB in the last 60s — the pipe is moving" through forty
  minutes of that, and a stranger counted `Download complete` against
  `Pull complete` by hand to tell a phase change from a stall. Before you
  conclude a silent pull hung, three checks, in order: (1) the heartbeat
  (or `./bootstrap.py status`) — if the host is still receiving bytes it
  is slow, not hung, and if it says extraction, a quiet pipe is expected;
  (2) **`df --block-size=1M`** on the daemon's data root (`docker info --format
  '{{.DockerRootDir}}'`) twice a minute apart — it grows as layers land.
  **Megabytes, not `df -h`**: at this project's bandwidth a human-readable
  `df -h` is blind, and this README used to prescribe it — round six measured a
  flat `102G` twice while a `df -k` sampler on the same filesystem moved
  **+214 MB/min**, and the reader nearly filed a disk regression against a
  correct README. (Not `docker system df` either, which this README named before
  that: measured flat through an actively progressing pull on Docker 29.8 — it
  accounts an image only once the image is complete.) One caveat the check
  needs: **on a shared data root `df` counts every tenant**, so it is only
  attributable when the data root is on its own filesystem. (3) the failure
  signatures in the bullet above — `Retrying in N seconds` **followed by** a run
  that ends `unexpected EOF`, or `failed to extract` / `failed to mount`. Read
  that first pair as a conjunction: **the retry line alone is the pull
  recovering out loud, not a fault** — it was measured on healthy pulls that
  completed, in three rounds out of three, and this README used to say a healthy
  pull never prints it, one sentence before telling you to interrupt. Only then
  kill it, and re-run `up`: the daemon resumes from the layers it kept.

## What a trajectory looks like

`./read.py show` on a real archived episode — this one from the CP-36
stranger run, the 0.6B reference model (the demo's floor, honestly
rendered), lightly trimmed at one marked spot:

```
== episode sk-polar-550e486e-f544-45cb-859a-060012f16791 (accepted; archived thinking-off) ==
task        case_orchard @ timestep 2   (free, split train)
status      COMPLETED
model       Qwen/Qwen3-0.6B via openai_chat
checkout    branch timestep-2, commit 48499faa81 — pages 1..2 (2 visible at this cutoff)
turns       2 assistant turns, 2 tool calls
tokens      prompt 2,835; response 460 (107 trainable = 23%)
finish      stop
deliverable NONE — no `write` call this session (acceptance checks provenance, not task success)
system      4,466 chars, sha256 f56e8a6e9ea9dd1c… (the G2-pinned prompt — not repeated here)
rebuilt     2/2 completions merged, 1 full chain(s); builder findings: 0
timing      run 9.9s (init 0.2s, post 0.2s)

-- the task prompt --------------------------------------------------
What evidence about the true boundary line between the parcels is in the case file so far, and which way does each piece point? Cite pages as (page:N).

-- the session ------------------------------------------------------
[turn 1]
   -> mcp_gsj_search_case {"query": "true boundary line between parcels", "k": 1}
   -> mcp_gsj_search_decisions {"query": "true boundary line between parcels", "k": 1}
   <- 1 hits, pages [2] — all <= timestep 2 (the cutoff holds)
      page 2  score 0.52  md/page_0002.md
         ## Page 2 — The 2019 fence survey A survey commissioned jointly in March 2019 and carried out by the public surveyor Lena Ortiz located the registered…
   <- (288 chars)
      [… the decisions-search hits, trimmed here; since CP-81 `show` renders them
         as what they are — court, docket, Randnummer, the citation each admits —
         see "Decisions" below …]
[turn 2]
   - The true boundary line between the parcels is located in **Page 2** of the file.
   - Each piece of evidence points to **Page 2** of the file.

-- the deliverable --------------------------------------------------
NO deliverable was written — no `write` call happened in this session.
(This row's prompt is free-form (no skill card names a file); a session can qualify without one — qualification checks provenance, not task success.)
```

Three lines carry the demo's whole argument. The **checkout** line plus
the search result's `all <= timestep 2 (the cutoff holds)` — the temporal
cutoff is *observable* per episode, checked on the spot, not asserted.
The **deliverable** line — this episode qualified (its provenance is
sound) while plainly failing the task, and the system grades those two
things separately, in the header. And the **tokens** line — `107
trainable` is the loss-maskable span a trainer would actually consume
(`./read.py export` hands over a derived JSON projection, arrays referenced
by sha256). The three counts have three scopes, and the archive's own
`conventions` block is the source: `prompt` is the rendered prompt;
`response` is the **whole session's merged chain** after it — every
assistant turn *and* every tool result replayed as context, one
`response_ids` array (`loss_mask` 0 on the replayed tokens); `trainable`
is the sampled tokens alone, the `loss_mask` 1 positions. The 8,192-token
generation cap (`max_tokens` in `config.yaml`, pi's `maxTokens`) bounds
**one completion** — one assistant turn's generation — never the session,
so a `response` of 19,000 tokens with `finish stop` is not a contradiction:
no single turn hit the cap, and the count is the chain. (A round-six
reader met exactly that header and asked for the scopes; measured on the
CP-102 fresh-clone pair: a `response 2,522` episode whose two turns span
`[0, 34)` and `[2480, 2522)` — 76 trainable, the 2,446 between them one
tool result replayed.) A stronger model produces stronger sessions — the same
stranger run's 6-turn `case_mill` episode read all three pages in order
and wrote a coherent brief; what this weak one shows is that even the
floor is rendered honestly. (The header's `run 9.9s` is the sandboxed
session alone; the ~20–40 s expectation above is the whole
submit→archive round trip.)

## The three inputs

A corpus in [the contract's shape](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md)
(drawn below, under "Bring your own corpus"),
a `config.yaml` with your inference endpoint's URL and served-model name,
and that endpoint itself — that is everything; the bootstrap derives the rest.
A host-local endpoint (`http://127.0.0.1:…`) is fine: the bootstrap rewrites
it to `host.docker.internal` for the containers and prints the rewrite — on
Linux the endpoint must then listen beyond loopback (`config.yaml.example`
says why). A **decisions drop** needs no fourth input: put it inside the
corpus as `decisions/` and the library validates, locks and serves it
("Decisions" below).

Words this README leans on: the **estate** is the five demo containers on one
private docker network; **Polar** is the episode runtime the library vendors —
one published *image*, run here as three of those containers (the rollout
server, the gateway, and the receiver);
**pins** are this estate's approved fingerprints — tokenizer tail, system
prompt, skill cards — the receiver validates every trace against them; a trace
is **accepted** (it *qualified*) when it passes those provenance gates, which
says nothing about task success. Four published images make the estate —
Forgejo, `gsj-mcp-service`, `gsj-polar` (one image, three of the standing
containers), and `gsj-pi-harness`, the per-episode sandbox (started per
submit, not one of the five standing containers); **pi** is the agent
harness that works the task inside that sandbox. The **gates** (G1–G7)
are the receiver's per-trace validators — G1 pinned skill cards, G2 the
pinned system prompt, G3 the tool roster, G5 the temporal cutoff, G6 the
rendered tail before generation, G7 reconstruction and engine settings
(G4's byte hashes are estate-side) — specified in the library's
[checks-spec](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md).

The endpoint's contract, in one place: OpenAI-compatible chat completions
with a working tool-call parser; a context window >= the harness's
default 32,768; pinned sampling defaults (pi sends no sampling
parameters, so your server's defaults ARE the sampling policy); and, for
a non-Qwen model's automatic pin derivation, vLLM's `/tokenize` +
`/detokenize` — without them the reference defaults stand, loudly, and
`config.yaml.example` names the manual keys that cure it.

## Run it

Library 0.1.17 is the floor: the host tool and pinned Polar image carry the
estate activation and generated-lock reader refactoring. Retrieval image 0.5.1
carries the Starlette response helpers. Existing behavior is preserved. The `up`
this script drives still lists the rows `--row N` addresses under the taskbank line of its
`== run demo ==` block — the block this script echoes before it stands its own
Polar leg — and its Forgejo pull's heartbeat, when a pull is slow enough to print
one, says how long the layer tally has stood unchanged. What each earlier floor
added is at the end, under [What each floor carried](#what-each-floor-carried): it
stood here, forty lines of it in front of the commands, until a round-seven reader
filed it (F-127). One piece of it you need here: the estate writes three
`rollout.yaml` files — the bring-up's own `work/runs/demo/rollout.yaml`, for a
host-run Polar; `work/estate/rollout.yaml`, re-addressed for the three containers —
what episodes run with, and what `preflight.py` reads; and
`work/estate/receiver/rollout.yaml`, the receiver's own copy of that one, so its
`serve` re-renders a topology beside its own config and never aliases Polar's (a
round-five stranger looked in the wrong one first, a round-seven one found the
third with `find`). `work/runs/demo/pins.skeleton.json` sits beside the first, and
on this estate the walk it starts is not needed: `bootstrap.py` has already derived
real G1/G2 into `work/estate/pins.gsj.json`.
The bootstrap also checks that Docker can run a container and distinguishes
download failures from extraction/mount failures. The Polar image carries the
same wheel; a host pip upgrade alone cannot update its packaged tools. Credentials
adopted by the estate must follow the [shared credential grammar](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/server-guide.md):
nonempty printable ASCII
without apostrophes or an odd run of trailing backslashes.

```bash
# prerequisites:
#   Docker with the `docker compose` plugin (Compose V2 or later — the Go plugin,
#     not the legacy `docker-compose` v1; measured on 2.37.1 and 2.40.2) whose
#     daemon can RUN a container: `docker run --rm alpine true` exits 0. A daemon
#     that answers `docker info` and even pulls single-layer images can still be
#     unable to start one — a nested daemon on overlayfs did exactly that on
#     2026-09-06 (two stranger runs died there, one 67 s into `up`); the pull is not the check,
#     the run is.
#   Python >= 3.12, git
mkdir -p gsj-demo && cd gsj-demo     # a directory of your own: the venv lands HERE,
                                     # the clone beside it (an in-tree .venv would show
                                     # as untracked — the demo's .gitignore does not list it).
                                     # Already cloned to read this README? `cd ..` first:
                                     # the venv goes beside the clone, then `cd` back in.
python3 -m venv .venv && . .venv/bin/activate   # PEP 668 systems (Ubuntu >= 23.04)
                                                # refuse a bare pip install
pip install --timeout 120 --retries 5 \
  'gsj-harness-rollout-server>=0.1.17' pyarrow   # the library + the taskbank's parquet writer
                                                 # (add `pytest` to run the regression suite,
                                                 # README's last section). The two flags are IN
                                                 # this line on purpose: pip's default 15 s read
                                                 # timeout dies mid-way through pyarrow's 46.8 MB
                                                 # wheel on a slow pipe, and three strangers in
                                                 # three rounds hit it with the cure sitting in a
                                                 # paragraph they had already scrolled past. They
                                                 # cost a fast pipe nothing.
git clone https://github.com/MHGanainy/gsj-rollout-demo && cd gsj-rollout-demo

./synthetic/make_corpus.py        # the worked example: the corpus AND the thirty
                                  # decisions inside it — or bring your corpus
cp config.yaml.example config.yaml   # then fill in the three values:
                                     #   corpus — the tree above (./corpus-synthetic)
                                     #   inference.base_url — the endpoint's ORIGIN, no /v1:
                                     #     the gateway appends /v1/chat/completions itself
                                     #     (`validate` refuses a suffixed one)
                                     #   inference.model — an `id` from
                                     #     `curl <base_url>/v1/models`, byte-for-byte
                                     #     (pick the one you mean if several are listed;
                                     #     none listed = your endpoint is not up)

./bootstrap.py validate           # check the corpus before anything runs
./bootstrap.py up                 # the estate
```

**Apple Silicon / ARM**: nothing to do — every image pulls natively since
library CP-64 closed the last amd64-only gap (platform fact 1 above).

`up` runs, in order: **validate** the corpus (and stop loudly if it fails —
nothing runs against an invalid tree) → pull the three ghcr.io images
(the bring-up pulls Forgejo itself, a fourth — so the pull phase is not
over when `bootstrap.py`'s three land; round four waited 92 minutes and
then met a fourth pull) → derive
**this estate's pins** from your corpus and your endpoint → hand your three
values — and an external decisions fallback, if you kept one beside the
corpus, as `--decisions-dir` — to **the library's own estate tool** (`python -m gsj_rollout.estate`,
the production tool the wheel ships since 0.1.3 — as `gsj_rollout.bringup`
through 0.1.5, renamed at library CP-72 — the exact answers it gets
are written to `work/bringup-answers.yaml`), which stands up **Forgejo**,
creates the owner and mints its tokens, **scaffolds** the corpus into
per-case repos, stands up the **MCP retrieval service** (printing the
retrieval config — the decisions line names your drop — before anything
is embedded) and **ingests** the cases and the decisions,
builds the **taskbank**, **verifies** everything round-trip, and writes its
run record → re-address its `rollout.yaml` for containers and stand up
**Polar** (rollout server, gateway, receiver —
[as one published image](docs/ADR-0001-polar-as-a-container.md)) → print
what is running, where, and how to stop it. Since library 0.1.3 this
script *reads* config.yaml and drives that tool; nothing the tool does is
re-implemented here (an operator with more than three inputs — an existing
Forgejo to adopt, another owner, another embedding model — runs the tool
directly; its `--help` lists every knob).

Running `up` twice is safe — the bring-up reuses what stands (tokens
verified, repos converged, the index matched by fingerprint) and says what
it reused; the Polar leg is recreated only when its generated files
changed. `./bootstrap.py down` stops the estate; `down --wipe` resets it.

The estate is five containers on the `gsj-demo-net` docker network, in
two compose projects: `gsj-demo` (the library's bring-up — `gsj-demo-forgejo`,
`gsj-demo-mcp`) and `gsj-demo-polar` (this repo's Polar leg —
`gsj-demo-polar-rollout`, `gsj-demo-polar-gateway`, `gsj-demo-receiver`);
`docker logs <name>` reaches any of them, and `./bootstrap.py status` lists
what stands — in one of three states: **ACTIVE** (an `up` or `down` holds
`work/.bootstrap.lock`: it says wait and suggests nothing — during the
image pulls there is no record and no container yet, which is normal;
before library CP-94 it printed `nothing running — ./bootstrap.py up` then,
and a stranger nearly obeyed), **no estate** (nothing running, no record:
`./bootstrap.py up`), and **standing** (the containers, the URLs, the
submit recipe). The lock is the kernel's `flock` on that file, not the
file: when an `up` is killed, the kernel drops the lock with the process
and the file with its dead pid stays behind — `status` then sees no
holder and reports the estate, not ACTIVE, and `up` takes the lock again.
So a lock file whose process is gone is detected as stale and ignored, and
**never needs removing by hand** (a round-six reader was killed twice
mid-`up`, recovered exactly this way, and found the sentence missing; the
suite measures it on the real probe). The
bring-up publishes Forgejo and the MCP on `127.0.0.1` host ports of its
choosing (its recipe; the ports are in its `== run demo ==` block and in
`work/runs/demo/run.json`); the Polar leg publishes **no host ports** — to
talk to it, join the network, as every command below does. Everything the
estate generates or archives lives under `work/` — the bring-up's run
directory is `work/runs/demo/` (its `.env` holds every secret, mode 0600 —
the only place a value is *written on purpose*: the retrieval service's
clone cache under `work/runs/demo/mcp-data/` also carries the read token in
its bare clones' git config, library wishlist 47, which is why the whole run
directory is mode 0700; its `run.json` names variables, never values), the
Polar leg's files are `work/estate/`, the archive is
`work/traces/` — except the derived corpus files: `taskbank.parquet`,
`corpus.lock.json` and, when decisions/ contains XML, `decisions.lock.json`.
These are written at the corpus root and belong with its data.

## Walkthrough: an episode, submitted and read

You have just run `up` and its final printout ended with a `docker run`
one-liner. This is what to do with it. If a late phase failed and the
printout never came (round four: two strangers), the same one-liner is on
disk at `work/estate/submit.sh` — written the moment it became derivable,
before the Polar leg — and `./bootstrap.py status` reprints it; `status`
reports a partial estate rather than crashing on it since library CP-96.

**0 — preflight your endpoint (once per endpoint, before spending episodes):**

You may run it before `up` too, as soon as `config.yaml` is filled: every
row except `tokenizer tail` answers then (that row waits for the pins `up`
derives, and skips, saying so — a `[ -- ]` line naming the missing file),
and on a non-reference model the `end-of-turn id` row settles only after
`up` derives the id into `work/estate/rollout.yaml` — until then it is a
`[warn]` saying the derivation has not run (since library CP-96; it used to
be a `[FAIL]` whose second cure was the very thing the next sentence
forbids — "the tool wins by proximity", a round-four stranger wrote, and
nearly took it). **Do not cure a pre-`up` mismatch by writing the id into
`config.yaml`**: an explicit value there overrides the derivation you are
about to test (two strangers nearly did; in both cases the derivation had
already given the same id unaided — which the `[warn]` row prints from
**your** endpoint, not from this page). **Exit codes**: 0 when no row is `[FAIL]` (warnings are
the limits of what an API can see), 1 when one is, or when `config.yaml`
cannot be read — so a healthy endpoint exits 0 both before and after `up`,
and the early run is safe under `set -e`. And after `up`, the `end-of-turn id` row
reads `work/estate/rollout.yaml` — *what episodes run with* — not
`config.yaml`: an edit to `config.yaml` changes nothing until the next
`up` regenerates that file, and the row says which file it read
(measured 2026-09-07: a deliberately wrong `end_of_turn_token_id: 151645`
appended to `config.yaml` after `up` left preflight all-ok).

```bash
./preflight.py
```

**Run it again after `up` and before your first submit — `up` can exit 0 on
pins it expects to be quarantined.** On a non-reference model `up` derives the
G6 tail and the end-of-turn id from your endpoint with one `/tokenize` request
per probe, each under a 15 s timeout and no retry, so on a shared endpoint one
request can simply miss. `up` then keeps the reference estate's values, says so
in its log (`the first episode will likely be quarantined at G6`) and still
exits 0; the post-`up` preflight is the gate that exits 1 on it, with `[FAIL]`
on the `tokenizer tail` and `end-of-turn id` rows. The cure is the one the log
names — re-run `./bootstrap.py up` with the endpoint live (23 s warm, round
seven) — and three things that failure path prints are not to be believed as
written: the log's `this endpoint cannot render its own chat template over the
API (not vLLM?)` is an inference from one lost request, not a measurement
(round seven's endpoint was vLLM and answered the same request in 0.25 s either
side of it); `work/estate/pins.gsj.json`'s `coverage.g6_expected_tail_ids`
still reads `derived here from the endpoint's own template render` — its
`derived_at` line says FAILED, so read that one; and the library tool's
`WARNING: --end-of-turn-token-id 151645 disagrees with the endpoint's own
render` is `bootstrap.py` having passed the reference id down as though you
had chosen it, so the library's own successful measurement is overruled and
the cure it names uses flags this script does not expose — the re-run is the
cure. Round seven's a2 met all four in one run and caught them only because it
ran this preflight after `up`; `FINDINGS.md` F-122 and F-123 carry the
`bootstrap.py` half.

The demo's smoke ran against the reference stack (vLLM serving
`Qwen/Qwen3-0.6B` with pinned sampling). Your endpoint differs in ways that
break *different* things — no tool-call parser, another tokenizer, unpinned
sampling, a smaller context window. The preflight probes what an API can
reach (reachability, the served name, the context window, the tool parser,
the served tokenizer against this estate's pinned tail ids, the end-of-turn
id, and whether your chat template **rewrites history** across turns — the
one failure you would otherwise learn only from G7 quarantines after the
episodes are already spent) and names each mismatch **with its
consequence** — so you learn your tokenizer differs from a preflight row,
not from a quarantined episode. What an API cannot see (your sampling
defaults) it says so, once, out loud — its `sampling defaults` row ends
"pin them server-side", which is advice for the first of the two cases
under Platform fact 2; on a borrowed endpoint read it as "The borrowed
endpoint" below.

For comparison, the reference stack's serve argv — the endpoint every number
in this README was measured against:

```bash
vllm serve Qwen/Qwen3-0.6B --max-model-len 32768 \
  --enable-auto-tool-choice --tool-call-parser hermes \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --chat-template qwen3_training.jinja \
  --generation-config <dir holding the snapshot's generation_config.json>
```

The last two flags are load-bearing: the symmetric chat template
([TRL's `qwen3_training.jinja`](https://github.com/huggingface/trl/blob/main/trl/chat_templates/qwen3_training.jinja))
is why multi-turn episodes reconstruct as ONE chain, and the pinned
generation config IS your sampling policy — pi sends no sampling parameters.

**1 — submit one episode.** **Copy the fenced command below, not the `up`
printout's one-liner**: they differ in one flag, and the fence is already
correct. The printout (and `work/estate/submit.sh`) end in `--row 0`, which is
a real episode — `case_mill@3`'s precedent prompt, the one step 3 runs — while
this walkthrough explains **`--row 2`**, `case_orchard@2`, the transcript shown
above. Neither is wrong and you need not edit anything; take the block below
and the rest of this section describes what you get. (The printout has named
the bank's first row and said so beneath itself since library CP-94, after a
stranger copied it verbatim and ran a different episode from the one explained
here; a round-six reader pointed out that a warning about a mismatch is not the
same as not having one, which is what this paragraph now removes. The
taskbank is what the bring-up built from your corpus — the printout's
taskbank line says how many rows yours produced; the synthetic corpus makes
six rows, numbered 0–5, sorted by case, timestep and prompt id, and **row 2**
is the transcript shown above; rows 0 and 4 are the two precedent prompts of
"Decisions" below — step 3 runs one — and rows 1 and 5 are the skill-card
tasks the 0.6B floor model is apt to loop on). The estate requires sign-in for read (a sandbox agent cannot
re-clone a case past its cutoff), so the generated config names the
read-scoped token by *variable* (`estate.clone_credential_env`) and
`submit` presents its value. Since library 0.1.7, `submit` reads the `.env`
beside its config when the variable is not exported, so the run's `.env`
is mounted read-only beside `/estate/rollout.yaml` and nothing is sourced
or exported; the token never reaches a trace:

```bash
docker run --rm --network gsj-demo-net \
  -v "$PWD/work/estate:/estate" -v "$PWD/work/runs/demo/.env:/estate/.env:ro" \
  -v "$PWD/corpus-synthetic:/corpus" -e GSJ_PINS_PATH=/estate/pins.gsj.json \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.17 \
  gsj-rollout submit --config /estate/rollout.yaml \
    --from-bank /corpus/taskbank.parquet --row 2
```

Run it from the clone root: the fence reads `$PWD`. `work/estate/submit.sh`
holds the same command with absolute paths written in and passes extra
arguments through, so it runs from anywhere — it ends `--row 0`, and
`work/estate/submit.sh --row 2` gives this row (the last `--row` wins).

(The token variable's name follows your corpus's `owner:` —
`GSJ_FORGEJO_READ_TOKEN_<OWNER>`; the `up` printout and `./bootstrap.py
status` print the recipe with yours, and `estate.clone_credential_env` in
`work/estate/rollout.yaml` names it. An exported value still wins over the
file — the library's rule — which is why the old recipe's subshell
(`set -a; . work/runs/demo/.env; set +a` around the `docker run`, with `-e
GSJ_FORGEJO_READ_TOKEN_<OWNER>`) keeps working on this image too; it is
simply no longer needed. Never leave those secrets exported in your shell:
a value left there would beat the run's `.env` in compose's interpolation
on a later `up`.)

(One episode at a time under this one-liner: the client submits every
task as `gsj-task`, and a second `submit` while the first still runs is
refused with an opaque `409 Conflict` — pass `--task-id <another>` for a
concurrent one, or wait. The README's example transcript is row 2,
`case_orchard@2`; rows 1 and 5 are the skill-card tasks the floor model is
apt to loop on.)

**1b — the pair that shows the cutoff *binding*, not merely holding.** Row 2
alone cannot tell you *where* the temporal cutoff is enforced: at `t=2` the
case branch holds only two pages, so no later page **could** be retrieved
whatever the retrieval service does. The two mechanisms — a checkout scoped to
`T`, and a retrieval bound that filters by `T` — are indistinguishable on one
row. **The same case at a second timestep separates them**, and this corpus is
built for it. Run row 3 beside row 2:

```bash
docker run --rm --network gsj-demo-net \
  -v "$PWD/work/estate:/estate" -v "$PWD/work/runs/demo/.env:/estate/.env:ro" \
  -v "$PWD/corpus-synthetic:/corpus" -e GSJ_PINS_PATH=/estate/pins.gsj.json \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.17 \
  gsj-rollout submit --config /estate/rollout.yaml \
    --from-bank /corpus/taskbank.parquet --row 3 --task-id easement
```

Row 2 is `case_orchard@2`, row 3 is `case_orchard@4`, and the **1998 easement
deed exists only on page 4** — deed no. **98-4417**, registered 11 August 1998,
a number that appears nowhere else in the corpus (the suite checks the thirty
rendered decisions for it). Row 3's prompt asks for exactly that, as a
case-file question:

> Is there an easement deed in the case file so far? If so, which page records
> it, what is the deed number and when was it registered? Cite the page as
> (page:N).

**What the t=4 transcript should show**, in order: a `-> mcp_gsj_search_case`
line under turn 1; a `page 4` hit in its result (`<- 4 hits, pages [4, 1, 2, 3]
— all <= timestep 4 (the cutoff holds)` in every CP-103 sample); and an answer naming `98-4417`, the date and page 4.
`./read.py export`'s `page_census.search_pages_returned` lists the pages the
searches returned (`[1, 2, 3, 4]` here) and `pages_beyond_timestep` is `[]` —
on both rows. Same case, same corpus, same estate, one flag apart: the
difference between the two transcripts is the retrieval bound doing its job.
On the 0.6B floor model library CP-103 measured this wording at **5 of 5**
samples opening the case file at t=4, every answer naming 98-4417, the date
and page 4 (as "page 4" in prose, never as the `(page:4)` token the prompt
asks for — the floor model being itself). **Run by strangers, round seven**:
both demo-door readers ran this fence verbatim against a borrowed
`qwen3.6-27b`, and both t=4 episodes called `mcp_gsj_search_case` first
(`easement deed`, then `Grunddienstbarkeit` or `easement`), got page 4 as the
top hit, made no decisions call and answered `(page:4)`, `98-4417`, `11 August
1998` — the token form included.

**When the t=4 episode goes elsewhere.** The prompt leads to the case file; it
cannot force the agent there, and the floor model samples. If the transcript
shows a `-> mcp_gsj_search_decisions` line and **no** `-> mcp_gsj_search_case`
line, the agent answered from precedent: the episode is still **accepted**
(acceptance checks provenance, not task success), its
`page_census.search_pages_returned` reads `null` — the case file was never
searched — and any page or registry number in the answer rests on nothing the
session retrieved. `show`'s `citations` line and the `dec:` grounding cover
the decisions half of such an answer; nothing yet grounds a `page:N` the way
`dec:` tokens are grounded (`FINDINGS.md` F-120 prices that check), so read
`search_pages_returned` and the tool lines as the check. Re-submit under
another `--task-id` and read the pair you get. This is not hypothetical: row
3's *shipped* wording ("Does any recorded easement or right of way affect the
disputed strip? Name the registry number and cite the page") did exactly this
on the floor model in library CP-102's run and in 4 of 5 samples at CP-103 —
a decision's docket as the "registry number", a `page:7` no checkout holds —
which is why the wording changed.

**The same question at t=2.** Row 3's text lives at t=4 in the bank; to ask it
where the page does not exist, pass the triple instead of the row (the header
then reads `split None` — a triple submit records no split):

```bash
docker run --rm --network gsj-demo-net \
  -v "$PWD/work/estate:/estate" -v "$PWD/work/runs/demo/.env:/estate/.env:ro" \
  -v "$PWD/corpus-synthetic:/corpus" -e GSJ_PINS_PATH=/estate/pins.gsj.json \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.17 \
  gsj-rollout submit --config /estate/rollout.yaml \
    --case case_orchard --timestep 2 --task-id easement-t2 \
    --prompt 'Is there an easement deed in the case file so far? If so, which page records it, what is the deed number and when was it registered? Cite the page as (page:N).'
```

The honest t=2 answer is that the file does not (yet) contain one. What the
floor model actually does, measured 5 of 5 at CP-103: it searches the case
file (`<- 2 hits, pages [1, 2] — all <= timestep 2 (the cutoff holds)`, no
page 4), cannot name the deed number and says so ("not provided") — and then
writes that "the easement deed is recorded on page 1", which page 1 does not
say; two of five invented a 2019 registration, the survey's year. Read the
search result and the absent number as the evidence — that is the retrieval
bound holding — and the sentence about page 1 as the 0.6B model confabulating
over it. A larger model does what the prompt allows: round seven's a1 ran this
triple on the 27B unprompted — five case-file searches in English and German,
every one returning pages 1 and 2 only, then `mcp_gsj_case_status`
(`pages_visible 2`) — and answered *"No, there is no easement deed recorded in
the case file so far."*, with no page 4, no 98-4417 and no invented date. Two
wordings that offered an escape ("if the file does not contain
one, say so") were measured and dropped: at t=4, where the deed exists, the
floor model wrote that sentence **without calling any tool** in 3 of 5 and 5
of 5 samples — an honest-empty clause is a lazy exit for a small model, so
the prompt has none, and the t=2 negative has to come from a search that finds
nothing. (The library's register carried the pair as its row 107 — never run
by anyone outside the project through six stranger rounds, because nothing
asked for it; library CP-102 ran it as its author and found the shipped wording
going to precedent. Round seven's two demo-door readers ran it, one of them
both halves, and the row closed at library CP-104 — as a claim about what this
walkthrough can *show* a reader. It was never a question about whether the
retrieval service filters; the next paragraph says where that happens.)

**Where each half is enforced** — round seven's a1 asked for this beside step
1b, having seen the retrieval service's census carry all four orchard pages
while its t=2 searches returned `[1, 2]` and its t=4 ones `[1, 2, 3, 4]`. Both
halves take `T` from the task, never from the agent. **The checkout**: the
harness clones the case from Forgejo at `timestep-T` alone — `--depth 1
--single-branch`, the remote and the reflog then removed — so the sandbox's
`md/` holds pages `1..T`, and the estate requires sign-in for read, so the agent
cannot re-clone past it (that is what the git host is for: one repository per
case, one branch per timestep, cloned fresh into every sandbox). **The
retrieval**: the service indexes each case's *whole* document once — the census
a1 saw — and applies the cutoff per query. The harness mints every episode a
token signed with the estate's secret and carrying `case_id` and `timestep`; the
service checks the signature and takes `T` from the token alone;
`mcp_gsj_search_case` filters its candidates to `page <= T` *before* ranking (a
pre-filter, not a trim of the ranked list — the library's
`test_cutoff_prefilters_candidates_not_postfilters` pins it), and
`mcp_gsj_case_status` counts the same visible pages; `mcp_gsj_search_decisions`
is never clamped. So the pair separates the halves because a case-file search
never reads the checkout: at t=2 the index still held page 4, and the only thing
keeping it out of the results was the token's `T`. Different queries change
nothing — library CP-104 sent one query, `easement deed`, to this estate's live
service under a t=2 and a t=4 token: page 4 came back only under t=4, and a t=2
token re-encoded to `T=4` under its original signature was refused. **After the
episode**, `show`'s `all <= timestep T` and `export`'s `pages_beyond_timestep`
are `read.py`'s own computation over the archived trace, and the receiver's G5
is the library's (`checks.py`) over the same trace — two implementations of one
property on one record; neither is the filter, which acted before the trace
existed. G5 also reads the checkout's recorded posture (`gsj_workspace`:
shallow, zero remotes, pages `1..T`).

Polar starts a sandboxed episode container, the agent works the task
against your endpoint and the estate's retrieval, and the finished trace is
POSTed to the receiver, which **validates it against this estate's pins**
and archives it — accepted traces to `work/traces/`, rejected ones (with
their findings) to `work/traces/quarantine/`. The archive is durable and
receiver-side; `--out <dir>` would additionally keep a client-side copy,
which is the trainer's collection path, not this walkthrough's.

**2 — read it:**

```bash
./read.py                  # what landed: accepted and quarantined, one line each
./read.py show             # the latest episode, as a session transcript
./read.py export           # the same episode as JSON a program consumes
./read.py quarantine       # anything rejected: every finding, explained
```

`show` renders what the excerpt above shows: the task triple and the
checkout (branch, **the pages visible at this cutoff**), each assistant
turn, each tool call and its result, and the deliverable if one was
written. Three things it is careful about, because they are the point:

- **Retrieval results show their pages.** Every `mcp_gsj_search_case` hit
  prints `page N`, and the transcript checks them against the episode's
  timestep on the spot — `all <= timestep 2 (the cutoff holds)`. The
  temporal cutoff is observable per-episode, not asserted.
- **Decision hits show what they are.** Every `mcp_gsj_search_decisions`
  hit prints the court, the docket, the date and type, the Randnummer (or
  the section, for a unit that has none) and the citation the hit admits —
  `dec:<doknr>:rn:<N>`, or `dec:<doknr>` when there is no `rn` — and every
  `dec:` token the agent writes is checked against the session's own hits
  on the spot: `grounded` or `UNGROUNDED`, per token, beside the turn that
  wrote it; the header's `citations` line sums it up (and says NONE when
  hits were available and nothing was cited).
- **Thinking is rendered distinguishably** (the `|`-prefixed block inside
  the turn). The archive stores reasoning only inside the token arrays, so
  `show` decodes them — that needs `pip install tokenizers` and the served
  model's tokenizer; without it the transcript says, per turn, what it
  could not render rather than showing you a wall of half-truth.
- **Truncation is labelled where you will see it.** A `finish_reason:
  length` episode says so in the header AND at the point the text stops.
  It *qualified* — qualification checks provenance, not task success
  ([the library's checks specification](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/checks-spec.md))
  — and whether to train on it is the trainer's call.

`export` is a projection of the archived body — the trace fields keyed by
name (counts, boundaries, the receiver's findings, reconstruction stats,
page census, per-turn calls) with the giant token/mask/logprob arrays
**referenced, not repeated** (`--arrays` embeds them; they are ~95% of the
body's bytes, the archive already holds them verbatim, and the `archive`
block carries the archive file's sha256 so a consumer can verify it read
the same bytes). Its root key `format` is the version discriminator
(`gsj-demo-episode-export/2`; a stranger guessed `schema`). Two fields a
trainer can **assert on**, stronger than anything `show` renders:
`page_census.pages_beyond_timestep` — the temporal cutoff as a machine
field, `[]` on every accepted episode (`show`'s `all <= timestep 2 (the
cutoff holds)` is the same fact rendered) — and `gate_findings`, the
receiver's verdict (`[]` = accepted). What `gate_findings: []` does *not*
say is which gates had anything to check: see "What an acceptance covers".

Neither view adds anything: everything both show comes from the one
archived JSON the receiver wrote. The archive is the truth; these are views.

**3 — see the decisions tool work** (the walkthrough's row 2 is a free
prompt on the case file: on the reference model it searched decisions
too, on a stronger model it did not — both round-three episodes on a 27B
left `decision_census.searched: false`; a precedent row makes the agent
search them):

```bash
docker run --rm --network gsj-demo-net \
  -v "$PWD/work/estate:/estate" -v "$PWD/work/runs/demo/.env:/estate/.env:ro" \
  -v "$PWD/corpus-synthetic:/corpus" -e GSJ_PINS_PATH=/estate/pins.gsj.json \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.17 \
  gsj-rollout submit --config /estate/rollout.yaml \
    --from-bank /corpus/taskbank.parquet --row 0 --task-id precedent
./read.py show            # the hits render as court, docket, Randnummer, the citation each admits
./read.py export | python3 -c 'import json,sys; print(json.load(sys.stdin)["decision_census"])'
```

`decision_census.searched` is `true` and `hits_returned` counts the
paragraphs the agent read; whether it *cited* one is the `tokens_written`
list — the reference model's measured record is the table under
"Decisions"; round three's two episodes on a stranger's 27B wrote none
either, and round four's precedent-row episode on the same 27B wrote
twelve, all grounded, none ungrounded — what a model writes is the
episode's, not the model class's.

## Decisions

The estate's agent has **eleven tools on its roster**, and G3 pins that
roster as a whole (the eleven-tool wire array, hashed; the set is the
library's, not per-estate — a corpus does not change it). Counted from the
hashed array itself (`trajectory.traces[0].tools` in any archived episode —
this sentence used to say eight and three and then name a fourth, and a
round-six reader could not make it add up): **seven** are pi's built-ins —
`read`, `ls`, `grep`, `find`, `write`, `edit`, `bash` — and **four** are
this estate's MCP tools, all four inside the eleven G3 hashes:
`mcp_gsj_search_case` searches *this* case's pages and is scoped by the
episode's cutoff; `mcp_gsj_search_decisions` searches **court decisions** —
precedent, the same for every case, not cutoff-scoped; `mcp_gsj_case_status`
reports the episode's scope (`case_id`, `timestep`, `pages_visible`) and is
often the first call a capable model makes; `mcp_gsj_decision_stats`
reports the drop's census. The worked example brings thirty decisions:

```
./synthetic/make_corpus.py        # writes corpus-synthetic/, including decisions/
```

**What they are.** Thirty fictional decisions of two invented courts of
an invented district — the Landgericht and Oberlandesgericht Grevenau,
2009 to 2024 — in
[rii-dok v1](https://www.rechtsprechung-im-internet.de/), the XML the
German judiciary publishes its decisions in and the format the library's
[decisions surface](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/decisions-surface.md)
parses: one `jb-<doknr>.xml` per decision, a `doknr` that is its key, and
the body as `<dl class="RspDL">` rows whose `<a name="rd_N">` anchors are
the **Randnummern** (the numbered paragraphs a lawyer cites). Made-up
text, structurally real — the parser walks them exactly as it walks the
33,979 published Bundesgerichtshof decisions the surface was written
against, and returns whole Randnummern.

**Why they are worth reading.** They are written *about the demo's own
cases*: an orchard boundary dispute and a mill lease. So the thirty are
about easements and rights of way, the land register against a
long-standing fence, prescriptive possession, the scope of "agricultural
passage", termination of a commercial lease for arrears, rent reduction
for a flooded annex, a landlord who defers a repair it owes. A stranger
who searches for the right of way over the disputed strip gets back
paragraphs that answer the question — which is the only way to see that
the tool works.

**How the estate gets them.** No fourth input: the drop sits **inside**
the corpus as `decisions/`. Library 0.1.9 validates it with the corpus;
`up` writes `decisions.lock.json`, mounts it read-only and verifies that the
served drop matches the lock. The review before embedding names the drop,
and `./bootstrap.py status` prints it afterwards. Bring your own by
putting rii-dok v1 files there. A changed drop is picked up by re-running
`./bootstrap.py up`.

A drop kept outside as `<corpus>-decisions/` remains the fallback, without
the corpus lock: `./bootstrap.py up` detects the sibling drop and answers
the **library estate tool's** `--decisions-dir` for you through
`work/bringup-answers.yaml` — `bootstrap.py` itself has no such flag (its
`up --help` lists none). To migrate an older generated
drop inward, run `mkdir -p <corpus>/decisions` then
`mv <corpus>-decisions/*.xml <corpus>/decisions/` and re-run `up`.
Two populated drops refuse and name both paths; choose one before retrying.
With neither drop populated, the service serves its thirty synthetic
stand-ins and the tool still answers.

**Citing one.** The corpus's `AGENTS.md` carries the clause the surface
asks for (§9.5), so the agent is told the grammar:

```
- Cite a decision as `dec:<doknr>:rn:<N>` — the hit gives you both:
  `decision_id` is the doknr, `rn` is the Randnummer (for example
  `dec:GREV000082013:rn:7`).
- When the hit carries no `rn` (`rn: null`, or no `rn` key at all), drop the
  suffix and cite `dec:<doknr>`. Never invent an `rn`, and never cite a
  decision that no search in this session returned.
```

The second half is the **degradation rule**, and it is not decoration: a
hit on a whole section (a Leitsatz, a Tenor) carries `rn: null`, and a
production service that does not resolve Randnummern at all carries no
`rn` key — in both cases the suffixed form does not exist, and an agent
that invents one is fabricating. `./read.py show` checks every `dec:`
token the agent writes against that session's own hits and marks it
`grounded` or `UNGROUNDED`, and the header's `citations` line says what
happened — including `NONE`, when hits were there and nothing was cited.

Editing `AGENTS.md` moves this estate's G2 pin, which is correct and
expected: `up` re-derives the pin from whatever `AGENTS.md` your corpus
carries, so the receiver validates episodes against *your* prompt.

**What the reference model actually did, measured.** Do not expect the
clause to produce citations on its own — it did not here, and the honest
result is more useful than a promise. Five episodes were run against this
drop with the clause in the pinned system prompt, all accepted:

| episode | decision hits | `dec:` tokens written | what the agent wrote instead |
|---|---|---|---|
| `case_orchard@4`, the precedent prompt | 5 | none | the five doknr in prose, bolded |
| `case_mill@3`, the precedent prompt | 5 | none | four doknr in prose, with holdings |
| two earlier runs of the same two rows | 5 and 5 | none | the same |
| a free prompt spelling out the exact token form | 2 | **one, ungrounded** | `dec:GREV000082013:rn:7` |

So the 0.6B reference model — the demo's floor, untrained on this
grammar — copies the identifier and drops the syntax. Told the exact form
in the task prompt, it produces a token and **fabricates the Randnummer**:
both hits in that episode were section units carrying `rn: null`, whose
only valid citation is the bare `dec:GREV000082013`, and it invented
`:rn:7`. That is precisely the failure the degradation rule exists to
prevent, and `read.py` caught it at the source without being asked:

```
citations   1 dec: token(s) — 0 grounded, 1 ungrounded; 2 decision hit(s) available
   dec:GREV000082013:rn:7
   cites dec:GREV000082013:rn:7 — UNGROUNDED rn — the decision was retrieved
     (turn 1) but no hit carried rn 7
```

A stronger model will do better; the point of the demo is that you can
see which it is, per episode, from the archive alone. Whether a *trained*
policy follows the rule is an open question in the library's register
(its wishlist row 70), and it is the reason the grammar is checkable
rather than merely documented.

**What it costs.** Almost nothing, and the numbers say why the demo can
afford thirty where a real corpus is a different scale. The drop is 444 KB
of XML; the retrieval service reads it, parses **313 units** out of it (244
Randnummern and 69 whole sections — a Leitsatz, a Tenor, a title line) and
embeds 317 pieces in about 5 seconds inside the container **on an idle
Apple Silicon laptop with the native arm64 image**; the store on disk grows
to 1.8 MB, and `work/` after two episodes is 10 MB. It costs `up` nothing
you would notice there: the whole from-nothing run below, decisions
included, was **80 s**. On a contended CPU host the same 317 pieces are
minutes, not seconds — round four (a laptop running four nested-Docker
containers at once) measured them inside a 90 s window on one host and
could not measure them on another whose host slept mid-embed — and while they embed, the bring-up's poll line says the service is still
working: on this corpus almost always as `the service is still working (the
next collection has not reported a batch yet)`, the line both round-seven demo
readers saw. The named form, `building decisions: batch 1/1` (library CP-96),
prints only once a collection's first add batch has landed, and the thirty
decisions' 317 pieces are a single batch of up to 1,000, so that collection is
finished by the next poll. Before library CP-96 the line read `2/2 embedded`
and looked finished. The library's `--ingest-timeout`
(default 1800 s, on the process's clock) is the budget, and
`./bootstrap.py up --ingest-timeout <seconds>` forwards it. For comparison, the real corpus the surface was
written against is 33,979 decisions and about 1.16 million pieces — hours,
not seconds — which is why the library's `--decisions-dir` takes a
directory and re-embeds the decisions collection alone when the drop
changes.

## Both modes

The estate runs thinking-off by default. To run thinking-on:

```yaml
# config.yaml
thinking: medium        # the conventional ON; a bare `on` is a YAML boolean.
                        # pi's levels: off|minimal|low|medium|high|xhigh|max —
                        # every non-off level is wire-equivalent here
```

then `./bootstrap.py up` again — pins re-derive for the mode (the receiver's
archive stamp follows: `<session>.thinking-on.json`), the Polar services
restart on the changed files, and your endpoint needs no restart (the
harness switches the chat template per request). Submit again and `show`
renders the reasoning inside each turn.

## When something is rejected

A rejected trace is the most actionable object in the system: it names
exactly which gate failed and kept the full body as evidence.

```bash
./read.py quarantine            # list: session, mode, findings
./read.py quarantine <id>       # each finding: meaning + what to do
```

The classic first quarantine is `G6:prompt_suffix_ne_tail_ids` — a
thinking-mode mismatch between the submit leg and the estate's pins, or a
non-Qwen model whose pins never got derived at `up` time — the endpoint was
down, or it was up and its one derivation request timed out, which a shared
endpoint makes routine (step 0 says what that path prints). The bootstrap
derives them from the endpoint's own template render: re-run `./bootstrap.py
up` with the endpoint live, and the preflight's `tokenizer tail` row verifies
before an episode is spent.

## Bring your own model

The estate does not require Qwen. When `inference.model` is not the
reference, `up` derives the tokenizer-bound pins from your endpoint's own
template render — the G6 tail and the end-of-turn id, over vLLM's
`/tokenize` + `/detokenize` — and names, out loud, what it cannot derive
(G4's byte hashes; your sampling defaults). The library now owns the
recipe from an endpoint URL to the values `up` needs —
[docs/guide/bring-your-own.md#your-model](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/guide/bring-your-own.md#your-model):
the served name from `/v1/models`, the end-of-turn id and the
generation-prompt delta from `/tokenize` with the kwargs pi actually
sends, and what an endpoint cannot give you (G4's byte hashes, the
weights revision, the sampling policy), stated as absent; MODEL-SURFACE
below stays the item-by-item surface. Two facts about that derivation a
round-seven reader could not find here: it sends one `/tokenize` request per
probe with a 15 s timeout and no retry (on a shared endpoint, re-run `up` if one
misses — step 0), and it renders under the kwargs pi actually sends,
`{"enable_thinking": <level != off>, "preserve_thinking": true}` on every
request whatever the level. `preserve_thinking` is a template switch pi sends
unconditionally; the derivation renders under it because G6 compares what pi's
requests render, and whether a template reads either key is the template's own
business (one that reads neither renders the same tail both ways — Llama-3.x,
library CP-38; the library's bring-your-own.md, "The kwargs pi sends"). The preflight then verifies
the derived values and measures the one property nothing checks *before*
episodes are spent: whether your chat template re-renders history exactly
(if it does not, every multi-turn episode reconstructs as disconnected
chains and quarantines at G7 — the `template` row is where you learn that
before it costs you). The whole surface, item by item — what
changes with the model, who derives it, what breaks when it is wrong —
is [docs/MODEL-SURFACE.md](docs/MODEL-SURFACE.md). Honest status: the
first non-Qwen episode ran at CP-38 — Llama-3.1-8B-Instruct, served
with its own tool parser (`llama3_json`) and its own embedded template,
derived at `up`, preflighted all-ok, and **accepted: `chains_total: 1`,
eight completions merged, zero findings**. What the second family
taught (two turn terminators, the round trip's two halves, malformed
JSON ending episodes, retrieval-free green) is written where it
belongs: MODEL-SURFACE's "second family, measured" section.

## What an acceptance covers

`accepted` means the receiver's gates found nothing to complain about —
under **this estate's** `work/estate/pins.gsj.json`, whose approved sets
are not all this estate's. On a non-reference endpoint the file's eight
slots stand like this (a stranger tabulated them on 2026-09-07; the file's
`coverage` block says the same, per set, since library CP-94):

| approved set | gate | on a foreign endpoint | what an acceptance therefore says |
| --- | --- | --- | --- |
| `skill_card_hash` | G1 | **derived here** from your corpus's skill cards | the card the row resolved is one of yours |
| `system_prompt_hash` | G2 | **derived here** from your `AGENTS.md` | the wire system prompt is yours, byte for byte |
| `tool_roster_hash` | G3 | **carried** from the reference estate, **checked on every trace** | the roster on the wire equals the reference's eleven tools |
| `settings_hash` | G7 (settings clause) | **carried** from the reference, **checked on every trace** | the harness settings equal the reference's (compaction off) |
| `g6_expected_tail_ids` / `_tail` | G6 | **derived here** from the endpoint's own template render | every assistant turn opened with the tail your template renders |
| `tokenizer_hash` | G4 | **EMPTY** — not derivable over an API | **nothing** — no gate reads it; the served tokenizer's bytes were not measured |
| `chat_template_hash` | G4 | **EMPTY** — not derivable over an API | **nothing** — the served template's bytes were not measured |
| (no set) | sampling | **unknown** — pi sends no sampling parameters | **nothing** — the temperature that produced the logprobs is not recorded anywhere |

Two things follow. A carried set that *matches* is still a measurement —
G3 and G7 prove the harness is the reference harness on every trace. An
empty set is not a gate that passed; it is a gate nothing checks: on the
reference model the estate-side G4 walk (the library's `pins/derive_pins.py`,
run where the served snapshot's files are on disk: it hashes `tokenizer.json`
and the template file the engine serves) verified the tokenizer and template
bytes once, at pin time; on your endpoint nobody has, and `up`
says so (`pins — … EMPTY — nothing checks them — G4`). On the reference
model the same table reads carried-and-checked for G3/G7/G6 and
carried-not-checked-by-any-trace-gate for G4.

Where that warning belongs, argued at library CP-94: in the pins file
itself (`coverage`, `provenance.engine` — the record a trainer sets
`GSJ_PINS_PATH` to), in `up`'s pins line, and in `./read.py` beside
`accepted` (parked: F-87). Not in the library's `submit`/receiver — a
line there costs the size law and a release, and the archive already
carries the whole answer by reference: the pins file the receiver
validated against. `provenance.engine` used to be the reference estate's
server record copied verbatim (`Qwen/Qwen3-0.6B` at `127.0.0.1:8000`, the
H200's snapshot paths — "another machine entirely"); since library CP-94
it is re-recorded for the endpoint `config.yaml` names, with the reference
block kept under `carried_from`, labelled.

## The borrowed endpoint

`config.yaml.example`, the `up` printout and the preflight's `sampling
defaults` row all say "pin them server-side". That is the case where you
serve the model. The other case — a platform team hands you a URL you may
not restart or re-argv — is the normal one, and both round-three demo
strangers were in it. Then: the tool-call parser's *presence* you can test
read-only (the preflight's `tool parser` row does; the library's
`probe_model.py` step 5 too); its identity, the weights revision and the
sampling policy you cannot. Such an estate's episodes are still accepted
— every gate above still holds — and nothing downstream says the sampling
policy was unknown, except the pins file: `provenance.engine.sampling_policy`
and `coverage.sampling_policy` read `UNKNOWN`, which is what a trainer
setting `GSJ_PINS_PATH` sees. What those traces are good for: **provenance
work** (the cutoff, the pinned prompt and cards, the roster, the tail, the
reconstruction — every claim this README makes) — and **not for
training-distribution work**, where the temperature that produced 2,233
logprob'd tokens is the single largest unknown in the artifact (a
stranger's words). The library's register carries this as its open row 22
(per-episode engine binding); when you *can* pin, do, and record the argv.
Unknown is not the same as unusable: on both engines this project has
measured (library CP-09 and CP-09′) the captured logprobs matched a
teacher-forced replay of the model within numerical noise, so each number is
the model's own score of the token it emitted; what the unknown policy hides is
the distribution those tokens were *drawn* from — which a trainer needs for any
correction against the behaviour policy, and cannot recover from these traces.
On a borrowed engine whose version you do not know, the first half is
unmeasured too. Whether that disqualifies the traces is the trainer's call
(round seven's a2 asked).

## Bring your own corpus

The corpus is a directory tree in
[the contract's shape](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md).
The synthetic corpus is the worked example — `./synthetic/make_corpus.py`
writes exactly this, including its decisions drop:

```
corpus-synthetic/
├── corpus.yaml                  # names the corpus, the git identity, the sandbox image
├── AGENTS.md                    # the agent's standing instructions (G2's pin derives from it)
├── decisions/                   # thirty jb-<doknr>.xml files; up writes decisions.lock.json
├── skills/
│   └── brief/
│       └── SKILL.md             # a task shape; G1 pins these bytes
├── train/
│   └── cases/
│       └── case_orchard/        # one case = one document set
│           ├── timestep-2/
│           │   ├── pages/
│           │   │   ├── page_0001.md     # what exists at cutoff t=2 …
│           │   │   └── page_0002.md
│           │   └── prompts.yaml         # tasks at this cutoff (optional — contract §4)
│           └── timestep-4/
│               ├── pages/
│               │   └── page_0001.md … page_0004.md   # … two more pages exist by t=4
│               └── prompts.yaml
└── eval/
    └── cases/
        └── case_mill/
            └── timestep-3/      # pages/ + prompts.yaml, the same shape
```

Pages are absolute-numbered `page_NNNN.md` under each
`timestep-<T>/pages/` — a timestep holds every page visible at that
cutoff, so a later timestep repeats the earlier pages and adds its own,
contiguously from 1. (`up` scaffolds these source trees into per-case git
repos with one `timestep-<T>` branch each — the `md/page_NNNN.md` paths
you see in transcripts are that *generated* layout, not something you
create.) After `up`, the corpus root also holds `taskbank.parquet` —
the tasks, one row per prompt — and `corpus.lock.json`. A populated
`decisions/` adds `decisions.lock.json`, written by the scaffold phase of
`up` and checked against the served drop.

That shape, with your documents in the pages, is all `bootstrap.py up`
needs. `validate` names every rule your tree breaks before anything runs.

The synthetic corpus is also the demo's proof: the 1998 easement deed
(no. 98-4417) exists only on `case_orchard`'s page 4 — and, checked by the
suite, in no rendered decision — so an episode at timestep 2 *cannot* cite
it and an episode at timestep 4 *can* — the temporal cutoff, observable in
one fact (and in every `show` transcript's page lines). *Can*, not *must*:
whether the t=4 agent opens the case file is the agent's choice, which is
why row 3's prompt is shaped to lead there (step 1b says what to check).


## Reader evidence contract (CP-86)

`show`, `export` and `decision_census` share one tool-call-ID join. Reordered
results keep their tool identity. Missing results, unmatched results (including
those without IDs), and duplicate/ambiguous IDs are named and retained; none
is silently paired by position. Citation availability respects the turn in
which a result arrived. This checks identifier grounding, not whether a legal
claim is supported, and assigns no reward — `export`'s `reward` is the
trace's own field passed through, and `null` because nothing in this estate
scores (a rollout server that scores is outside the library's scope; filling it
is the trainer's).

A `write` call records an **attempt**, including its full attempted content.
Only the tool's recognized success acknowledgement establishes `succeeded` at
that turn; an explicit error or an error reply such as EACCES establishes
`failed`. A missing, ambiguous or unrecognized reply gives `unknown`. A success
acknowledgement does not prove that a file still exists. The deliverable is
the **last write attempt**; earlier attempts remain in each turn's calls/results.

`export` now emits **`gsj-demo-episode-export/2`**:

- `turns[].tool_calls[]` adds `id`. `turns[].results[]` adds `tool_call_id`,
  `name`, `status` (`matched`, `missing`, `unmatched`, `ambiguous`) and the
  full original `result` (null when missing), plus its `result_turn` arrival
  position; `chars` and `head` remain.
  Results follow call identity rather than arrival position. Extra results
  remain explicitly labelled; consumers must join by ID, never array index.
  An archive containing only orphan results has an unnumbered group (`n: null`),
  no token span and zero assistant turns.
- `deliverable` adds `attempted` and `outcome` (`not_attempted`, `succeeded`,
  `failed`, `unknown`). For attempts it carries `content`, raw `arguments`,
  `tool_call_id`, original `result`, `path` and `turn`. `written` is true only
  for recognized success, false for failed/no attempt, and **null for unknown**.
  A v1 consumer treating the old boolean as proof of success must migrate.
- `decision_census` retains its fields; corrected identity attribution can
  change hits, citable forms and grounding verdicts. Token/mask/logprob archive
  references and the original archives are unchanged. Token-span projection
  remains positional and is not the thinking decoder's stronger alignment
  guarantee (CP-82 §7 item 17).

Legacy unstamped/stamped archives, quarantine wrappers, current decision
result envelopes and historical concatenated JSON hit objects remain readable.
Malformed config/archive roots refuse with the file, expected shape and a
recovery action. The regression suite is `python3 -m pytest -q tests` (needs
`pip install pytest`, which the install line above does not bring; `python3`
rather than `python` because a stock Ubuntu >= 23.04 box has no `python` on
PATH unless the venv from "Run it" is active, and this section is a long way
from that activation — the same class of system the PEP 668 note names);
[fixture provenance and limitations](tests/fixtures/README.md) distinguish
real captures from synthetic message mutations. Phase 6 inherits this fixture
contract; no grader or core helper has been added.

## What each floor carried

The demo's floor moves with the library's releases. This is what each one added to
what a reader of this README sees, newest first; it opened "Run it" through library
CP-104, and a round-seven reader filed it as history standing in front of the
commands (F-127). The floors before 0.1.10 are the chronology in the stale-0.1.3
bullet under [What to expect, measured](#what-to-expect-measured).

- **0.1.17**: estate activation and generated-lock reader refactoring in the
  host tool and matching Polar image, plus retrieval image **0.5.1** with
  Starlette response helpers. Existing behavior, models, persisted formats
  and walkthrough requirements are preserved.
- **0.1.16** (library CP-106): an internal estate phase cleanup with behavior
  preserved. The host floor and matching Polar image carry the same release;
  the walkthrough and its evidence requirements are unchanged.
- **0.1.15** (library CP-104, released at CP-105): round seven's `up` — the rows
  `--row N` addresses listed under the taskbank line of the `== run demo ==` block
  this script echoes, and the pull heartbeat's tally age; in the library tool's own
  output that this script does not echo (its host-leg `next —` block), the pullable
  Polar image named from a wheel and every printed command carrying `--runs-dir`,
  `--corpus` and the interpreter; a cut pull transfer told to re-run the same
  command; a `/tokenize` request with no answer retried once.
- **0.1.14** (library CP-101, released at CP-102): an `up` whose closing
  `== run demo ==` block agrees with the pins line printed twenty lines above it: on
  this estate, where `bootstrap.py` has already derived real G1/G2 into
  `work/estate/pins.gsj.json`, the skeleton row says `G1/G2 EMPTY in it — NOT NEEDED
  on this estate` instead of 0.1.13's unconditional `EMPTY until an inspected
  quarantined episode supplies them` — the contradiction a round-six reader of this
  README filed from one screen.
- **0.1.13** (library CP-98 + CP-99, released at CP-100): the gateway-host probe
  whose `measured` label means what it says — a sentinel answering a per-run nonce,
  dialled from a container on the run's network AND from this host, with only the
  candidate that returns the nonce on both legs accepted, `host.docker.internal`
  appended rather than tried first on nothing but resolving, and a gateway port the
  process cannot bind reported UNMEASURED instead of measured against somebody
  else's listener (a round-five stranger lost a whole run to the old label); a
  `docker exec` that cannot start the interpreter reported as a failure rather than
  as silence; six sites that no longer write a measurement's word over an inference;
  a storage-driver warning carrying numbers measured against a control; and the
  fallback probe's reaper actually waiting out its bound.
- **0.1.12** (library CP-96 + CP-97, released at CP-97): the gateway-host probe by
  `docker exec` into the run's own retrieval container (a probe that cannot run
  degrades with the cure named instead of aborting one file short of
  `rollout.yaml`), every readiness wait on the process's clock with the measured
  wait printed beside the budget, the collection being built on the poll line,
  `verify`'s skips counted apart from its passes, the pull heartbeat naming the
  layer phase, and `work/runs/demo/pins.skeleton.json` beside the run's own
  `rollout.yaml` — with the G6 tail and end-of-turn id measured from the engine, and
  saying in the file whether the walk it starts is needed on this estate at all.
- **0.1.11** (library CP-94, released at CP-95): `status` in three states, the
  sandbox image checked before any Docker call, the pull heartbeat and the pins line
  naming the approved sets left empty.
- **0.1.10** (library CP-92, released at CP-93): the native-platform and split pull
  refusals, partial-run status and seven-verb help.
