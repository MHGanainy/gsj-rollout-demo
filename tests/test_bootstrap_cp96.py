"""Library CP-96 — what round four found in bootstrap.py and preflight.py:
the Polar readiness probe as a class (a `docker exec` into one of this
estate's own Polar containers; a named fallback a `finally` removes; a
timeout that comes back as a sentence, and `up` goes on), `status` on the
record a failed `up` leaves behind (reports, never crashes), `--ingest-timeout`
forwarded, the submit recipe written to disk the moment it is derivable,
the storage driver named at the first Docker call, the pull heartbeat
naming the layer phase, and preflight's pre-`up` cure suppressed with its
exit codes stated.

Hermetic: no Docker, no endpoint — the `run` and `popen` seams are faked."""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import FakePull

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bootstrap = module('bootstrap')


@pytest.fixture
def work(tmp_path, monkeypatch):
    w = tmp_path / "work"
    monkeypatch.setattr(bootstrap, "WORK", w)
    monkeypatch.setattr(bootstrap, "LOCK", w / ".bootstrap.lock")
    monkeypatch.setattr(bootstrap, "RUNDIR", w / "runs" / "demo")
    monkeypatch.setattr(bootstrap, "ESTATE", w / "estate")
    monkeypatch.setattr(bootstrap, "POLAR_ENV", w / "polar.env")
    return w


# ------------------------------------------------------ the probe class

def test_in_net_python_execs_into_a_running_polar_container_and_creates_nothing(monkeypatch):
    """a1 twice and a2 once: the probe `docker run --rm`'d the 465 MiB Polar
    image under timeout=90 and died as a bare TimeoutExpired with all three
    Polar containers Running underneath. It execs into one of them now."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            running = cmd[-1] == "gsj-demo-polar-rollout"
            return subprocess.CompletedProcess(cmd, 0 if running else 1, "true\n" if running else "", "")
        assert cmd[:3] == ["docker", "exec", "gsj-demo-polar-rollout"] and cmd[3:5] == ["python", "-c"]
        return subprocess.CompletedProcess(cmd, 0, "rollout ok | receiver ok\n", "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    proc = bootstrap.in_net_python("print('x')", timeout=90)
    assert proc.returncode == 0 and "rollout ok" in proc.stdout
    assert not any(c[:2] == ["docker", "run"] or c[:2] == ["docker", "rm"] for c in calls)


def test_in_net_python_fallback_is_named_removed_in_a_finally_and_a_timeout_is_a_sentence(monkeypatch):
    """a2 found `friendly_hopper` in `docker ps -a` hours later: a killed
    `docker run --rm` never fires its --rm."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "No such object")
        if cmd[:2] == ["docker", "run"]:
            assert "--rm" not in cmd and cmd[2] == "--name" and cmd[3].startswith("gsj-demo-probe-")
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        assert cmd[:3] == ["docker", "rm", "-f"], cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    proc = bootstrap.in_net_python("print('x')", timeout=90)
    assert proc.returncode == bootstrap.PROBE_TIMEOUT_EXIT
    assert proc.stderr.startswith("the probe timed out after 90 s via a `docker run` of ")
    assert "copy-on-create" in proc.stderr and "may be perfectly healthy" in proc.stderr
    name = next(c[3] for c in calls if c[:2] == ["docker", "run"])
    assert ["docker", "rm", "-f", name] in calls and "still creating" not in proc.stderr


def test_reap_container_keeps_trying_and_the_timeout_names_a_container_it_could_not_reap(monkeypatch):
    monkeypatch.setattr(bootstrap.time, "sleep", lambda s: None)
    answers = iter([1, 0])
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, next(answers), "", ""))
    assert bootstrap.reap_container("gsj-demo-probe-1", wait_s=60) is True
    clock = iter([0.0, 0.0, 31.0])
    monkeypatch.setattr(bootstrap.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "No such container"))
    assert bootstrap.reap_container("gsj-demo-probe-2", wait_s=30) is False

    def fake_run(cmd, **kw):
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "No such object")
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return subprocess.CompletedProcess(cmd, 1, "", "No such container")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    monkeypatch.setattr(bootstrap, "reap_container", lambda name, wait_s=30: False)
    proc = bootstrap.in_net_python("print('x')", timeout=90)
    assert proc.returncode == bootstrap.PROBE_TIMEOUT_EXIT
    assert "the daemon is still creating gsj-demo-probe-" in proc.stderr and "`docker rm -f" in proc.stderr


