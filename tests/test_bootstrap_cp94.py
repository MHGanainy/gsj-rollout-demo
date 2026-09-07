"""Library CP-94 — what round three found in bootstrap.py: `status` during an
`up` (the lock), the pull heartbeat, and a pins file that says what it
covers (`coverage`, `provenance.engine` re-recorded for the endpoint that
serves this estate, the reference block kept as `carried_from`).

Hermetic: no Docker, no endpoint. The pins tests need the installed
library's packaged pins and G2 capture (the wheel), and a corpus written
by synthetic/make_corpus.py into a temp directory."""
import fcntl
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bootstrap = module('bootstrap')


@pytest.fixture
def work(tmp_path, monkeypatch):
    """A private work/ (the lock, the estate dir) so nothing touches the repo's."""
    w = tmp_path / "work"
    monkeypatch.setattr(bootstrap, "WORK", w)
    monkeypatch.setattr(bootstrap, "LOCK", w / ".bootstrap.lock")
    monkeypatch.setattr(bootstrap, "RUNDIR", w / "runs" / "demo")
    monkeypatch.setattr(bootstrap, "ESTATE", w / "estate")
    monkeypatch.setattr(bootstrap, "POLAR_ENV", w / "polar.env")
    return w


# ------------------------------------------------------------- the lock

def test_status_says_active_and_suggests_nothing_while_up_holds_the_lock(work, monkeypatch, capsys):
    """A stranger ran `status` mid-pull and read `nothing running —
    ./bootstrap.py up` twice plus `no bring-up record — ./bootstrap.py up`."""
    ps = subprocess.CompletedProcess([], 0, "NAME\tSTATUS\tPORTS\n", "")
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: ps)
    with bootstrap.held_for("up"):
        holder = bootstrap.lock_holder()
        assert holder and holder.startswith("./bootstrap.py up (pid")
        bootstrap.print_status(None, None, None, active=holder)
    out = capsys.readouterr().out
    assert "== the estate == ACTIVE — ./bootstrap.py up (pid" in out and "wait for it" in out
    assert "Do not start a second `up`" in out and "never delete the lock file" in out
    assert "nothing running yet — the running command has not reached it" in out
    assert "no bring-up record" in out and "yet — it lands once" in out
    assert "— ./bootstrap.py up)" not in out            # the old suggestion, gone while active
    assert bootstrap.lock_holder() is None               # released with the command


def test_status_without_a_running_command_keeps_the_no_estate_suggestions(work, monkeypatch, capsys):
    ps = subprocess.CompletedProcess([], 0, "NAME\tSTATUS\tPORTS\n", "")
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: ps)
    bootstrap.print_status(None, None, None, active=bootstrap.lock_holder())
    out = capsys.readouterr().out
    assert "ACTIVE" not in out
    assert "(gsj-demo: nothing running — ./bootstrap.py up)" in out
    assert "no bring-up record at" in out and "— ./bootstrap.py up)" in out


def test_a_second_up_is_refused_as_busy_while_the_lock_is_held(work, capsys):
    with bootstrap.held_for("up"):
        with pytest.raises(SystemExit) as exc:
            with bootstrap.held_for("down"):
                pass
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "another ./bootstrap.py command holds" in err and "is still running" in err
    assert "status says ACTIVE" in err and "do not delete the lock file" in err


def test_lock_holder_reads_a_free_or_missing_lock_as_none(work):
    assert bootstrap.lock_holder() is None
    with bootstrap.held_for("up"):
        pass
    assert (work / ".bootstrap.lock").is_file() and bootstrap.lock_holder() is None


def test_the_lock_is_held_across_a_separate_open_description(work):
    """What `status` in another process sees: the kernel lock, not the file."""
    with bootstrap.held_for("up"):
        fd = (work / ".bootstrap.lock").open("r")
        with pytest.raises(BlockingIOError):
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.close()


# --------------------------------------------------------- the heartbeat

