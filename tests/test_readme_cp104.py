"""Library CP-104 — what the last round's two demo-door strangers found, and
the README sentences that answer them, pinned to the code they describe.

Round seven (2026-09-09, against 0.1.14): a1 and a2 both ran step 1b; a1 ran
the t=2 half through the triple and got the honest negative; library row 107
closed. The README now says where each half of the cutoff is enforced (F-124),
what `bootstrap.py`'s failed-derivation path prints and which of it not to
believe (F-122, F-123 — the `bootstrap.py` half is recorded, not lifted), the
image sizes measured from the manifests (F-121), and seven sentences checked
against the tool (F-125). Every test below reads the README AND the source it
quotes: when `bootstrap.py` is lifted and F-122/F-123 are fixed, these fail
and name the README sentence to move with them.

Hermetic: no Docker, no endpoint."""
import ast
import importlib.util
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
FLAT = " ".join(README.split())            # the README with its line wraps undone


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bootstrap = module("bootstrap_cp104", ROOT / "bootstrap.py")
BOOTSTRAP_SRC = (ROOT / "bootstrap.py").read_text()
READ_SRC = (ROOT / "read.py").read_text()


# --------------------------------------------- F-121: the sizes, one label each

def test_no_disk_figure_is_labelled_as_the_wire():
    assert "4.05 GB compressed on the wire" not in FLAT
    assert "44% of the total" not in FLAT.replace("44% of the total\" through", "")
    assert "**~1.8 GB compressed on the wire**" in FLAT          # the Quickstart
    assert "**~1.8 GB compressed on the wire** — the one that governs the clock" in FLAT
    assert "1.79 GB for `arm64`, 1.84 GB for `amd64`" in FLAT
    assert "`docker system df` is the accounting check once the pulls are done" in FLAT


# --------------------------------------------- F-122 / F-123: the failure path, quoted from the source

def test_the_derivation_timeout_the_readme_states_is_bootstraps():
    timeout = inspect.signature(bootstrap._endpoint_json).parameters["timeout"].default
    assert timeout == 15.0
    assert "one `/tokenize` request per probe, each under a 15 s timeout and no retry" in FLAT
    assert "one `/tokenize` request per probe with a 15 s timeout and no retry" in FLAT


def test_the_inference_the_readme_quotes_is_what_a_timeout_makes_bootstrap_print(monkeypatch):
    monkeypatch.setattr(bootstrap, "_endpoint_json",
                        lambda url, payload, timeout=15.0: (None, "TimeoutError: timed out"))
    why = bootstrap.derive_endpoint_pins("http://engine.invalid:8000", "qwen3.6-27b", "off")["why"]
    quoted = "this endpoint cannot render its own chat template over the API (not vLLM?)"
    assert quoted in " ".join(why.split())
    assert f"`{quoted}` is an inference from one lost request" in FLAT


def test_the_coverage_string_the_readme_warns_about_is_keyed_on_the_model_not_the_derivation():
    literal = "derived here from the endpoint's own template render (G6); "
    assert literal in BOOTSTRAP_SRC
    # the branch that chooses it reads `reference` (the model name), not the derivation's result
    assert 'reference = model == REFERENCE_MODEL' in BOOTSTRAP_SRC
    assert "still reads `derived here from the endpoint's own template render`" in FLAT


def test_the_reference_id_the_readme_says_is_passed_down_is_bootstraps_fallback():
    assert 'answers["end_of_turn_token_id"] = BuilderConfig().end_of_turn_token_id' in BOOTSTRAP_SRC
    from gsj_rollout.config import BuilderConfig
    assert BuilderConfig().end_of_turn_token_id == 151645
    assert "`WARNING: --end-of-turn-token-id 151645 disagrees with the endpoint's own render`" in FLAT
    assert "`bootstrap.py` having passed the reference id down" in FLAT


def test_step_0_says_run_the_preflight_after_up():
    assert "**Run it again after `up` and before your first submit — `up` can exit 0 on pins it expects to be quarantined.**" in FLAT
    assert "F-122 and F-123 carry the `bootstrap.py` half" in FLAT


# --------------------------------------------- F-124: where each half is enforced

def test_step_1b_says_where_each_half_is_enforced():
    assert "**Where each half is enforced**" in FLAT
    for claim in ("`--depth 1 --single-branch`, the remote and the reflog then removed",
                  "takes `T` from the token alone",
                  "filters its candidates to `page <= T` *before* ranking",
                  "`test_cutoff_prefilters_candidates_not_postfilters`",
                  "a case-file search never reads the checkout",
                  "`mcp_gsj_search_decisions` is never clamped"):
        assert claim in FLAT, claim


