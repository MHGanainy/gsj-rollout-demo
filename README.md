# gsj-rollout-demo

From **your documents** to **a running rollout estate** — one command.
From an episode to **a trajectory you can actually read** — one more.

This is the demo for [gsj-harness-rollout-server](https://github.com/MHGanainy/gsj-harness-rollout-server):
the rollout server that takes a task `(case, timestep, prompt)`, runs an
agent in an isolated sandbox with temporally-scoped retrieval, and emits a
training-ready trajectory. The
[`-examples` repo](https://github.com/MHGanainy/gsj-harness-rollout-server-examples)
shows a **trainer** how to train against an estate that already exists.
*This* repo shows someone who has **documents, a config, and an inference
endpoint** how to get an estate — and how to see what the agent did in it.

## The three inputs

A corpus in [the contract's shape](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md),
a `config.yaml` with your inference endpoint's URL and served-model name,
and that endpoint itself — that is everything; the bootstrap derives the rest.

## Run it

```bash
# prerequisites: Docker (with compose v2), Python >= 3.12
pip install 'gsj-harness-rollout-server>=0.1.2'
git clone https://github.com/MHGanainy/gsj-rollout-demo && cd gsj-rollout-demo

./synthetic/make_corpus.py        # the worked example — or bring your corpus
cp config.yaml.example config.yaml   # then fill in the three values

./bootstrap.py validate           # check the corpus before anything runs
./bootstrap.py up                 # the estate
```

`up` runs, in order: **validate** the corpus (and stop loudly if it fails —
nothing runs against an invalid tree) → stand up **Forgejo** → **scaffold**
the corpus into per-case repos → stand up the **MCP retrieval service** and
**ingest** → build the **taskbank** → **verify** everything round-trip →
derive **this estate's pins** → stand up **Polar** (rollout server, gateway,
receiver — [as one published container](docs/ADR-0001-polar-as-a-container.md))
→ print what is running, where, and how to stop it.

Running `up` twice is safe — every step detects existing state and says so.
`./bootstrap.py down` stops the estate; `down --wipe` resets it.

The estate is five services on the private `gsj-demo-net` docker network
(**no host ports** — to talk to it, join the network, as every command below
does). Everything it generates or archives lives under `work/`.

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
id) and names each mismatch **with its consequence** — so you learn your
tokenizer differs from a preflight row, not from a quarantined episode. What
an API cannot see (your sampling defaults) it says so, once, out loud.

**1 — submit one episode** (the `up` printout's one-liner; row 0 of the
taskbank the bootstrap built from your corpus):

```bash
docker run --rm --network gsj-demo-net \
  -v "$PWD/work/estate:/estate" -v "$PWD/corpus-synthetic:/corpus" \
  -e GSJ_PINS_PATH=/estate/pins.gsj.json \
  ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.2 \
  gsj-rollout submit --config /estate/rollout.yaml \
    --from-bank /corpus/taskbank.parquet --row 0
```

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

`show` renders: the task triple and the checkout (branch, **the pages
visible at this cutoff**), each assistant turn, each tool call and its
result, and the deliverable if one was written. Three things it is careful
about, because they are the point:

- **Retrieval results show their pages.** Every `mcp_gsj_search_case` hit
  prints `page N`, and the transcript checks them against the episode's
  timestep on the spot — `all <= timestep 12 (the cutoff holds)`. The
  temporal cutoff is observable per-episode, not asserted.
- **Thinking is rendered distinguishably** (the `|`-prefixed block inside
  the turn). The archive stores reasoning only inside the token arrays, so
  `show` decodes them — that needs `pip install tokenizers` and the served
  model's tokenizer; without it the transcript says, per turn, what it
  could not render rather than showing you a wall of half-truth.
- **Truncation is labelled where you will see it.** A `finish_reason:
  length` episode says so in the header AND at the point the text stops.
  It *qualified* — qualification checks provenance, not task success
  (ADR-0025) — and whether to train on it is the trainer's call.

`export` is a projection of the archived body — the trace fields keyed by
name (counts, boundaries, gate results, reconstruction stats, page census,
per-turn calls) with the giant token/mask/logprob arrays **referenced, not
repeated** (`--arrays` embeds them; they are ~95% of the body's bytes and
the archive already holds them verbatim).

Neither view adds anything: everything both show comes from the one
archived JSON the receiver wrote. The archive is the truth; these are views.

## Both modes

The estate runs thinking-off by default. To run thinking-on:

```yaml
# config.yaml
thinking: medium        # the conventional ON; a bare `on` is a YAML boolean
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
non-Qwen tokenizer (the preflight's `tokenizer tail` row warns about the
second before it costs an episode).

## Expectations, measured (reference stack, the two-case synthetic corpus)

- `up`, cold on an empty docker host: **~2.5 min** (mostly image pulls +
  first MCP embed); warm re-run: **~10 s**. Disk: **~3.5 GB** of images.
- One episode end-to-end: **25–50 s** against a host-local 0.6B engine.
- Qualification: expect near-total on the reference stack (the library's
  CP-32 measured 72/72; this demo's smoke 1/1). An empty quarantine is
  normal, not suspicious.
- **A small model hitting the generation cap is visible, not broken.** The
  0.6B reference model regularly ends brief-shaped tasks at the 8,192-token
  cap — `submit` prints the ADR-0025 `length-terminated:` line and `show`
  labels the truncation twice. Expect degenerate episodes too (the smoke's
  first accepted episode read `AGENTS.md` seventy times and wrote nothing —
  the transcript collapses the repetition and says NO deliverable was
  written). A 0.6B agent is the demo's floor, honestly rendered, not its
  recommendation.

## Bring your own corpus

The synthetic corpus is the worked example of
[the contract](https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md):
run `./synthetic/make_corpus.py` and read the tree it writes — `corpus.yaml`,
`AGENTS.md`, `skills/*/SKILL.md`, and per-case `md/page_NNNN.md` pages under
`train/` and `eval/` — that shape, with your documents in the pages, is all
`bootstrap.py up` needs. `validate` names every rule your tree breaks
before anything runs.

The synthetic corpus is also the demo's proof: the 1998 easement deed
exists only on `case_orchard`'s page 4, so an episode at timestep 2
*cannot* cite it and an episode at timestep 4 *must* — the temporal cutoff,
observable in one fact (and in every `show` transcript's page lines).