def test_ensure_image_beats_with_elapsed_and_host_bytes_during_a_slow_pull(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "PULL_HEARTBEAT_S", 0.15)
    counter = {"rx": 10 ** 9}

    def rx():
        counter["rx"] += 2 * 1024 * 1024
        return counter["rx"]

    monkeypatch.setattr(bootstrap, "host_rx_bytes", rx)
    monkeypatch.setattr(bootstrap, "image_present", lambda image: False)

    def fake_run(cmd, **kw):
        assert cmd == ["docker", "pull", "example.invalid/big:1"]
        time.sleep(0.5)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    bootstrap.ensure_image("example.invalid/big:1", "a test image")
    out = capsys.readouterr().out
    beats = [line for line in out.splitlines() if "still pulling example.invalid/big:1" in line]
    assert len(beats) >= 2, out
    assert all("elapsed" in b and "received 2.0 MiB" in b and "the pipe is moving" in b for b in beats)
    assert "The pull that is healthy and silent" in out


def test_ensure_image_heartbeat_says_nothing_moved_and_points_at_the_three_checks(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "PULL_HEARTBEAT_S", 0.15)
    monkeypatch.setattr(bootstrap, "host_rx_bytes", lambda: 7)
    monkeypatch.setattr(bootstrap, "image_present", lambda image: False)
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: (time.sleep(0.4),
                                                             subprocess.CompletedProcess(cmd, 1, "", "no such host"))[1])
    with pytest.raises(SystemExit):
        bootstrap.ensure_image("example.invalid/big:1", "a test image")
    out = capsys.readouterr()
    assert "received NOTHING" in out.out and "the three checks" in out.out
    assert "could not pull example.invalid/big:1" in out.err


def test_host_rx_bytes_is_a_count_or_none():
    value = bootstrap.host_rx_bytes()
    assert value is None or (isinstance(value, int) and value >= 0)


# ------------------------------------------------------- what pins cover

