# What changes when the model changes

Every packaged pin — and, unless labelled otherwise, every measured
number in the README — comes from the reference estate: vLLM serving
`Qwen/Qwen3-0.6B` under the symmetric chat template, pinned sampling.
(One other family has measured numbers too: Llama-3.1-8B-Instruct, run
and accepted at CP-38, labelled where its figures appear here and in the
README — "the second family, measured" below is its record.) Point
`config.yaml` at your own model and a specific, finite set of things
move. This page walks all of them: what
each one is, who derives it now, and what breaks when it is wrong. It is
written for the moment *before* you spend an episode learning any of it.

How each value is derived — the four classes used below:

- **[endpoint]** — derivable from your endpoint's API. The bootstrap and
  the preflight do these for you, automatically.
- **[snapshot]** — derivable from a local copy of the model's tokenizer
  files. A recipe below; no API exposes these.
- **[estate]** — knowable only on the serving host (the serve argv).
- **[you]** — a decision no tool can make or check.

## The table

| what | class | who derives it | if it is wrong |
|---|---|---|---|
| served model name (`inference.model`) | [you] | you; preflight's `model` row verifies byte-for-byte (any name works, slashed or not — the library prepends its own provider label internally) | every episode dies as ADM1/ADM4 "no completions" |
| the chat template itself | [estate] | your serve argv (`--chat-template`, or the snapshot's embedded one) — nothing here can choose it *for* you; the four template-derived rows below (prefix-extension, the G6 tail, `end_of_turn_token_id`, `generation_prompt_glue_ids`) are derived *from* it — the tool-parser and context-window rows are not | the four template-derived rows just named |
| the tool-call parser | [estate] | your serve argv — it is family-bound (vLLM: `--tool-call-parser hermes` for Qwen, `llama3_json` for Llama-3.1; vLLM documents one per family); preflight's `tool parser` row probes it, and a real request whose reply carries a STRUCTURED `tool_call` (the parser half of a tool round trip; the answer half — whether the model *uses* the result — is temperament, see "the second family, measured") is the strong verify | the model's calls stay text: episodes run tool-poor or tool-free and still come back green — the tool-FREE case has a purpose-built gate (`H41:roster_offered_zero_tool_calls`, policy-off by default); the tool-POOR case no gate can see |
| prefix-extension property | [endpoint] | preflight's `template` row | multi-turn episodes quarantine at `G7:chains_total_ne_1` — after each is spent (see below) |
| G6 tail (`g6_expected_tail`, `…_ids`) | [endpoint] | bootstrap, at `up`, when `inference.model` is not the reference | every episode quarantined at `G6:prompt_suffix_ne_tail_ids` |
| `end_of_turn_token_id` | [endpoint] | bootstrap, at `up` (into the generated rollout.yaml); preflight's `end-of-turn id` row verifies | reconstruction mis-splits every multi-turn episode |
| `generation_prompt_glue_ids` | [endpoint], only when needed | preflight's `template` row prints the candidate list on a constant divergence; you set it in config.yaml | only relevant when the template rewrites history by a constant span |
| G4 hashes (`tokenizer_hash`, `chat_template_hash`) | [snapshot] | nobody, over an API — the bootstrap writes them **empty** for any non-reference model, derivation success or failure (the reference's values would be a lie for your model either way); recipe below | nothing, at the receiver, today: no trace-side gate reads them. What you lose is the estate-side drift walk they exist for |
| context window | [endpoint] on vLLM, else [you] | preflight's `context window` row; `context_window` in config.yaml | mid-episode 400s once the real window fills |
| sampling defaults | [you] / [estate] | nobody — pi sends NO sampling parameters, and no API states server defaults | you train on whatever distribution the server happens to default to (unpinned vLLM: T=1.0) |
| `thinking` mode | [you] | config.yaml; pins re-derive per mode at `up` | see "thinking on a family without the mode" below |
| G2 system-prompt hash | model-independent (measured) | bootstrap, from your corpus's AGENTS.md | — (the reference capture contains no model-identifying byte; a different *pi* version would move it, a different model does not — verified live at CP-38: the hash reproduced on an accepted Llama-3.1 episode) |
| G1 skill cards · G3 tool roster · G7 settings | model-independent | your corpus's cards; pi's fixed 11-tool roster; a harness constant | — |
| the README's measured timings/quality | reference-stack-bound | — | your numbers differ; the pipeline's claims don't |

## The chat template decides everything below it

The served template — the file in your serve argv, or the snapshot's
embedded `chat_template` if you pass none — is the artifact the four
template-derived rows are derived *from*. Two consequences worth saying
plainly:

- **"Same model" does not mean "same template."** Serving the reference
  Qwen3-0.6B *without* the README's `--chat-template qwen3_training.jinja`
  is a different estate: the tail pins still match, but history re-renders
  strip the think block and the `template` row FAILs. The serve argv is
  provenance, not decoration.
- **Mirrors of the same model ship different templates.** Measured while
  building this page: one popular Llama-3.1-8B-Instruct mirror ships a
  simplified template that ignores `add_generation_prompt` entirely and
  never renders tool calls; the faithful mirror carries Meta's full one.
  The derivation here probes what your endpoint *actually serves*, which
  is the only artifact that matters — but if you downloaded a snapshot to
  serve, know that the repo you pulled decides your template.

## The prefix-extension property

Polar reconstructs a multi-turn episode as ONE token chain only if each
turn's prompt render *strictly extends* the previous one — history must
re-render byte-identically. A template that rewrites history (Qwen3's
stock template strips `<think>` blocks from past turns) splits the
reconstruction into disconnected chains; the receiver catches that —
every multi-turn episode is quarantined at `G7:chains_total_ne_1` — but
only **after** each episode is spent, with the cross-turn context
already lost.

The preflight's `template` row measures it over `/tokenize` (a two-turn
render pair) **before** any episode is spent. Three outcomes:

1. **Extends** — nothing to do. Measured here: the reference stack
   (thinking off and on), and Llama-3.1's official template — the
   first non-Qwen family measured, its stock template needs no
   symmetric variant.
2. **Rewrites by a constant span** — the row prints the lost ids; set
   `generation_prompt_glue_ids: [those ids]` in config.yaml and re-run
   `up`. The library re-inserts them at reconstruction (its ADR-0007
   glue stitch — the mechanism the reference estate used before the
   symmetric template made it unnecessary; Qwen3's constant span is
   `[151667, 271, 151668, 271]`, the empty think block).
3. **Rewrites, not constant** — this model needs a symmetric template
   variant before episodes are worth spending (TRL ships one for Qwen3;
   other families may need their own). The row says so.

What the probe measures turned out to be the whole chain-GROUPING
condition (`chains_total`) — measured at CP-38 on the first live
non-Qwen episode. (One further thing a complete merge needs is the
derived `end_of_turn_token_id` occurring in every re-render — the
end-of-turn section below owns that, and a wrong id fails closed at
`G7:chains_truncated`, never silently.)
Reconstruction compares each request's prompt render against the
*previous request's prompt render* (canonical-vs-canonical; the sampled
bytes never enter the prefix comparison), so renders-extend-renders IS
the property. Where the sampled bytes and the template's re-render of a
turn disagree, the merged stream keeps both, correctly labelled: the
model's actual sampled tokens ride at loss-mask 1, the template's
canonical close and the interstitial ride at mask 0. Measured
concretely: every Llama-3.1 tool-call turn *samples* `<|eom_id|>` as
its stop while the template re-renders the turn closed with
`<|eot_id|>` — the stream carries the sampled `<|eom_id|>` at mask 1
followed by the canonical `<|eot_id|>` at mask 0, and `chains_total`
stayed 1. (An earlier revision of this page claimed
sampled-vs-rerendered identity was an extra condition only an episode
could confirm — measured false; that claim is withdrawn.)

