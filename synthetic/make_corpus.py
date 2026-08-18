#!/usr/bin/env python3
"""Generate the demo's synthetic corpus — the repo's own self-test and the
worked example a stranger copies.

    ./synthetic/make_corpus.py            # writes ./corpus-synthetic
    ./synthetic/make_corpus.py --out DIR

The tree it writes is contract-valid without edits (both splits, a
multi-timestep case, one skill-card prompt and free prompts) and the page
content is built so retrieval is meaningful and the cutoff observable:
the 1998 easement deed exists ONLY on case_orchard's page 4 — an episode
at timestep 2 must not see it (its checkout physically lacks the page and
`search_case` is cutoff-filtered), an episode at timestep 4 must find it.

AGENTS.md is written byte-identical to estate/AGENTS.reference.md — that
text is what the reference system-prompt pin (G2) embeds, so a corpus that
keeps it needs no G2 re-derivation at all (the bootstrap re-derives it
anyway, from whatever AGENTS.md your corpus carries).
"""

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

CORPUS_YAML = """\
name: gsj-demo-synthetic
owner: gsj-staging                    # the estate the bootstrap stands up
forgejo:
  base_url: http://forgejo:3000       # in-network DNS — the bootstrap's Forgejo
mcp:
  url_base: http://mcp:8790           # in-network DNS — the bootstrap's retrieval
git:                                  # fixed identity => deterministic commit SHAs
  name: gsj-demo-fixtures
  email: fixtures@gsj.invalid
  date: "2026-01-01T00:00:00 +0000"
sandbox_image: ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3
"""

SKILL_BRIEF = """\
# Case brief

Produce a structured brief of the case file as it stands at this cutoff:

1. **Parties** — who is against whom, and in what capacity.
2. **The dispute** — one paragraph, in your own words.
3. **Evidence by page** — every substantive fact, cited as (page:N).
4. **Open questions** — what the file does not yet establish.

Use only the case file in this checkout and the retrieval tools. Cite a
page for every fact. Write the brief to `out/<task_id>.md`.
"""

# --- case_orchard (train): a boundary dispute, 4 pages, growing file ---------

ORCHARD_PAGES = {
    1: """\
# Alba Orchards e.K. v. Marrow Farms GmbH — case file

## Page 1 — Parties and the disputed strip

Alba Orchards e.K. (claimant) operates the fruit plantation on parcel 114/2
of the Grevenau land registry. Marrow Farms GmbH (respondent) farms the
adjoining parcel 114/3 to the east. In dispute is a strip of roughly 3.4
metres by 180 metres along the shared boundary, currently on the western
side of an old wire fence, used by the claimant for an irrigation ditch
and an access track.

The claimant seeks a declaration that the strip belongs to parcel 114/2
and an order that the respondent cease crossing it with machinery.
""",
    2: """\
## Page 2 — The 2019 fence survey

A survey commissioned jointly in March 2019 and carried out by the public
surveyor Lena Ortiz located the registered boundary between parcels 114/2
and 114/3. Ortiz's plan places the old wire fence 3.2 metres WEST of the
registered boundary line along the full length of the disputed strip; the
strip between fence and registered line is therefore, by the registry
geometry alone, part of parcel 114/3 — the respondent's parcel.

The claimant does not contest the measurement. It argues instead that the
fence has stood since at least 1996 and that the strip's use has been
exclusively its own since then.
""",
    3: """\
## Page 3 — Witness statement, Tomas Rehn

Tomas Rehn, who has farmed the parcel north of both parties since 1991,
states: the wire fence stood in its present line when he took over in
1991; Alba Orchards (then under its founder) dug the irrigation ditch on
the western side "in the mid-nineties"; Marrow Farms' machinery used a
gate at the southern end of the fence "a few times a year, always with a
word to the Albas first" until around 2018, after which crossings became
frequent and unannounced.
""",
    4: """\
## Page 4 — The 1998 easement deed

A certified registry extract, obtained late in the proceedings, records
easement deed no. 98-4417, registered 11 August 1998 against parcel
114/2: a right of way in favour of the respective owner of parcel 114/3,
"for agricultural passage to the Greven creek across the ditch track",
i.e. across exactly the disputed strip. The deed was granted by Alba
Orchards' founder in settlement of an earlier drainage dispute.

The easement changes the posture of the case: even if the claimant were
to establish ownership of the strip, the recorded right of way would
survive it.
""",
}