def test_polar_up_goes_on_when_the_probe_itself_could_not_run(work, monkeypatch, capsys):
    """The estate underneath was healthy every time (`{"status":"ok","nodes":1}`
    — the exact condition being tested); the probe failing is not the
    estate failing. Say so, in the house style, and continue."""
    work.mkdir()
    (work / "estate").mkdir()
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(bootstrap, "in_net_python", lambda code, timeout=600.0: subprocess.CompletedProcess(
        [], bootstrap.PROBE_TIMEOUT_EXIT, "", "the probe timed out after 90 s via x"))
    monkeypatch.setattr(bootstrap, "estate_digest", lambda: "abc")
    bootstrap.polar_up({"ports": {"rollout": 8080, "gateway": 8200, "receiver": 8300}})
    out, err = capsys.readouterr()
    assert "the readiness probe could not run: the probe timed out after 90 s via x" in out
    assert "this is a check, not a phase — the estate stands" in out
    assert "docker exec gsj-demo-polar-rollout python -c" in out
    assert "FAIL" not in err and (work / "estate" / bootstrap.DIGEST_FILE_NAME).read_text() == "abc\n"


def test_polar_up_still_refuses_when_the_probe_ran_and_the_leg_is_not_up(work, monkeypatch, capsys):
    work.mkdir()
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(bootstrap, "in_net_python", lambda code, timeout=600.0: subprocess.CompletedProcess(
        [], 1, "rollout NOT READY | receiver ok\n", ""))
    with pytest.raises(SystemExit) as exc:
        bootstrap.polar_up({"ports": {"rollout": 8080, "gateway": 8200, "receiver": 8300}})
    assert exc.value.code == 1
    assert "the Polar leg did not come up" in capsys.readouterr().err


def test_check_engine_reads_the_probe_sentinel(monkeypatch):
    monkeypatch.setattr(bootstrap, "in_net_python", lambda code, timeout=600.0: subprocess.CompletedProcess(
        [], bootstrap.PROBE_TIMEOUT_EXIT, "", "the probe timed out after 30 s via x"))
    assert bootstrap.check_engine("http://e:1", "m").startswith("UNREACHABLE — the probe timed out")


# ----------------------------------------------- status on a partial record

def partial_record() -> dict:
    """What run.json holds after an `up` that died in the retrieval wait: the
    forgejo block and the compose block, no `mcp`, no `ports`."""
    return {"forgejo": {"mode": "created", "url": "http://127.0.0.1:3000",
                        "container_url": "http://gsj-demo-forgejo:3000", "owner": "gsj-staging",
                        "read_token_env": "GSJ_FORGEJO_READ_TOKEN_GSJ_STAGING"},
            "compose": {"mcp": {"image": "ghcr.io/mhganainy/gsj-mcp-service:0.5.0",
                                "container": "gsj-demo-mcp", "port": 8790}}}


def test_status_reports_a_partial_record_instead_of_dying_on_it(work, monkeypatch, capsys):
    """a2: `KeyError: 'mcp'` at bootstrap.py:1206 in exactly the state a
    failed `up` leaves behind — "status is excellent when the estate is
    whole and dies when it is broken, which is the reverse of when an
    operator needs it." The three lines it printed were already the right
    answer; now the rest follows."""
    ps = subprocess.CompletedProcess([], 0, "NAME\tSTATUS\tPORTS\ngsj-demo-forgejo\tUp 10 hours\t\n", "")
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: ps)
    bootstrap.print_status(None, None, partial_record())
    out, err = capsys.readouterr()
    assert "Traceback" not in out + err and "KeyError" not in out + err
    assert "the bring-up's record is PARTIAL" in out
    assert "forgejo    http://gsj-demo-forgejo:3000     case repos under /gsj-staging/" in out
    assert "mcp        created (ghcr.io/mhganainy/gsj-mcp-service:0.5.0), NOT recorded ready" in out
    assert "polar leg  not reached (no ports recorded" in out
    assert "re-run ./bootstrap.py up (resumable" in out
    assert "submit recipe: not derivable yet" in out


