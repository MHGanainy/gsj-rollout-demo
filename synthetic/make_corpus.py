#!/usr/bin/env python3
"""Generate the demo's synthetic corpus — the repo's own self-test and the
worked example a stranger copies.

    ./synthetic/make_corpus.py            # writes ./corpus-synthetic and
                                          #        ./corpus-synthetic-decisions
    ./synthetic/make_corpus.py --out DIR  # DIR and DIR-decisions

The tree it writes is contract-valid without edits (both splits, a
multi-timestep case, one skill-card prompt and free prompts) and the page
content is built so retrieval is meaningful and the cutoff observable:
the 1998 easement deed exists ONLY on case_orchard's page 4 — an episode
at timestep 2 must not see it (its checkout physically lacks the page and
`search_case` is cutoff-filtered), an episode at timestep 4 must find it.

Beside the corpus it writes a DECISIONS DROP (library CP-81): thirty
fictional court decisions in the rii-dok v1 XML the library's decisions
surface parses (docs/decisions-surface.md in the library repo — `<dokument>`,
a `doknr`, `<dl class="RspDL">` rows with `rd_N` anchors, `tenor`,
`gruende` …), written to BEAR ON these two cases: easements and rights of
way, the land register against a long-standing fence, prescriptive
possession, considerate exercise, commercial-lease termination for arrears,
rent reduction for flooding, a landlord's deferred repair. Made-up text,
structurally real: the service ingests the drop as Randnummern (level 2 of
the surface) and a search returns something RELEVANT to the cases. The
thirty are data — `synthetic/decisions.json` — and the XML is rendered here,
deterministically. The drop sits BESIDE the corpus (`<corpus>-decisions/`)
because the corpus contract admits no `decisions/` entry inside a corpus
yet (library wishlist row 73); `bootstrap.py up` finds it there and hands
it to the library's bring-up as `--decisions-dir`.

AGENTS.md is the reference AGENTS.md — the text the reference system-prompt
pin (G2) embeds, read out of the library's own packaged capture (library
>= 0.1.3; no demo-side copy since CP-61) — PLUS the decisions-citation
clause of the surface's §9.5 (`dec:<doknr>:rn:<N>`, the degradation rule
beside it). That clause moves G2 for this corpus, by design: the bootstrap
re-derives the pin from whatever AGENTS.md your corpus carries (library
CP-43's path), so the estate's receiver validates episodes against THIS
corpus's prompt, not the reference's.
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DECISIONS_JSON = HERE / "decisions.json"

CORPUS_YAML = """\
# The corpus's identity (docs/corpus-contract.md in the library repo).
# Since library CP-71 (wheel 0.1.6) a corpus is three fields: name, owner,
# git:. The git host, the retrieval URL and the sandbox image are the
# ESTATE's — the estate tool answers them (here: bootstrap.py does, from
# config.yaml) — not the corpus's; a corpus is not bound to a runtime.
# Older corpora still carrying forgejo:/mcp:/sandbox_image validate with a
# deprecation warning, never a failure.
name: gsj-demo-synthetic
owner: gsj-staging                    # any usable Forgejo username (library CP-71's shape check);
                                      #   the token env vars derive from it
git:                                  # DO NOT CHANGE: fixed identity => deterministic commit SHAs
  name: gsj-demo-fixtures
  email: fixtures@gsj.invalid
  date: "2026-01-01T00:00:00 +0000"
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

# The decisions-citation clause (library docs/decisions-surface.md §9.5),
# inserted into the reference AGENTS.md before its "## Deliverables"
# section. Both halves are deliberate: the format the hit gives, and the
# DEGRADATION RULE — an agent that meets a hit without an `rn` (a section
# unit, or a level-1 implementation) drops the suffix rather than inventing
# one; the grammar has no valid suffixed form for such a hit.
AGENTS_DECISIONS_CLAUSE = """\
## Decisions

- `mcp_gsj_search_decisions` searches published court decisions (precedent),
  not the case file; its hits are not scoped by the case's cutoff.
- Cite a decision as `dec:<doknr>:rn:<N>` — the hit gives you both:
  `decision_id` is the doknr, `rn` is the Randnummer (for example
  `dec:GREV000082013:rn:7`).
- When the hit carries no `rn` (`rn: null`, or no `rn` key at all), drop the
  suffix and cite `dec:<doknr>`. Never invent an `rn`, and never cite a
  decision that no search in this session returned.

""".encode("utf-8")
AGENTS_INSERT_BEFORE = b"## Deliverables"

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
and 114/3. Ortiz's plan places the old wire fence 3.2 metres EAST of the
registered boundary line along the full length of the disputed strip; the
strip between the registered line and the fence is therefore, by the
registry geometry alone, part of parcel 114/3 — the respondent's parcel.

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
  - {id: "free:precedent", source: free, text: "Page 4 records a right of way over the disputed strip. Search the decisions for precedent on whether such a registered right survives a change of ownership of the strip, and say what they hold, citing each decision you rely on."}
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
  - {id: "free:precedent", source: free, text: "The tenant withholds rent over flooding that the cooperative's own maintenance file shows it knew about and deferred repairing. Search the decisions for precedent on whether arrears that build up that way can found a termination, and say what they hold, citing each decision you rely on."}
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