ORCHARD_PROMPTS_T2 = """\
prompts:
  - {id: "free:boundary-evidence", source: free, text: "What evidence about the true boundary line between the parcels is in the case file so far, and which way does each piece point? Cite pages as (page:N)."}
"""

ORCHARD_PROMPTS_T4 = """\
prompts:
  - {id: "skill:brief", source: skill, name: brief}
  - {id: "free:easement", source: free, text: "Does any recorded easement or right of way affect the disputed strip? Name the registry number and cite the page."}
"""

# --- case_mill (eval): a lease arrears dispute, 3 pages ----------------------

MILL_PAGES = {
    1: """\
# Greven Mill Cooperative v. B. Hartl — case file

## Page 1 — Parties and the lease

The Greven Mill Cooperative (claimant) owns the historic water mill on the
Greven creek and lets its turbine hall to commercial tenants. Bertha Hartl
(respondent) has rented the hall since 2021 for a small-batch flour
business under a five-year lease at 1,400 euros per month.

The cooperative claims six months of arrears (8,400 euros) and seeks
termination. Hartl admits withholding rent and pleads a defect: recurring
flooding of the hall's storage annex.
""",
    2: """\
## Page 2 — The flooding record

Hartl's log, with photographs, records water ingress into the storage
annex on nine dates between October 2024 and March 2026, each within two
days of the creek's high-water gauge exceeding 1.8 metres. Two deliveries
of flour (invoiced at 1,150 and 730 euros) were written off. The
cooperative's caretaker countersigned four of the nine entries.
""",
    3: """\
## Page 3 — The cooperative's maintenance file

The maintenance file shows the annex's flood gate was reported jammed in
September 2024 by the caretaker, budgeted for repair in the 2025 plan,
and not repaired. An internal note of February 2025 reads: "defer gate
works until the lease question with H. is resolved."
""",
}

MILL_PROMPTS_T3 = """\
prompts:
  - {id: "skill:brief", source: skill, name: brief}
"""


def write_case(root: Path, split: str, case_id: str, pages: dict,
               prompts_by_timestep: dict) -> None:
    case = root / split / "cases" / case_id
    for t, prompts in prompts_by_timestep.items():
        tdir = case / f"timestep-{t}" / "pages"
        tdir.mkdir(parents=True)
        for n in range(1, t + 1):
            # byte-identical across timesteps by construction (contract rule 3)
            (tdir / f"page_{n:04d}.md").write_text(pages[n])
        (case / f"timestep-{t}" / "prompts.yaml").write_text(prompts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO / "corpus-synthetic"))
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing tree")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        if not args.force:
            print(f"{out} already exists — pass --force to regenerate "
                  "(the tree is deterministic; regeneration is byte-identical)")
            return 1
        shutil.rmtree(out)

    out.mkdir(parents=True)
    (out / "corpus.yaml").write_text(CORPUS_YAML)
    shutil.copy(REPO / "estate" / "AGENTS.reference.md", out / "AGENTS.md")
    (out / "skills" / "brief").mkdir(parents=True)
    (out / "skills" / "brief" / "SKILL.md").write_text(SKILL_BRIEF)

    write_case(out, "train", "case_orchard", ORCHARD_PAGES,
               {2: ORCHARD_PROMPTS_T2, 4: ORCHARD_PROMPTS_T4})
    write_case(out, "eval", "case_mill", MILL_PAGES,
               {3: MILL_PROMPTS_T3})

    print(f"synthetic corpus written to {out}")
    print("  train/case_orchard: timesteps 2 and 4 — the 1998 easement deed "
          "(registry no. 98-4417) exists only on page 4; an episode at "
          "timestep 2 cannot see it, an episode at timestep 4 must find it")
    print("  eval/case_mill:     timestep 3, skill-card prompt")
    print("next: point config.yaml's `corpus:` here and run ./bootstrap.py up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
