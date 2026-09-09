"""Library CP-103 — the instrument before the last round.

CP-102 ran the walkthrough's step 1b (row 2 at t=2 beside row 3 at t=4) and
found that the 0.6B floor model never opened the case file at t=4: row 3's
prompt asked a question a precedent search could plausibly answer, and the
model took the plausible route. This module pins what the corpus generator
now guarantees so the pair stays an instrument rather than a coin toss:

- row 3 of the bank is still ``case_orchard@4`` / ``free:easement`` (the bank
  sorts by case, timestep, prompt id — the README's ``--row 3`` depends on it);
- the easement prompt names the case file as its source, asks for the page in
  the ``(page:N)`` form the agent is taught, and names no tool;
- the fact it asks for — deed no. 98-4417 — exists on page 4 alone, and the
  rendered decisions drop does not carry it, so a decisions search cannot
  answer the question;
- ``lock_holder()`` ignores a lock file whose process is gone (F-117 — the
  lock is the kernel's flock, not the file; verified on the real function).

Hermetic: no Docker, no endpoint. The corpus tests need the installed
library's packaged G2 capture (make_corpus.py reads it)."""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


make_corpus = module("make_corpus", ROOT / "synthetic" / "make_corpus.py")
bootstrap = module("bootstrap", ROOT / "bootstrap.py")

DEED_NO = "98-4417"
DEED_DATE = "11 August 1998"


def bank_rows():
    """The bank's rows in the order ingest_corpus.py's taskbank phase writes
    them — sorted by (case_id, timestep, prompt_id), the library's rule."""
    rows = []
    for case_id, by_t in (("case_orchard", {2: make_corpus.ORCHARD_PROMPTS_T2,
                                            4: make_corpus.ORCHARD_PROMPTS_T4}),
                          ("case_mill", {3: make_corpus.MILL_PROMPTS_T3})):
        for t, text in by_t.items():
            for p in yaml.safe_load(text)["prompts"]:
                rows.append((case_id, t, p["id"], p))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return rows


def easement_prompt() -> str:
    return next(p["text"] for p in yaml.safe_load(make_corpus.ORCHARD_PROMPTS_T4)["prompts"]
                if p["id"] == "free:easement")


# ----------------------------------------------------------- the bank's rows

def test_the_bank_has_six_rows_and_row_3_is_case_orchard_at_t4_free_easement():
    rows = bank_rows()
    assert len(rows) == 6
    assert [(r[0], r[1], r[2]) for r in rows] == [
        ("case_mill", 3, "free:precedent"), ("case_mill", 3, "skill:brief"),
        ("case_orchard", 2, "free:boundary-evidence"),
        ("case_orchard", 4, "free:easement"),           # the README's step 1b: --row 3
        ("case_orchard", 4, "free:precedent"), ("case_orchard", 4, "skill:brief"),
    ]


# -------------------------------------------------------- the prompt's shape

def test_the_easement_prompt_names_the_case_file_as_its_source():
    """Row 2's prompt works because it asks what is *in the case file so far*;
    the shipped row 3 asked a question precedent could plausibly answer."""
    text = easement_prompt()
    assert "case file" in text
    assert "so far" in text                       # the same anchor row 2 uses


def test_the_easement_prompt_asks_for_the_page_in_the_taught_form():
    assert "(page:N)" in easement_prompt()


def test_the_easement_prompt_is_a_question_not_a_tool_instruction():
    text = easement_prompt().lower()
    for forbidden in ("mcp_", "search_case", "search_decisions", "tool", "search"):
        assert forbidden not in text, forbidden


def test_the_easement_prompt_asks_for_what_only_page_4_carries():
    """The deed's number and its registration date are page 4's facts; a
    precedent hit carries a doknr and a docket, never a deed number."""
    text = easement_prompt()
    assert "deed number" in text
    assert "registered" in text and "which page" in text


def test_the_easement_prompt_does_not_invite_an_answer_without_looking():
    """Measured at library CP-103 on the 0.6B floor, at t=4 where the deed
    exists: both variants carrying an "if the file does not contain one, say
    so" clause let the model write exactly that sentence with NO tool call —
    3 of 5 samples for one wording, 5 of 5 for the other. The honest t=2
    answer must come from a search that finds nothing, not from a clause that
    excuses the search — so the prompt has no such clause. `If so` is the
    whole allowance for a negative."""
    low = easement_prompt().lower()
    for forbidden in ("say so", "does not contain", "if not", "not in the file"):
        assert forbidden not in low, forbidden
    assert "if so" in low