No `/tokenize` on your engine? The same probe runs from a local snapshot
of the model you serve (needs `pip install transformers`):

```python
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("<snapshot dir or hf id>")
h1 = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
h2 = h1 + [{"role": "assistant", "content": "A"},
           {"role": "user", "content": "U2"}]
def ids(msgs):  # add your serve-time chat_template/kwargs if you pin any
    text = tok.apply_chat_template(msgs, tokenize=False,
                                   add_generation_prompt=True)
    return tok(text, add_special_tokens=False)["input_ids"]
p1, p2 = ids(h1), ids(h2)
assert p2[:len(p1)] == p1, f"rewrites history at {next(k for k in range(min(len(p1),len(p2))) if p1[k]!=p2[k])}"
```

One caveat that bit during this page's own measurements: the template in
a *mirror's* snapshot may not be the template your engine serves — probe
the snapshot you actually point the engine at.

## G6 on your model: what the gate still means

G6 compares every assistant-turn opening of the token stream against the
pinned tail. What that *asserts* depends on the family:

- **Qwen3, thinking off**: the tail is the 41-byte empty think block —
  the gate proves thinking was OFF at every position the template could
  have shown it.
- **Qwen3, thinking on**: the tail is the bare `<|im_start|>assistant\n`
  — template integrity plus the assertion that no opening carries the
  off-mode signature.