def test_read_py_computes_its_census_itself_as_the_readme_says():
    """'two implementations of one property on one record': read.py imports
    no part of the library and parses the search hits with its own parser."""
    tree = ast.parse(READ_SRC)
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "gsj_rollout" not in imported
    assert "def parse_hits(" in READ_SRC and "hit_pages.extend(" in READ_SRC
    assert "are `read.py`'s own computation over the archived trace" in FLAT


def test_row_107_is_described_as_closed_and_as_a_claim_about_the_walkthrough():
    assert "the row closed at library CP-104 — as a claim about what this walkthrough can *show* a reader" in FLAT
    assert "It was never a question about whether the retrieval service filters" in FLAT
    assert "open row 107" not in FLAT


# --------------------------------------------- F-125: seven sentences, each against the tool

def test_length_terminated_is_described_as_printed_every_run():
    import gsj_rollout.cli as cli
    src = inspect.getsource(cli)
    assert 'print(f"length-terminated: {truncated}/{len(accepted)} accepted episodes ended "' in src
    assert "the `length-terminated: N/M` line it prints after every run" in FLAT


def test_the_heartbeat_states_the_readme_names_are_bootstraps():
    layers = {"a" * 12: "Extracting", "b" * 12: "Download complete", "c" * 12: "Downloading",
              "d" * 12: "Pull complete"}
    text, _ = bootstrap.pull_phase_summary(layers)
    assert text == "1/4 layers complete, 1 extracting, 1 downloaded, waiting to extract, 1 downloading"
    assert ("then whichever of `K extracting`, `K downloaded, waiting to extract` and "
            "`J downloading` apply, in that order") in FLAT


def test_the_poll_line_forms_the_readme_quotes_are_the_librarys():
    import gsj_rollout.estate as est
    src = inspect.getsource(est)
    assert "building {b['collection']}: batch" in src
    assert "the service is still working (the next collection has not reported a batch yet)" in src
    assert "`the service is still working (the next collection has not reported a batch yet)`" in FLAT


def test_submit_sh_carries_absolute_paths_and_passes_arguments_through():
    assert Path(bootstrap.WORK).is_absolute()
    assert 'f"    -v {WORK}/estate:/estate' in BOOTSTRAP_SRC and ' "$@"\\n' in BOOTSTRAP_SRC
    assert "`work/estate/submit.sh` holds the same command with absolute paths written in" in FLAT
    assert "`work/estate/submit.sh --row 2` gives this row (the last `--row` wins)" in FLAT


def test_the_three_rollout_yamls_are_named_and_are_the_ones_bootstrap_writes():
    assert '(ESTATE / "rollout.yaml").write_text(text)' in BOOTSTRAP_SRC
    assert '(ESTATE / "receiver" / "rollout.yaml").write_text(text)' in BOOTSTRAP_SRC
    for path in ("`work/runs/demo/rollout.yaml`", "`work/estate/rollout.yaml`",
                 "`work/estate/receiver/rollout.yaml`"):
        assert path in FLAT, path


def test_a_new_shell_is_reminded_of_the_venv_in_the_quickstart():
    quick = README.split("## Quickstart", 1)[1].split("```bash", 1)[1].split("```", 1)[0]
    lines = [l.strip() for l in quick.strip().splitlines()]
    clone = next(i for i, l in enumerate(lines) if l.startswith("git clone "))
    assert lines[clone + 1].startswith("# a new shell later? `. ../.venv/bin/activate` here first")
    # the install line the proofs extract is unchanged
    assert "pip install --timeout 120 --retries 5 'gsj-harness-rollout-server>=0.1.17' pyarrow" in lines


# --------------------------------------------- F-126: four answers, each true of the code

def test_reward_is_the_trace_field_passed_through():
    assert '"reward": trace.get("reward")' in READ_SRC
    assert "`export`'s `reward` is the trace's own field passed through" in FLAT


def test_the_g4_walk_is_named_and_the_kwargs_are_the_ones_pi_sends():
    assert "the library's `pins/derive_pins.py`, run where the served snapshot's files are on disk" in FLAT
    assert '`{"enable_thinking": <level != off>, "preserve_thinking": true}` on every request whatever the level' in FLAT
