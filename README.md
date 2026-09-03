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

## What to expect, measured

The numbers below are measured, not estimated — most on one from-nothing
run (library CP-36, the *stranger run*: a fresh clone, a fresh venv,
anonymous image pulls, an Apple Silicon Mac, no prior state) against the
reference stack — vLLM serving `Qwen/Qwen3-0.6B` host-local, the
two-case synthetic corpus; where a number comes from another checkpoint,
it says so. The CP-nn stamps name checkpoints of the library's measured
record — one report per checkpoint under its
[docs/reports](https://github.com/MHGanainy/gsj-harness-rollout-server/tree/main/docs/reports).
Wrong expectations make a working system read as broken — the trainer
repo learned that as
[its finding F-18](https://github.com/MHGanainy/gsj-harness-rollout-server-examples/blob/main/FINDINGS.md)
— so: what this costs, and what is normal.

- **Install**: seconds — clone 1.7 s, venv + `pip install` 5.5 s
  (measured at library CP-61, fast pipe). You bring Docker (compose v2),
  Python >= 3.12 and git.
- **Disk**: **~6 GB** of images (measured at library CP-61 on
  Apple Silicon: the daemon grew 5.4 GB for the four images, whose sizes
  sum to 6.1 GB — the pull transfers less; an earlier README said 3.5 GB —
  that was the compressed estimate, not disk). `work/` after one episode:
  10–14 MB.
- **`up`, cold on an empty docker host: ~4 min on the measured run, ~2.5 min where every image pulls natively; 80 s from a fresh clone where the images are already present** (measured at library CP-81: clone 0.1 s, venv + `pip install` from PyPI 40 s, `make_corpus.py` 0.05 s, `validate` 1.4 s, `up` 38 s — the estate, the corpus, and the thirty decisions embedded) — one uninterrupted
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
  (this checkout pins `0.5.0`, the decisions surface — library CP-79; its
  amd64 predecessor ran ~2 min under emulation for the first embed; the
  native first embed measured 22 s), `gsj-pi-harness:pi0.83.0-3` since
  library CP-64 (republished as a two-platform index under the same
  pinned tag, the amd64 child byte-unchanged), and `gsj-polar` always
  did. History, for anyone reading an old trace: before library CP-64 an
  ARM docker refused the sandbox's amd64-only manifest rather than
  emulating (measured at library CP-36, F-54), so the bootstrap pulled it
  `--platform linux/amd64` explicitly and the per-episode sandbox ran
  under emulation — episode speed unaffected even then, since the agent
  talks to your endpoint over HTTP. That cure retired with the arc.
- **Platform fact 2 — a non-Qwen endpoint works, and the serve argv is
  yours to write.** `up` derives the model-bound pins from your
  endpoint's own template render, automatically; what nobody can derive
  is your serve command — the tool-call parser and the sampling pins are
  flags only you can set. [docs/MODEL-SURFACE.md](docs/MODEL-SURFACE.md)
  walks the whole surface; the first non-Qwen episode
  (Llama-3.1-8B-Instruct, CP-38) derived at `up`, preflighted all-ok, and
  was accepted.
- **Normal, not broken.** An empty quarantine is normal — the reference
  stack measured 72/72 accepted at library CP-32, this demo's smoke 1/1.
  A small model hitting the 8,192-token generation cap is labelled, not
  silent: `submit` prints the `length-terminated:` line and `show` marks
  the truncation twice — such an episode *qualified*, and whether to
  train on it is the trainer's call. Degenerate episodes are the 0.6B
  floor model being itself, honestly rendered: an early smoke episode
  read `AGENTS.md` seventy times and wrote nothing, and the transcript
  collapses the repetition and says NO deliverable was written.
  Acceptance checks **provenance, not task success**. Two lines you would
  only ever have seen on a stale library 0.1.3 install (cured at the
  library's CP-62, shipped in 0.1.4 — this demo's floor moved 0.1.4 → 0.1.6 → 0.1.7): a false `pins —
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
  floors the library at `>=0.1.7` and refuses before the recipe would
  matter — for it, the upgrade IS the cure; the recipe is for the demo
  checkout of the same era (`git checkout 13d579e`).

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
(`./read.py export` hands over the same body as JSON, arrays referenced
by sha256). A stronger model produces stronger sessions — the same
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
says why). A **decisions drop** needs no fourth input: put it beside the
corpus as `<corpus>-decisions/` and `up` finds it ("Decisions" below).

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

```bash
# prerequisites: Docker (with compose v2), Python >= 3.12, git
# (a venv is yours to bring: python3 -m venv .venv && . .venv/bin/activate —
#  PEP 668 systems refuse a bare pip install)
pip install 'gsj-harness-rollout-server>=0.1.7' pyarrow   # the library + the taskbank's parquet writer
git clone https://github.com/MHGanainy/gsj-rollout-demo && cd gsj-rollout-demo

./synthetic/make_corpus.py        # the worked example: the corpus AND the thirty
                                  # decisions beside it — or bring your corpus
cp config.yaml.example config.yaml   # then fill in the three values:
                                     # corpus, inference.base_url, inference.model

./bootstrap.py validate           # check the corpus before anything runs
./bootstrap.py up                 # the estate
```

**Apple Silicon / ARM**: nothing to do — every image pulls natively since
library CP-64 closed the last amd64-only gap (platform fact 1 above).

`up` runs, in order: **validate** the corpus (and stop loudly if it fails —
nothing runs against an invalid tree) → pull the four images → derive
**this estate's pins** from your corpus and your endpoint → hand your three
values — and the decisions drop beside your corpus, if there is one, as
`--decisions-dir` — to **the library's own estate tool** (`python -m gsj_rollout.estate`,
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

The estate is five containers on the `gsj-demo-net` docker network. The
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
`work/traces/` — except the taskbank (`taskbank.parquet` +
`corpus.lock.json`), which is written beside your corpus because it is
derived from your corpus and belongs with it.

## Walkthrough: an episode, submitted and read

You have just run `up` and its final printout ended with a `docker run`
one-liner. This is what to do with it.

**0 — preflight your endpoint (once per endpoint, before spending episodes):**

```bash
./preflight.py
```

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
defaults) it says so, once, out loud.

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

**1 — submit one episode** (the `up` printout's one-liner, with `--row 1`:
the taskbank the bring-up built from your corpus — the printout's taskbank
line says how many rows yours produced; the synthetic corpus makes
six rows, numbered 0–5, sorted by case, timestep and prompt id, and **row 2**
is the transcript shown above; rows 0 and 4 are the two precedent prompts of
"Decisions" below, and rows 1 and 5 are the skill-card tasks the 0.6B floor
model is apt to loop on). The estate requires sign-in for read (a sandbox agent cannot
re-clone a case past its cutoff), so the generated config names the
read-scoped token by *variable* (`estate.clone_credential_env`) and
`submit` presents its value. Since library 0.1.7 — the version inside this
checkout's `gsj-polar` image — `submit` reads that value from the `.env`
beside its config when the variable is not exported, so the run's `.env`
is mounted read-only beside `/estate/rollout.yaml` and nothing is sourced
or exported; the token never reaches a trace:

```bash
docker run --rm --network gsj-demo-net \
  -v "$PWD/work/estate:/estate" -v "$PWD/work/runs/demo/.env:/estate/.env:ro" \
  -v "$PWD/corpus-synthetic:/corpus" -e GSJ_PINS_PATH=/estate/pins.gsj.json \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.7 \
  gsj-rollout submit --config /estate/rollout.yaml \
    --from-bank /corpus/taskbank.parquet --row 1
```

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
  ([the library's ADR-0025](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/decisions/ADR-0025-length-termination-surfaced-not-screened.md))
  — and whether to train on it is the trainer's call.

`export` is a projection of the archived body — the trace fields keyed by
name (counts, boundaries, gate results, reconstruction stats, page census,
per-turn calls) with the giant token/mask/logprob arrays **referenced, not
repeated** (`--arrays` embeds them; they are ~95% of the body's bytes and
the archive already holds them verbatim).

Neither view adds anything: everything both show comes from the one
archived JSON the receiver wrote. The archive is the truth; these are views.

## Decisions

The estate's agent has two retrieval tools. `mcp_gsj_search_case` searches
*this* case's pages and is scoped by the episode's cutoff.
`mcp_gsj_search_decisions` searches **court decisions** — precedent, the
same for every case, not cutoff-scoped. The worked example brings thirty
of them:

```
./synthetic/make_corpus.py        # writes corpus-synthetic/ AND corpus-synthetic-decisions/
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

**How the estate gets them.** No fourth input: the drop sits **beside**
the corpus as `<corpus>-decisions/`, and `./bootstrap.py up` finds it and
passes it to the library's bring-up as `--decisions-dir`. It is mounted
read-only into the retrieval service, which embeds it as its own
collection — the review the bring-up prints before the embed names your
drop, and `./bootstrap.py status` prints it afterwards. Beside, not
inside: the corpus contract has no `decisions/` entry yet, so `validate`
would refuse one (`bootstrap.py` says so with the `mv` if you try). Bring
your own by putting rii-dok v1 files there instead; with no drop at all,
the service serves its thirty synthetic stand-ins and the tool still
answers.

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
embeds 317 pieces in about 5 seconds inside the container; the store on
disk grows to 1.8 MB, and `work/` after two episodes is 10 MB. It costs
`up` nothing you would notice: the whole from-nothing run below, decisions
included, was **80 s**. For comparison, the real corpus the surface was
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
non-Qwen model whose pins never got derived because the endpoint was down
at `up` time (the bootstrap derives them from the endpoint's own template
render; re-run `./bootstrap.py up` with the endpoint live, and the
preflight's `tokenizer tail` row verifies before an episode is spent).

## Bring your own model

The estate does not require Qwen. When `inference.model` is not the
reference, `up` derives the tokenizer-bound pins from your endpoint's own
template render — the G6 tail and the end-of-turn id, over vLLM's
`/tokenize` + `/detokenize` — and names, out loud, what it cannot derive
(G4's byte hashes; your sampling defaults). The preflight then verifies
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

## Bring your own corpus

The corpus is a directory tree in
[the contract's shape](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md).
The synthetic corpus is the worked example — `./synthetic/make_corpus.py`
writes exactly this (and the decisions drop beside it, next section):

```
corpus-synthetic-decisions/      # the thirty decisions, jb-<doknr>.xml — BESIDE the corpus ("Decisions" below)
corpus-synthetic/
├── corpus.yaml                  # names the corpus, the git identity, the sandbox image
├── AGENTS.md                    # the agent's standing instructions (G2's pin derives from it)
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
create.) After `up`, two derived files appear beside your tree:
`taskbank.parquet` — the tasks, one row per prompt — and
`corpus.lock.json`.

That shape, with your documents in the pages, is all `bootstrap.py up`
needs. `validate` names every rule your tree breaks before anything runs.

The synthetic corpus is also the demo's proof: the 1998 easement deed
exists only on `case_orchard`'s page 4, so an episode at timestep 2
*cannot* cite it and an episode at timestep 4 *must* — the temporal cutoff,
observable in one fact (and in every `show` transcript's page lines).