def agents_md(reference: bytes) -> bytes:
    """The reference AGENTS.md with the §9.5 decisions clause inserted before
    its Deliverables section — exactly once, or the derivation is unsound."""
    if reference.count(AGENTS_INSERT_BEFORE) != 1:
        sys.exit("make_corpus: the packaged reference AGENTS.md does not carry one "
                 "'## Deliverables' section — the clause has no place to go; "
                 "report it with the installed library version")
    head, tail = reference.split(AGENTS_INSERT_BEFORE)
    return head + AGENTS_DECISIONS_CLAUSE + AGENTS_INSERT_BEFORE + tail


# --- the decisions drop: rii-dok v1, rendered from synthetic/decisions.json --

RII_DOCTYPE = ('<!DOCTYPE dokument\n'
               '  SYSTEM "https://www.rechtsprechung-im-internet.de/dtd/v1/rii-dok.dtd">')
# the fictional courts' benches, by senate/chamber — the signatures after
# the last Randnummer (a table or plain rows: both shapes the surface DROPS)
JUDGES = {
    ("OLG", "4. Zivilsenat"): ("Dr. Feldmann", "Aurich", "Dr. Sperling"),
    ("OLG", "8. Zivilsenat"): ("Wendt", "Dr. Lohse", "Kastner"),
    ("OLG", "12. Zivilsenat"): ("Dr. Brandes", "Ihle", "Nowak"),
    ("LG", "2. Zivilkammer"): ("Dr. Rabe", "Vollmer", "Schick"),
    ("LG", "7. Zivilkammer"): ("Hennig", "Dr. Orth", "Lange"),
}
SECTION_UNITS = ("titelzeile", "leitsatz", "tenor")   # one section unit each when present


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(text: str, style: str, *, indent: bool = False, span: bool = False) -> str:
    """One paragraph, in the drop's two renderings: the pre-2018 plain
    `<p>`, and the post-2018 export that wraps every paragraph's text in a
    styled `<span>` (the fixture's third file — a `.text`-only parser reads
    it as empty; the surface's `itertext` does not). `indent` is the
    publisher's quotation rendering (`margin-left:36pt`) the unit rule keys
    on; `span` forces a bare `<span>` wrapper (the indented-tail
    discriminator of the fixture's sixth file)."""
    attrs = []
    if indent:
        attrs.append("margin-left:36pt")
    if style == "span":
        attrs.append("text-align: justify")
    attr = f' style="{"; ".join(attrs)}"' if attrs else ""
    if style == "span":
        body = f'<span style="color: rgb(0, 0, 0)">{_esc(text)}</span>'
    elif span:
        body = f"<span>{_esc(text)}</span>"
    else:
        body = _esc(text)
    return f"<p{attr}>{body}</p>"


def _table(cells: list) -> list:
    """`<table class="Rsp">` as the publisher writes it (signature blocks,
    the odd table inside a Randnummer) — dropped whole by the surface."""
    lines = ['<table class="Rsp">']
    for row in cells:
        lines.append("   <tr>")
        for cell in row:
            lines += ['      <td colspan="1" rowspan="1" valign="top">',
                      f'         <p style="text-align:left">{_esc(cell)}</p>',
                      "      </td>"]
        lines.append("   </tr>")
    lines.append("</table>")
    return lines


def _dl(anchor, dd_lines: list) -> list:
    """One `<dl class="RspDL">` row: `anchor` None for an unanchored row,
    else the Randnummer whose `<a name="rd_N">` opens the unit."""
    lines = ['         <dl class="RspDL">']
    if anchor is None:
        lines.append("            <dt/>")
    else:
        lines += ["            <dt>", f'               <a name="rd_{anchor}">{anchor}</a>',
                  "            </dt>"]
    lines += ["            <dd>"] + [f"               {line}" for line in dd_lines] \
        + ["            </dd>", "         </dl>"]
    return lines


SPACER = _dl(None, ["<p/>"])          # the publisher's empty row between rows


def _section(name: str, blocks: list, *, div: bool = True) -> list:
    if not blocks:
        return [f"   <{name}/>"]
    rows = [line for block in blocks for line in block]
    if not div:                          # titelzeile: rows directly under the element
        return [f"   <{name}>"] + [line[3:] for line in rows] + [f"   </{name}>"]
    return [f"   <{name}>", "      <div>"] + rows + ["      </div>", f"   </{name}>"]


