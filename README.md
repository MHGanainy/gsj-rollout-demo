# gsj-rollout-demo

From **your documents** to **a running rollout estate** — one command.

This is the demo for [gsj-harness-rollout-server](https://github.com/MHGanainy/gsj-harness-rollout-server):
the rollout server that takes a task `(case, timestep, prompt)`, runs an
agent in an isolated sandbox with temporally-scoped retrieval, and emits a
training-ready trajectory. The
[`-examples` repo](https://github.com/MHGanainy/gsj-harness-rollout-server-examples)
shows a **trainer** how to train against an estate that already exists.
*This* repo shows someone who has **documents, a config, and an inference
endpoint** how to get an estate at all.

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

## What you get

A five-service estate on the private `gsj-demo-net` docker network (no host
ports — from outside, join the network): Forgejo serving your cases as
git repos with one branch per timestep, cutoff-filtered semantic retrieval
over exactly those repos, and Polar ready to run sandboxed episodes against
**your** endpoint — every trace validated on arrival against pins derived
from **your** corpus. Traces, secrets, session logs, and every generated
file live under `work/`, stated by the final printout.

The synthetic corpus is also the demo's proof: the 1998 easement deed
exists only on `case_orchard`'s page 4, so an episode at timestep 2
*cannot* cite it and an episode at timestep 4 *must* — the temporal cutoff,
observable in one fact.

Submitting episodes and reading the resulting trajectories is the next
walkthrough (CP-35); `up`'s final printout already shows the one-liner.
