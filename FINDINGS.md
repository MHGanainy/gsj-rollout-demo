# FINDINGS — the demo repo's register

The external F-series continues here. F-01–F-53 — the trainer-side
consumer record — live in
[gsj-harness-rollout-server-examples/FINDINGS.md](https://github.com/MHGanainy/gsj-harness-rollout-server-examples/blob/main/FINDINGS.md);
this file carries the demo's rows, F-54 onward — F-54–F-68 minted at
library CP-36 (the first from-nothing stranger test — the library's
`docs/reports/CP-36.md` is where each row's full story lives; F-54's
durable half is still open as library wishlist row 40), F-69 at
library CP-40 (the audit's orphan pass). **The F-series is ONE register across both consumer
repos: a new row, minted from either file, takes the next id after the
highest anywhere. Next fresh id: F-70.** Severity vocabulary here is
CP-36's: blocking / costly / cosmetic / wrong shape, pass-tagged.
`library-side?` marks the half a demo commit cannot cure.

**[library CP-43 — 2026-08-24] The audit's demo-side remainder closed**
in this repo's front-door sitting (the library's `docs/reports/CP-43.md`
is the record): W6 — `bootstrap.py` now empties G4's two hashes for ANY
non-reference model, derivation success or failure, so MODEL-SURFACE's
emptied-G4 claim is true unconditionally; W7 — the README draws the
corpus *source* tree as it is (`timestep-<T>/pages/page_NNNN.md`) and
names `md/` as the generated repo-side layout; W9's demo half — the
per-episode band now matches its own CP-36 measurements (~20–40 s);
C9 — `config.yaml.example` no longer says the eot default "silently
stands" (the bootstrap is loud about it); C10 — MODEL-SURFACE's
chat-template row now NAMES the four template-derived rows and excludes
the tool-parser and context-window rows (naming, not class-counting —
the context-window row is [endpoint]-classed on vLLM too, so "the four
[endpoint] rows" would re-embed the off-by-one); C11 — the generated
`pins.gsj.json` now carries THIS estate's `host`/`walk_status` and G1/G2
provenance instead of the reference H200's, and its `derived_at` records
what the run derived, carried, emptied, or FAILED to derive (the
failure-path artifact no longer claims endpoint-derived G6); M2 — the phantom
`healthcheck.sh` cite replaced with a self-contained description; and
S4's four demo texts — `bootstrap.py`'s eot docstring (the render-side
closer, not the engine's stop id — CP-38's measurement), `read.py`'s G6
cure (pins derive automatically at `up`, not a manual re-pin),
`preflight.py`'s "(Qwen3)" tail label, MODEL-SURFACE's one-estate
opener. No run pass, no new row; **next fresh id stays F-70**.

| # | severity | finding | library-side? | status |
| --- | --- | --- | --- | --- |
| F-54 | **blocking (ARM hosts)** [pass 1, honest path] | `gsj-mcp-service:0.3.0` and `gsj-pi-harness:pi0.83.0-3` publish `linux/amd64` only (`gsj-polar` is multi-arch — the estate is asymmetric); an ARM docker REFUSES a manifest list with no matching platform rather than emulating, so `up` died at the mcp pull and, cured, again at the sandbox pull. The sandbox message misdiagnosed ("cannot reach ghcr.io"). What a stranger does: a docker-literate one reconstructs `docker pull --platform linux/amd64`; anyone else stops dead on the demo's headline promise | **yes** — the durable cure is an operator/publishing op: arm64 variants + a multi-arch index under the SAME pinned tags (provenance-sensitive; library wishlist row 40) | demo half FIXED at `96f2329`: bootstrap `ensure_amd64_image` (on ARM, absent → pull amd64 explicitly and say so; measured working — the mcp embed ran 115 s under emulation, episodes unaffected) + README ARM paragraph + truthful messages. Durable half **OPEN** as library wishlist row 40 |
| F-55 | costly [pass 1] | README disk claim ~3.5 GB vs 6.3–7.1 GB measured | no | FIXED at `96f2329`: measured numbers, the old number named as compressed |
| F-56 | cosmetic [pass 1] | A transient GHCR TLS timeout fails `up` one-shot; the message is actionable and the re-run recovered | no | RECORDED, deliberately unfixed — a retry would mask real registry errors |
| F-57 | costly [pass 1, desk] | "fill in the three values" names two; the third (`corpus:`) lived only in the example file | no | FIXED at `96f2329` |
| F-58 | costly [pass 1, desk] | The host-local-endpoint rewrite (`host.docker.internal`) was absent from the README while its "no host ports" framing pointed the reader at the wrong worry | no | FIXED at `96f2329` |
| F-59 | cosmetic [pass 1, desk] | "Everything … lives under `work/`" vs the taskbank + lock written beside the corpus | no | FIXED at `96f2329` (the exception stated with its reason) |
| F-60 | costly [pass 1, desk] | The reference serve argv was nowhere; the desk-reader budgeted "30–60 minutes of vLLM wrangling" and predicted an issue asking for it | no | FIXED at `96f2329`: the argv block, with the two load-bearing flags (symmetric template, pinned generation config) called out as such |
| F-61 | cosmetic [pass 1, desk] | estate / Polar / pins / qualified undefined at first use; "five services" ambiguous against five containers | no | FIXED at `96f2329` (glossary block; the fix's own first draft re-embedded the ambiguity and was repaired pre-commit to "one published image, run here as three of those containers") |
| F-62 | cosmetic [pass 1, desk] | No row count for "row 0"; thinking levels unlisted | no | FIXED at `96f2329` |
| F-63 | costly [pass 3, both transcript readers] | `status COMPLETED` + `accepted` misread as task success; the outcome lived in a footer parenthetical ("correct design stance, wrong font size") | no | FIXED at `96f2329`: `show` header `deliverable` line ("acceptance checks provenance, not task success"); export `deliverable` object |
| F-64 | costly [pass 3, export reader] | `arrays.where` was an absolute path from this host in ad-hoc notation, with no integrity check | no | FIXED at `96f2329`: `archive.file`, `archive.sha256` (verified matching the body), `where` keyed to `archive.file`; made disposition-aware for quarantined bodies pre-commit |
| F-65 | costly [pass 3, export reader] | Span half-openness, mask polarity, and logprob alignment were recoverable only by arithmetic | no | FIXED at `96f2329`: the `conventions` block (each claim verified against a real body before being written down) |
| F-66 | cosmetic [pass 2/3] | The deliverable footer's "The skill asks for out/&lt;task_id&gt;.md" rendered on free-form rows that asked no such thing (`case_orchard@t2`) | no | FIXED at `96f2329`: conditional on `prompt_source`, with a third branch for bodies that name none |
| F-67 | wrong shape [pass 5] | The injected "missing prompts.yaml" is not an invalid corpus: contract §4 blesses it (`PASS 4 pages, 0 prompts`; the timestep contributes no tasks — the honest 0-count in the row is the guard) | no | NO FIX — not a defect; recorded so it is not re-filed as a bug |
| F-68 | cosmetic [pass 5] | read.py messages cited a README section by a nonexistent name | no | FIXED at `96f2329` |
| F-69 | costly, latent [library CP-40, audit O4 — minted by the three-repo audit, not by a run pass] | The estate depends on anonymous Forgejo read, and no document said so: compose sets `DISABLE_REGISTRATION` but no sign-in requirement, and the bootstrap's per-episode clone URL (`bootstrap.py` `clone_url_for`) embeds no credentials — anonymous read is load-bearing. Nothing is published to host ports, but the sandboxed agent lives on the same compose network by construction (it clones from it): a URL-guessing agent can re-clone `http://forgejo:3000/gsj-staging/<case_id>.git` and read past its timestep cutoff over the network. The in-sandbox git channel is closed (library CP-11: `--depth 1`, no remote, no reflog); this is the network channel — library gap row 2's estate residual, inherited unchanged | **yes** — the cure is estate posture (credentialed clone URLs or sandbox egress policy — library gap row 2); flipping sign-in on alone would break the credential-less clone flow, so the fix is a design, not a flag | OPEN — decided at library CP-40: production-prep, not permanently accepted. Acceptable for a demo whose corpus is synthetic; NOT acceptable for a run someone intends to train from — the first production bring-up owns it (library charter §7 row 2's [CP-40] note is the master record) |