def _text_rows(texts: list, style: str) -> list:
    blocks = []
    for i, text in enumerate(texts):
        if i:
            blocks.append(SPACER)
        blocks.append(_dl(None, [_p(text, style)]))
    return blocks


def _reasoning_rows(rows: list, style: str, tail, signature, judges) -> list:
    """A reasoning section's rows in document order: anchored Randnummern,
    headings and resumed paragraphs (plain unanchored rows), indented
    quotations, a table standing as its own row (its only content —
    dropped, the row ignored), then after the last anchor the optional
    indented notice (kept by the tail rule) and the signatures (dropped)."""
    blocks = []
    for row in rows:
        kind = row["kind"]
        if kind == "rn":
            blocks.append(_dl(row["n"], [_p(row["text"], style)]))
        elif kind in ("heading", "plain"):
            blocks.append(_dl(None, [_p(row["text"], style)]))
        elif kind == "quote":
            blocks.append(_dl(None, [_p(row["text"], style, indent=True)]))
        elif kind == "table":
            blocks.append(_dl(None, _table(row["table"])))
        else:
            raise ValueError(f"unknown row kind {kind!r}")
        blocks.append(SPACER)
    if tail:
        blocks.append(_dl(None, [_p(tail, style, indent=True, span=True)]))
        blocks.append(SPACER)
    if signature == "table":
        a, b, c = judges
        blocks.append(_dl(None, _table([[a, "", b], ["", c, ""]])))
    elif signature == "rows":
        a, b, c = judges
        blocks.append(_dl(None, [_p(f"{a}                    {b}", style)]))
        blocks.append(_dl(None, [_p(f"           {c}", style)]))
    return blocks


def decision_xml(d: dict) -> str:
    """One decision as rii-dok v1: the 26 elements of the DTD in its order
    (spec §2.1), the nine ANY body sections carrying `<dl class="RspDL">`
    rows. Deterministic: the same data renders the same bytes."""
    style, judges = d["style"], JUDGES[(d["court"], d["spruchkoerper"])]
    body = d["body"]
    head = [
        '<?xml version="1.0" encoding="UTF-8"?>', RII_DOCTYPE, "<dokument>",
        f"   <doknr>{d['doknr']}</doknr>",
        f"   <ecli>{_esc(d['ecli'])}</ecli>" if d["ecli"] else "   <ecli/>",
        f"   <gertyp>{_esc(d['court'])}</gertyp>",
        f"   <gerort>{_esc(d['gerort'])}</gerort>",
        f"   <spruchkoerper>{_esc(d['spruchkoerper'])}</spruchkoerper>",
        f"   <entsch-datum>{d['date']}</entsch-datum>",
        f"   <aktenzeichen>{_esc(d['aktenzeichen'])}</aktenzeichen>",
        f"   <doktyp>{_esc(d['doktyp'])}</doktyp>",
        f"   <norm>{_esc(d['norm'])}</norm>" if d["norm"] else "   <norm/>",
        ("   <vorinstanz>" + "".join(f"{_esc(v)}<br/>" for v in d["vorinstanz"])
         + "\n   </vorinstanz>") if d["vorinstanz"] else "   <vorinstanz/>",
        "   <region>", "      <abk>DEU</abk>", "      <long>Bundesrepublik Deutschland</long>",
        "   </region>", "   <mitwirkung/>",
    ]
    sections = []
    sections += _section("titelzeile", _text_rows([d["titelzeile"]], style)
                         if d["titelzeile"] else [], div=False)
    sections += _section("leitsatz", _text_rows(d["leitsatz"], style))
    sections += _section("sonstosatz", [])
    sections += _section("tenor", _text_rows(d["tenor"], style))
    # the signatures (and the tail notice) close the LAST reasoning section
    last = next((n for n in ("gruende", "entscheidungsgruende", "tatbestand")
                 if body.get(n)), None)
    for name in ("tatbestand", "entscheidungsgruende", "gruende"):
        rows = body.get(name) or []
        closing = name == last
        sections += _section(name, _reasoning_rows(
            rows, style, d["rechtsmittelbelehrung"] if closing else None,
            d["signature"] if closing else None, judges) if rows else [])
    sections += _section("abwmeinung", [])
    sections += _section("sonstlt", [])
    foot = [
        f"   <identifier>https://decisions.grevenau.invalid/?docid=jb-{d['doknr']}</identifier>",
        "   <coverage>Grevenau</coverage>", "   <language>englisch</language>",
        "   <publisher>gsj-rollout-demo (synthetic)</publisher>",
        "   <accessRights>public</accessRights>", "</dokument>", "",
    ]
    return "\n".join(head + sections + foot)