def test_status_names_the_recipe_on_disk_when_a_later_phase_failed(work, monkeypatch, capsys):
    ps = subprocess.CompletedProcess([], 0, "NAME\tSTATUS\tPORTS\n", "")
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: ps)
    (work / "estate").mkdir(parents=True)
    (work / "estate" / bootstrap.RECIPE_FILE_NAME).write_text("#!/bin/sh\n")
    bootstrap.print_status(None, None, partial_record())
    out = capsys.readouterr().out
    assert f"submit recipe: on disk at {work / 'estate' / bootstrap.RECIPE_FILE_NAME}" in out


def test_status_with_a_whole_record_still_prints_the_recipe_and_points_at_the_file(work, monkeypatch, capsys):
    ps = subprocess.CompletedProcess([], 0, "NAME\tSTATUS\tPORTS\n", "")
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: ps)
    monkeypatch.setattr(bootstrap, "corpus_path", lambda demo: Path("/corpus"))
    rec = {**partial_record(), "mcp": {"url": "http://127.0.0.1:8790", "container_url": "http://gsj-demo-mcp:8790"},
           "ports": {"rollout": 8080, "gateway": 8200, "receiver": 8300},
           "corpus": {"taskbank_rows": 6}}
    bootstrap.print_status({"inference": {"base_url": "http://e:1", "model": "m"}}, "ok", rec)
    out = capsys.readouterr().out
    assert "gsj-rollout submit --config /estate/rollout.yaml" in out
    assert f"is on disk at {work / 'estate' / bootstrap.RECIPE_FILE_NAME}" in out


# ------------------------------------ --ingest-timeout and the recipe on disk

def test_up_forwards_ingest_timeout_and_writes_the_recipe_before_the_polar_leg(work, monkeypatch, capsys):
    """a2: the library's REFUSED block prescribed `--ingest-timeout`; the demo's
    `up` took four flags and forwarded none of that name. And when a late
    phase fails the walkthrough's one-liner never prints — two strangers
    never got one — so it is written the moment it is derivable."""
    seen = {}
    monkeypatch.setattr(bootstrap, "check_docker", lambda: None)
    monkeypatch.setattr(bootstrap, "check_library", lambda: None)
    monkeypatch.setattr(bootstrap, "load_demo_config", lambda p: {"inference": {"base_url": "http://e:1", "model": "m"}})
    monkeypatch.setattr(bootstrap, "corpus_path", lambda demo: work / "corpus")
    monkeypatch.setattr(bootstrap, "phase_validate", lambda c: None)
    monkeypatch.setattr(bootstrap, "write_polar_env", lambda: None)
    monkeypatch.setattr(bootstrap, "ensure_image", lambda image, what: None)
    monkeypatch.setattr(bootstrap, "derive_pins", lambda *a, **k: None)
    monkeypatch.setattr(bootstrap, "decisions_drop_for", lambda c: (None, 0))
    monkeypatch.setattr(bootstrap, "write_answers", lambda *a, **k: work / "answers.yaml")
    monkeypatch.setattr(bootstrap, "bringup", lambda *args: seen.setdefault("bringup", list(args)))
    rec = {**partial_record(), "mcp": {"url": "u", "container_url": "cu"},
           "ports": {"rollout": 8080, "gateway": 8200, "receiver": 8300}, "corpus": {"taskbank_rows": 6}}
    monkeypatch.setattr(bootstrap, "load_run", lambda: rec)
    monkeypatch.setattr(bootstrap, "containerize_rollout_yaml", lambda demo, rec: "http://e:1")
    monkeypatch.setattr(bootstrap, "render_topology", lambda: None)
    monkeypatch.setattr(bootstrap, "estate_digest", lambda: "d")

    def failing_polar_up(rec, recreate=False):
        raise SystemExit(1)                     # the late phase that fails

    monkeypatch.setattr(bootstrap, "polar_up", failing_polar_up)
    args = SimpleNamespace(config="config.yaml", overwrite_repos=False, rebuild=True, retarget=False,
                           forgejo_image=None, ingest_timeout=5400.0)
    with pytest.raises(SystemExit):
        bootstrap._cmd_up(args)
    assert seen["bringup"] == ["up", "--answers", str(work / "answers.yaml"), "-y", "--rebuild",
                               "--ingest-timeout", "5400.0"]
    recipe = work / "estate" / bootstrap.RECIPE_FILE_NAME
    assert recipe.is_file() and recipe.stat().st_mode & 0o100
    text = recipe.read_text()
    assert text.startswith("#!/bin/sh\n") and "gsj-rollout submit --config /estate/rollout.yaml" in text
    assert f"-v {work / 'corpus'}:/corpus" in text and text.rstrip().endswith('--row 0 "$@"')
    assert f"the submit one-liner is on disk at {recipe}" in capsys.readouterr().out