def test_the_precedent_prompt_stays_the_one_that_names_the_decisions():
    """Row 4 (`free:precedent`) is the prompt built for the decisions tool;
    the easement prompt must not drift into its territory."""
    rows = {r[2]: r[3].get("text", "") for r in bank_rows() if r[0] == "case_orchard" and r[1] == 4}
    assert "decisions" in rows["free:precedent"].lower()
    assert "decisions" not in rows["free:easement"].lower()
    assert "precedent" not in rows["free:easement"].lower()


# -------------------------------------------- the fact lives on page 4 only

def test_the_deed_number_is_on_page_4_of_the_orchard_pages_and_nowhere_else():
    pages = make_corpus.ORCHARD_PAGES
    assert DEED_NO in pages[4] and DEED_DATE in pages[4]
    for n in (1, 2, 3):
        low = pages[n].lower()
        assert DEED_NO not in pages[n]
        assert "easement" not in low and "right of way" not in low
    for n, text in make_corpus.MILL_PAGES.items():
        assert DEED_NO not in text


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    out = tmp_path_factory.mktemp("cp103") / "corpus"
    proc = subprocess.run([sys.executable, str(ROOT / "synthetic" / "make_corpus.py"), "--out", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not (out / "decisions").is_dir():
        pytest.skip(f"make_corpus.py could not write a corpus: {proc.stderr[-300:]}")
    return out


def test_the_rendered_decisions_drop_does_not_carry_the_deed_number(corpus):
    """decisions.json's `bears_on` notes name the deed — an author's
    annotation, never rendered. The XML the service ingests must not carry
    it, or a decisions search could answer the case-file question."""
    xml_files = sorted((corpus / "decisions").glob("*.xml"))
    assert len(xml_files) == 30
    carriers = [p.name for p in xml_files if DEED_NO in p.read_text(encoding="utf-8")
                or DEED_DATE in p.read_text(encoding="utf-8")]
    assert carriers == []


def test_in_the_written_tree_only_timestep_4_page_4_carries_the_deed_number(corpus):
    hits = sorted(str(p.relative_to(corpus)) for p in corpus.rglob("*")
                  if p.is_file() and DEED_NO in p.read_text(encoding="utf-8", errors="replace"))
    assert hits == ["train/cases/case_orchard/timestep-4/pages/page_0004.md"]
    assert not (corpus / "train/cases/case_orchard/timestep-2/pages/page_0004.md").exists()


def test_the_generators_own_printout_names_the_deed_number(corpus):
    """The number the t=4 answer must carry is printed at generation, so a
    reader can check a transcript against it without opening page 4."""
    proc = subprocess.run([sys.executable, str(ROOT / "synthetic" / "make_corpus.py"), "--out", str(corpus)],
                          capture_output=True, text=True)
    assert proc.returncode == 1 and "already exists" in proc.stdout      # refuses to overwrite: fine
    src = (ROOT / "synthetic" / "make_corpus.py").read_text()
    assert re.search(r"registry no\. 98-4417", src)


# ------------------------------------------------------ F-117: the stale lock

@pytest.fixture
def work(tmp_path, monkeypatch):
    w = tmp_path / "work"
    monkeypatch.setattr(bootstrap, "WORK", w)
    monkeypatch.setattr(bootstrap, "LOCK", w / ".bootstrap.lock")
    monkeypatch.setattr(bootstrap, "RUNDIR", w / "runs" / "demo")
    monkeypatch.setattr(bootstrap, "ESTATE", w / "estate")
    monkeypatch.setattr(bootstrap, "POLAR_ENV", w / "polar.env")
    return w


def test_a_lock_file_whose_process_is_gone_is_not_a_holder(work, monkeypatch, capsys):
    """a2 (round six) hit a lock left by two killed `up`s and found `status`
    ignoring it, correctly and undocumented. The lock is the kernel's flock:
    the file's text survives a killed process, the flock does not, so
    lock_holder() sees no holder and status reports the estate, not ACTIVE."""
    work.mkdir()
    bootstrap.LOCK.write_text("./bootstrap.py up (pid 999999) since 2026-09-09T00:00:00+0000\n")
    assert bootstrap.lock_holder() is None
    ps = subprocess.CompletedProcess([], 0, "NAME\tSTATUS\tPORTS\n", "")
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: ps)
    bootstrap.print_status(None, None, None, active=bootstrap.lock_holder())
    out = capsys.readouterr().out
    assert "ACTIVE" not in out
    assert "nothing running — ./bootstrap.py up" in out
    assert bootstrap.LOCK.is_file()                     # and nobody had to delete it


def test_a_live_holder_is_still_reported(work, capsys):
    with bootstrap.held_for("up"):
        assert (bootstrap.lock_holder() or "").startswith("./bootstrap.py up (pid")
    assert bootstrap.lock_holder() is None              # released with the process's fd