- **Any other family**: the tail is whatever your template appends for a
  new assistant turn (Llama-3.1: `<|start_header_id|>assistant<|end_header_id|>\n\n`),
  and the gate asserts **template integrity only** — every turn opened
  exactly as the template says turns open. The thinking meaning is
  Qwen-family-specific and does not transfer.

Edge case, measured: a template that ignores `add_generation_prompt` has
*no* generation-prompt suffix, so no G6 tail exists for it. The
derivation refuses to pin one (an empty pinned tail is treated as
fail-closed — every turn would offend) and says so; episodes then
quarantine against the reference tail, loudly.

## `end_of_turn_token_id`

The builder uses this id to locate, inside each next prompt's render,
where the previous assistant turn's canonical close ends and the
interstitial (tool results, chat glue) begins. The bootstrap derives it
from your template's own render: the **first non-whitespace token the
template emits after assistant content** (Qwen3: `<|im_end|>` = 151645;
Llama-3.1: `<|eot_id|>` = 128009). What that heuristic derives is the
RENDER-side closer — and the render-side closer is the value
reconstruction needs, measured at CP-38 on the first family where the
render and the stop split: Llama-3.1 under tools *stops* tool-call
turns at `<|eom_id|>` (128008, per Meta's ipython protocol) while its
template re-renders those turns closed with `<|eot_id|>` (128009). The
derived 128009 is correct anyway — the id is matched against the
*render*, not against the engine's stop token, and the sampled
`<|eom_id|>` stays in the stream as trainable data (the
prefix-extension section above shows the resulting mask geometry).
For anything exotic (a template that closes turns with plain text, an
engine with custom stop ids), cross-check `generation_config.json`'s
`eos_token_id` (often a *list* — Llama-3.1 ships `[128001, 128008,
128009]`, and the value you want is the one your template emits to
close an assistant turn, NOT necessarily the one the engine stops on)
and set `end_of_turn_token_id` in config.yaml explicitly — the explicit
value always wins, and the preflight row tells you when it disagrees
with what the template says.

One warning for direct *library* consumers (the demo path is immune —
it always configures the derived id): the underlying builder's
fallback auto-detect, used only when `end_of_turn_token_id` is left
unconfigured, picks the last *sampled* token of the first stopped
completion. On a two-terminator family like Llama-3.1 that is the stop
token (`<|eom_id|>`), which never appears in the canonical render — so
every chain would truncate to its first turn. Neither failure is
silent: the library stamps `A15:end_of_turn_token_id_not_configured`
the moment the id is unconfigured, and a truncated reconstruction
quarantines at `G7:chains_truncated`.

No `/tokenize` on your engine? Derivation cannot run (it needs vLLM's
`/tokenize` + `/detokenize`), the builder falls back to the reference
default 151645, and the explicit config key is the cure. From a local
snapshot:

```python
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("<snapshot dir or hf id>")
tok.convert_tokens_to_ids("<your template's end-of-turn token>")
# e.g. "<|eot_id|>" -> 128009 on Llama-3.1
```

## G4's two hashes, from a local snapshot

No API exposes the *bytes* of `tokenizer.json` or of the served
template, so for a non-reference model the bootstrap leaves both
approved sets empty rather than carry the reference's values as a lie.
Nothing at the receiver reads them today — they exist for the
estate-side drift walk (is the engine still serving what the pins were
derived from?). If you want that walk, derive them from the snapshot
you serve:

```python
import hashlib, json
raw = open("tokenizer.json", "rb").read()                  # git blob oid
tokenizer_hash = hashlib.sha1(b"blob %d\x00" % len(raw) + raw).hexdigest()
# chat_template_hash: sha256 of the template STRING the engine renders
# with — the file you pass via --chat-template, or the embedded field:
tpl = open("your_template.jinja", "rb").read()             # if argv-pinned
# tpl = json.load(open("tokenizer_config.json"))["chat_template"].encode()
chat_template_hash = hashlib.sha256(tpl).hexdigest()
```

and put each into its list in `work/estate/pins.gsj.json` (they are
re-derived at every `up`, so keep your own record — or better, keep the
serve argv under version control and re-run this recipe when it moves).

## Thinking on a family without the mode

`thinking:` is pi's passthrough to a Qwen hybrid-reasoning feature: every
non-off level sends `enable_thinking: true` in the request's template
kwargs. On a template that never references that variable — measured on
both Llama-3.1 templates — the render is **byte-identical either way**: a
non-off level is a wire no-op, episodes run normally, and the derived
pins are the same in both modes (measured live at CP-38: against a
served Llama-3.1-8B endpoint the derivation's mode pair returned
byte-identical tails and end-of-turn ids). Two things still change, and both are
labels, not behavior: the archive stamps `.thinking-on.json`, and the
transcript reader looks for Qwen's `<think>` marker ids (a labelled
heuristic — it finds nothing on your model, so nothing renders as
thinking). Recommendation: leave `thinking: off` unless your family
actually has the mode; a stamp that claims a mode your model lacks is
a small lie in your provenance.