def test_up_help_and_the_bringup_fail_text_name_ingest_timeout():
    proc = subprocess.run([sys.executable, str(ROOT / "bootstrap.py"), "up", "--help"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    text = " ".join(proc.stdout.split())
    assert "--ingest-timeout SECONDS" in text and "forwarded to the bring-up" in text
    source = (ROOT / "bootstrap.py").read_text()
    assert "--ingest-timeout <seconds> are forwarded from ./bootstrap.py up" in source


# ---------------------------------------------- the storage driver, at +17 s

def test_check_docker_names_a_copy_on_create_storage_driver_before_anything_runs(monkeypatch, capsys):
    """b2 and a2 priced vfs after the fact — ~13 GB per sandbox container, a
    600 s sandbox create budget blown; one `docker info` field says it at
    the first Docker call."""
    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "info", "--format"] and cmd[3] == "{{.Driver}}":
            return subprocess.CompletedProcess(cmd, 0, "vfs\n", "")
        return subprocess.CompletedProcess(cmd, 0, "29.0.0\n", "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: "/usr/bin/docker")
    bootstrap.check_docker()
    out = capsys.readouterr().out
    assert "storage driver 'vfs': every container is a full COPY of its image" in out
    assert "~13 GB per container" in out and "Continuing — slowly" in out


def test_check_docker_is_silent_about_an_overlay_driver(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, "overlay2\n" if "{{.Driver}}" in cmd else "29.0.0\n", ""))
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: "/usr/bin/docker")
    bootstrap.check_docker()
    assert "storage driver" not in capsys.readouterr().out


# ------------------------------------------------- the heartbeat's phase

PULL_LINES = ["0.5.0: Pulling from mhganainy/gsj-mcp-service\n",
              "a1b2c3d4e5f6: Pulling fs layer\n", "0f1e2d3c4b5a: Pulling fs layer\n",
              "a1b2c3d4e5f6: Downloading\n", "0f1e2d3c4b5a: Downloading\n",
              "a1b2c3d4e5f6: Download complete\n", "0f1e2d3c4b5a: Download complete\n",
              "a1b2c3d4e5f6: Extracting\n", "a1b2c3d4e5f6: Pull complete\n", "0f1e2d3c4b5a: Extracting\n"]


def test_pull_phase_summary_names_extraction_and_expects_no_bytes_there():
    layers = {}
    for line in PULL_LINES[:5]:
        bootstrap.pull_phase_tally(layers, line)
    assert bootstrap.pull_phase_summary(layers) == ("0/2 layers complete, 2 downloading", True)
    for line in PULL_LINES[5:]:
        bootstrap.pull_phase_tally(layers, line)
    text, expects = bootstrap.pull_phase_summary(layers)
    assert text.startswith("1/2 layers complete, 1 extracting — EXTRACTION") and expects is False


def test_ensure_image_heartbeat_names_the_phase_and_does_not_call_extraction_a_stall(monkeypatch, capsys):
    """a2: "26.0 KiB in the last 60s — the pipe is moving" printed through an
    extraction, when no bytes are expected; a1 counted `Download complete`
    against `Pull complete` by hand for forty minutes."""
    monkeypatch.setattr(bootstrap, "PULL_HEARTBEAT_S", 0.15)
    monkeypatch.setattr(bootstrap, "host_rx_bytes", lambda: 7)
    monkeypatch.setattr(bootstrap, "image_present", lambda image: False)
    monkeypatch.setattr(bootstrap, "popen", lambda cmd, **kw: FakePull(cmd, 0, lines=PULL_LINES, delay=0.4))
    bootstrap.ensure_image("example.invalid/big:1", "a test image")
    out = capsys.readouterr().out
    beats = [ln for ln in out.splitlines() if "still pulling example.invalid/big:1" in ln]
    assert beats, out
    assert all("1/2 layers complete, 1 extracting" in b and "as expected while the daemon extracts" in b
               for b in beats), beats
    assert "before killing anything" not in out and "a1b2c3d4e5f6: Pull complete" in out