@pytest.fixture
def corpus(tmp_path):
    out = tmp_path / "corpus"
    proc = subprocess.run([sys.executable, str(ROOT / "synthetic" / "make_corpus.py"), "--out", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not (out / "AGENTS.md").is_file():
        pytest.skip(f"make_corpus.py could not write a corpus: {proc.stderr[-300:]}")
    return out


def pins_for(work, corpus, model, base_url):
    work.mkdir(exist_ok=True)
    (work / "estate").mkdir(exist_ok=True)
    bootstrap.derive_pins(corpus, model, "off", base_url)
    return json.loads((work / "estate" / "pins.gsj.json").read_text())


def test_foreign_model_pins_record_the_endpoint_not_the_reference_machine(work, corpus, monkeypatch, capsys):
    """The stranger's finding: provenance.engine named Qwen/Qwen3-0.6B at
    127.0.0.1:8000 with HF snapshot paths that do not exist on this host."""
    monkeypatch.setattr(bootstrap, "derive_endpoint_pins",
                        lambda base, model, thinking: {"why": "no /tokenize (test)", "tail_ids": None})
    doc = pins_for(work, corpus, "qwen3.6-27b", "http://engine.invalid:40035")
    engine = doc["provenance"]["engine"]
    assert engine["endpoint"] == "http://engine.invalid:40035"
    assert engine["served_model"]["id"] == "qwen3.6-27b"
    assert engine["sampling_policy"].startswith("UNKNOWN")
    assert engine["weights_revision"].startswith("UNKNOWN")
    assert engine["tokenizer_and_chat_template_bytes"].startswith("NOT MEASURED")
    carried = engine["carried_from"]
    assert "REFERENCE estate" in carried["what"] and "another machine" in carried["what"]
    assert carried["served_model"]["id"] == "Qwen/Qwen3-0.6B"          # the packaged block, labelled
    assert "127.0.0.1:8000" in carried["served_model"]["source"]
    # G4 empty, and the coverage block says so per set
    assert doc["pins"]["tokenizer_hash"] == [] and doc["pins"]["chat_template_hash"] == []
    cov = doc["coverage"]
    assert cov["tokenizer_hash"].startswith("EMPTY") and cov["chat_template_hash"].startswith("EMPTY")
    assert cov["skill_card_hash"].startswith("derived here") and cov["system_prompt_hash"].startswith("derived here")
    assert cov["tool_roster_hash"].startswith("carried from the reference estate; checked on every trace")
    assert cov["settings_hash"].startswith("carried from the reference estate; checked on every trace")
    assert cov["sampling_policy"].startswith("UNKNOWN")
    out = capsys.readouterr().out
    assert "what an acceptance under this file covers" in out and "EMPTY — nothing checks them — G4" in out


def test_reference_model_pins_say_carried_and_checked_and_keep_g4(work, corpus, capsys):
    doc = pins_for(work, corpus, bootstrap.REFERENCE_MODEL, "http://127.0.0.1:8100")
    assert doc["pins"]["tokenizer_hash"] and doc["pins"]["chat_template_hash"]
    cov = doc["coverage"]
    assert cov["tokenizer_hash"].startswith("carried from the reference estate; NOT checked by any trace gate")
    assert cov["g6_expected_tail_ids"].startswith("carried from the reference estate (the reference model)")
    engine = doc["provenance"]["engine"]
    assert engine["endpoint"] == "http://127.0.0.1:8100"
    assert engine["tokenizer_and_chat_template_bytes"].startswith("carried from the reference estate")
    assert engine["carried_from"]["served_model"]["id"] == "Qwen/Qwen3-0.6B"
    out = capsys.readouterr().out
    assert "carried from the reference and checked on every trace G3, G7-settings, G6, G4" in out


def test_the_receiver_still_reads_the_pins_file_with_the_new_blocks(work, corpus, monkeypatch):
    """`coverage` and the rewritten `engine` block are outside `pins`: the
    library's loader must be indifferent to them."""
    monkeypatch.setattr(bootstrap, "derive_endpoint_pins",
                        lambda base, model, thinking: {"why": "no /tokenize (test)", "tail_ids": None})
    pins_for(work, corpus, "qwen3.6-27b", "http://engine.invalid:40035")
    proc = subprocess.run([sys.executable, "-c",
                           "from gsj_rollout import checks; print(len(checks.approved_set('system_prompt_hash')))"],
                          env={"GSJ_PINS_PATH": str(work / "estate" / "pins.gsj.json"), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.strip() == "1", proc.stderr


# ------------------------------------------------------------ the printout

def test_the_printout_says_which_row_the_one_liner_names(work, monkeypatch, capsys):
    ps = subprocess.CompletedProcess([], 0, "NAME\tSTATUS\tPORTS\n", "")
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: ps)
    monkeypatch.setattr(bootstrap, "corpus_path", lambda demo: Path("/corpus"))
    rec = {"forgejo": {"url": "http://127.0.0.1:3001", "container_url": "http://gsj-demo-forgejo:3000",
                       "owner": "gsj_staging", "read_token_env": "GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING"},
           "mcp": {"url": "http://127.0.0.1:8791", "container_url": "http://gsj-demo-mcp:8790"},
           "ports": {"rollout": 8080, "gateway": 8200, "receiver": 8300},
           "corpus": {"taskbank_rows": 6}}
    demo = {"inference": {"base_url": "http://127.0.0.1:8100", "model": "Qwen/Qwen3-0.6B"}}
    bootstrap.print_status(demo, "ok", rec)
    out = capsys.readouterr().out
    assert "--from-bank /corpus/taskbank.parquet --row 0" in out
    assert "(--row 0 is the bank's first row — this bank has 6 rows, 0–5; the README's" in out
    assert "walkthrough runs --row 2" in out
    assert "sessions/                       the gateway's per-episode scratch — Polar removes it after" in out
    assert "estate/artifacts/<session_id>/  the harness's per-episode artifacts + agent log" in out