def expected_units(d: dict) -> list:
    """What the surface's unit rule (spec §4) produces for this decision, in
    order: one section unit per non-empty titelzeile/leitsatz/tenor, then
    one Randnummer unit per anchored row — headings, quotations and resumed
    paragraphs join the Randnummer they follow; a table-only row, the
    signatures and a plain row after the last anchor produce nothing; the
    indented tail notice joins the last Randnummer."""
    units = [(name, None) for name in SECTION_UNITS
             if (d[name] if name != "titelzeile" else d["titelzeile"])]
    for name in ("tatbestand", "entscheidungsgruende", "gruende"):
        units += [(name, row["n"]) for row in d["body"].get(name) or []
                  if row["kind"] == "rn"]
    return units


def load_decisions() -> list:
    decisions = json.loads(DECISIONS_JSON.read_text(encoding="utf-8"))
    ids = [d["doknr"] for d in decisions]
    assert len(ids) == len(set(ids)) == 30, "the drop is thirty distinct doknr"
    return decisions


def write_decisions(out: Path, decisions: list) -> dict:
    out.mkdir(parents=True)
    census = {"files": 0, "units": 0, "randnummern": 0, "section_units": 0,
              "by_court": Counter(), "by_year": Counter(), "rn": {}}
    for d in decisions:
        (out / f"jb-{d['doknr']}.xml").write_text(decision_xml(d), encoding="utf-8")
        units = expected_units(d)
        census["files"] += 1
        census["units"] += len(units)
        census["randnummern"] += sum(1 for _, rn in units if rn is not None)
        census["section_units"] += sum(1 for _, rn in units if rn is None)
        census["by_court"][d["court"]] += 1
        census["by_year"][d["date"][:4]] += 1
        census["rn"][d["doknr"]] = [rn for _, rn in units if rn is not None]
    return census


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "corpus-synthetic"),
                    help="the corpus root; the decisions drop goes to <out>-decisions")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing tree (and its drop)")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    drop = out.parent / f"{out.name}-decisions"
    for path in (out, drop):
        if path.exists():
            if not args.force:
                print(f"{path} already exists — pass --force to regenerate "
                      "(the tree is deterministic; regeneration is byte-identical)")
                return 1
            shutil.rmtree(path)

    # the reference AGENTS.md comes out of the installed library's packaged
    # capture — read (and tripwired) BEFORE anything is written, so a missing
    # or inconsistent library leaves no half-built tree behind
    sys.path.insert(0, str(REPO))
    from bootstrap import reference_capture
    cap, i, j = reference_capture()
    decisions = load_decisions()
    out.mkdir(parents=True)
    (out / "corpus.yaml").write_text(CORPUS_YAML)
    (out / "AGENTS.md").write_bytes(agents_md(cap[i:j]))
    (out / "skills" / "brief").mkdir(parents=True)
    (out / "skills" / "brief" / "SKILL.md").write_text(SKILL_BRIEF)

    write_case(out, "train", "case_orchard", ORCHARD_PAGES,
               {2: ORCHARD_PROMPTS_T2, 4: ORCHARD_PROMPTS_T4})
    write_case(out, "eval", "case_mill", MILL_PAGES,
               {3: MILL_PROMPTS_T3})
    census = write_decisions(drop, decisions)

    print(f"synthetic corpus written to {out}")
    print("  train/case_orchard: timesteps 2 and 4 — the 1998 easement deed "
          "(registry no. 98-4417) exists only on page 4; an episode at "
          "timestep 2 cannot see it, an episode at timestep 4 must find it")
    print("  eval/case_mill:     timestep 3, skill-card prompt + a precedent prompt")
    print("  AGENTS.md:          the reference text + the decisions-citation clause "
          "(dec:<doknr>:rn:<N>; G2 re-derives at `up`)")
    by_court = ", ".join(f"{c} {n}" for c, n in sorted(census["by_court"].items()))
    years = sorted(census["by_year"])
    print(f"decisions drop written to {drop}")
    print(f"  {census['files']} rii-dok v1 files (jb-<doknr>.xml), {census['units']} units the "
          f"surface should produce: {census['randnummern']} Randnummern + "
          f"{census['section_units']} section units; by court {by_court}; "
          f"{years[0]}–{years[-1]}")
    print("  written to bear on the two cases (easements, the register against the "
          "fence, prescriptive possession, lease termination for arrears, rent "
          "reduction for flooding, the deferred repair) — a search returns precedent "
          "a lawyer on these cases would want")
    print("next: point config.yaml's `corpus:` here and run ./bootstrap.py up "
          "(it finds the drop beside the corpus)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