## The second family, measured (Llama-3.1-8B-Instruct, CP-38)

The first non-Qwen episode ran through this estate against
Llama-3.1-8B-Instruct (unsloth mirror — Meta's weights and Meta's full
embedded template) and was **accepted: `chains_total: 1`, eight
completions merged, zero findings**. What it taught that no probe
showed, kept here because each item is model-surface, not stack:

- **The serve legs that moved**: `--tool-call-parser llama3_json` (not
  hermes), no `--chat-template` flag (the snapshot's embedded template
  is Meta's full one — and the mirror decides it, see above), no
  reasoning-parser / thinking kwargs (Qwen legs), `--generation-config`
  pinned to the snapshot's own file (`temperature 0.6, top_p 0.9` — and
  note: **no top_k**).
- **A tool round trip has two halves.** The parser half (a structured
  `tool_call` comes back) is the half that protects your episodes —
  verify it before spending any. The answer half (the model *uses* the
  tool result) failed 4/4 healthcheck-style probes on this model — it
  answered with meta-commentary about its own call, or just called the
  tool again — while the episode collected the same day used its read
  results perfectly well under pi's multi-turn drive. Model temperament
  on a toy probe, not a stack failure; know which half a red probe is
  showing you.
- **Malformed sampled JSON ends episodes quietly.** The model's last
  turn emitted a `write` call with raw newlines inside its JSON
  strings (mixed in beside properly escaped `\n`); the parser (strict
  `json.loads`) fell back to plain text, pi
  read a text answer, and the episode ended with the real deliverable
  never written — while the turn-1 stub kept `deliverable: written:
  true`. Disposition says provenance, not success: read the transcript.
- **A green episode can be retrieval-free.** This one made 7 tool calls
  (file tools only, zero `mcp_gsj_*`) and was rightly accepted — the
  gates check provenance, and the temporal-cutoff machinery goes
  unexercised when the model never searches. If retrieval use matters
  to you, assert it on the export (`page_census`), not the disposition.
- **The exact-0.0 logprob rate is an estate property, not a constant.**
  Reference stack (0.6B Qwen, top_k 20 pinned): 6–14% of mask-1
  positions exactly 0.0, with a repetitive episode measured at 24.9%
  against the receiver's 0.25 allowance. This episode (8B Llama, no
  top_k in its generation config): **1.8%**. Model peakedness and the
  sampling policy's renormalization both move it; what transfers is
  only the lesson — measure yours before deciding what the LP6
  allowance means on your estate.

## What no probe can check

- **Sampling defaults** — pi sends none, so your server's generation
  defaults ARE the sampling policy, and no OpenAI-compatible API states
  them. Pin them in the serve argv (vLLM: `--generation-config`) and
  treat that argv as part of your estate's provenance.
- **Template-vs-training match** — a template can render, extend, and
  derive cleanly and still not be the format the model was trained on
  (a base model behind a chat template will run and produce garbage).
  The transcript reader is where you catch that, honestly rendered.
- **Quality** — the README's expectations section is measured on a 0.6B
  reference model, the demo's floor. Yours will differ; the pipeline's
  claims (cutoff enforcement, provenance gates, readable trajectories)
  are the part that transfers.