def test_ensure_image_still_fails_loudly_with_docker_stderr(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "PULL_HEARTBEAT_S", 0.15)
    monkeypatch.setattr(bootstrap, "host_rx_bytes", lambda: None)
    monkeypatch.setattr(bootstrap, "image_present", lambda image: False)
    monkeypatch.setattr(bootstrap, "popen", lambda cmd, **kw: FakePull(cmd, 1, stderr="no such host\n", delay=0.2))
    with pytest.raises(SystemExit) as exc:
        bootstrap.ensure_image("example.invalid/big:1", "a test image")
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    assert "no such host" in err and "could not pull example.invalid/big:1" in err
    assert "byte counters are not readable here" in out


# ------------------------------------------------------------- preflight

def preflight_with(monkeypatch, tmp_path, *, pins: bool, config_extra: str = ""):
    """preflight.main() against a faked endpoint: /v1/models serves the
    model, the tool probe answers a tool_call, /tokenize renders prefix-
    extending turns, and the derivation says the served template's turn
    terminator is 248046."""
    preflight = module('preflight')
    cfg = tmp_path / "config.yaml"
    cfg.write_text("corpus: ./c\ninference:\n  base_url: http://e:1\n  model: qwen3.6-27b\n" + config_extra)
    pins_path = tmp_path / "work" / "estate" / "pins.gsj.json"
    if pins:
        pins_path.parent.mkdir(parents=True)
        pins_path.write_text(json.dumps({"pins": {"g6_expected_tail": ["<|im_end|>\n"],
                                                  "g6_expected_tail_ids": [[248046, 198]]}}))

    def http(url, payload=None, timeout=10.0):
        if url.endswith("/v1/models"):
            return 200, {"data": [{"id": "qwen3.6-27b", "max_model_len": 131072}]}
        if url.endswith("/v1/chat/completions"):
            return 200, {"choices": [{"message": {"tool_calls": [{"function": {"name": "add"}}]}}]}
        if url.endswith("/tokenize"):
            if payload and "messages" in payload:
                n = len(json.dumps(payload["messages"]))
                return 200, {"tokens": list(range(n))}
            return 200, {"tokens": [248046, 198]}
        return 200, {"prompt": "x"}

    monkeypatch.setattr(preflight, "http", http)
    monkeypatch.setattr(preflight, "_failed", False)
    monkeypatch.setattr(preflight, "HERE", tmp_path)     # never the repo's standing work/
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--config", str(cfg), "--pins", str(pins_path)])
    monkeypatch.syspath_prepend(str(ROOT))
    import bootstrap as real_bootstrap
    monkeypatch.setattr(real_bootstrap, "derive_endpoint_pins",
                        lambda base, model, thinking: {"why": None, "eot_id": 248046, "eot_text": "<|im_end|>"})
    return preflight


def test_preflight_before_up_warns_and_exits_zero_without_offering_the_config_cure(monkeypatch, tmp_path, capsys):
    """a2: the pre-`up` FAIL row offered two cures joined by "or", and the
    second — writing the id into config.yaml — is the one the README forbids
    in bold: "the tool wins by proximity". With no pins file the derivation
    has not run: no FAIL, no second cure, exit 0."""
    preflight = preflight_with(monkeypatch, tmp_path, pins=False)
    code = preflight.main()
    out = capsys.readouterr().out
    assert code == 0, out
    assert "[warn] end-of-turn id" in out and "the derivation has not run yet" in out
    assert "./bootstrap.py up derives [248046]" in out
    assert "Do NOT set end_of_turn_token_id in config.yaml" in out
    assert "or set end_of_turn_token_id" not in out and "[FAIL] end-of-turn id" not in out
    assert "preflight: no fatal mismatch found" in out


def test_preflight_still_fails_an_explicit_config_value_that_disagrees(monkeypatch, tmp_path, capsys):
    preflight = preflight_with(monkeypatch, tmp_path, pins=False, config_extra="end_of_turn_token_id: 151645\n")
    code = preflight.main()
    out = capsys.readouterr().out
    assert code == 1 and "[FAIL] end-of-turn id" in out and "config.yaml end_of_turn_token_id" in out


def test_preflight_docstring_states_the_exit_codes():
    text = (ROOT / "preflight.py").read_text()
    assert "Exit codes: 0 — no [FAIL] row" in text and "1 — at least one [FAIL] row" in text
    assert "a healthy endpoint exits 0 both before and after `up`" in text
