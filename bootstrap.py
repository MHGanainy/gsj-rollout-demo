#!/usr/bin/env python3
"""gsj-rollout-demo bootstrap — a corpus, a config, an inference endpoint,
and one command later: a running estate with the corpus ingested and
verified.

    ./bootstrap.py validate   # check the corpus tree, nothing stood up
    ./bootstrap.py up         # the whole estate: validate -> pins -> the
                              # library's bring-up (Forgejo -> scaffold ->
                              # MCP -> ingest -> taskbank -> verify) ->
                              # Polar -> status
    ./bootstrap.py status     # what is running, where, and how to stop it
    ./bootstrap.py down       # stop the estate (data survives)
    ./bootstrap.py down --wipe  # stop AND delete <work>/ — a fresh estate

Running `up` twice is safe: every step detects existing state and says so.
Every failure states what to do next — a bootstrap that fails mute has
failed twice.

The stranger's three inputs (config.yaml — see config.yaml.example):
a corpus in the contract's shape, an inference endpoint URL, and the
served model's name. Everything else about the estate is derived.

Since library 0.1.3 this script is a READER (library CP-61). The estate
itself — the git host, the owner and its tokens, the scaffold, the
retrieval service and its index, the taskbank, the round-trip verify, the
run record — is stood up by the library's own bring-up, `python -m
gsj_rollout.bringup` (the production tool, shipped in the wheel): this
script maps config.yaml's three values onto that tool's answers and runs
it. What it adds is exactly what the library's bring-up deliberately stops
short of: THIS estate's pins, derived from your corpus and your endpoint,
and the Polar leg — rollout server, gateway, receiver — as containers of
one published image, so no second checkout or venv is ever needed.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("bootstrap: PyYAML is missing. It rides the library install:\n"
          "  pip install 'gsj-harness-rollout-server>=0.1.4' pyarrow", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent

# ---- the estate's published artifacts, pinned -------------------------------
POLAR_IMAGE = "ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.3"
MCP_IMAGE = "ghcr.io/mhganainy/gsj-mcp-service:0.4.0"       # multi-arch since library CP-61
SANDBOX_IMAGE = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"   # linux/amd64 only (F-54)
LIB_MIN = (0, 1, 4)          # the floor: the bring-up that pulls its images and takes
                             # --forgejo-image / --polar-leg / --runs-dir (library CP-62)
REFERENCE_MODEL = "Qwen/Qwen3-0.6B"   # the estate every packaged pin came from

# ---- the run: the library's bring-up names everything after it -------------
RUN = "demo"                       # -> compose project gsj-demo, containers
NETWORK = f"gsj-{RUN}-net"         #    gsj-demo-forgejo / gsj-demo-mcp, this network
WORK = HERE / "work"
RUNDIR = WORK / "runs" / RUN       # the bring-up's run directory (./runs/<name>/ from its cwd)
ESTATE = WORK / "estate"           # the Polar leg's files: pins, rollout.yaml, topology
COMPOSE = HERE / "estate" / "compose.yaml"   # the Polar leg only (three containers)
POLAR_ENV = WORK / "polar.env"     # the Polar leg's non-secret compose values
POLAR_PROJECT = f"gsj-{RUN}-polar"
ROLLOUT_HOST, GATEWAY_HOST, RECEIVER_HOST = "polar-rollout", "polar-gateway", "receiver"

_T0 = time.monotonic()


def say(msg: str) -> None:
    print(f"[bootstrap +{time.monotonic() - _T0:6.1f}s] {msg}", flush=True)


def die(what: str, fix: str) -> "None":
    print(f"\nbootstrap: FAIL — {what}", file=sys.stderr)
    print(f"  what to do: {fix}", file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    if cmd[:2] == ["docker", "compose"]:
        kw.setdefault("env", scrubbed_env())
    return subprocess.run(cmd, text=True, **kw)


def compose_cmd(*args: str) -> list:
    # two env-files: the Polar leg's own values, then the bring-up's .env —
    # the secrets, KEY='value', read by compose's dotenv parser (quotes
    # stripped; `docker run --env-file` would NOT strip them)
    return ["docker", "compose", "-f", str(COMPOSE), "--env-file", str(POLAR_ENV),
            "--env-file", str(RUNDIR / ".env"), *args]


def in_net_python(code: str, timeout: float = 600.0) -> subprocess.CompletedProcess:
    """Run a python snippet on the estate network (the Polar leg publishes
    no host ports — from outside, you join the network; so does this script)."""
    return run(["docker", "run", "--rm", "--network", NETWORK,
                "--add-host", "host.docker.internal:host-gateway",
                POLAR_IMAGE, "python", "-c", code],
               capture_output=True, timeout=timeout)


# ---------------------------------------------------------------- preflights

def check_docker() -> None:
    if shutil.which("docker") is None:
        die("`docker` is not on PATH.",
            "install Docker (https://docs.docker.com/engine/install/) and re-run")
    probe = run(["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True)
    if probe.returncode != 0:
        die("the Docker daemon is not reachable.",
            "start Docker (or fix socket permissions), then re-run; "
            f"daemon said: {probe.stderr.strip().splitlines()[-1] if probe.stderr.strip() else 'nothing'}")
    probe = run(["docker", "compose", "version", "--short"], capture_output=True)
    if probe.returncode != 0:
        die("`docker compose` (v2 plugin) is missing.",
            "install the Compose plugin (https://docs.docker.com/compose/install/) and re-run")


def check_library() -> None:
    import warnings
    # the packaged-pins UserWarning is about trace-validation gates; this
    # estate derives its own pins and names them (GSJ_PINS_PATH) on every
    # leg that validates traces, so in this process it is pure noise
    warnings.filterwarnings("ignore", message="gsj_rollout.checks")
    try:
        import gsj_rollout  # noqa: F401
    except ImportError:
        die("the gsj-harness-rollout-server library is not importable from this python "
            f"({sys.executable}).",
            "pip install 'gsj-harness-rollout-server>=0.1.4' pyarrow  (same environment "
            "you run bootstrap.py from)")
    import gsj_rollout
    have = tuple(int(x) for x in gsj_rollout.__version__.split("."))
    if have < LIB_MIN:
        die(f"library {gsj_rollout.__version__} predates this demo's floor — 0.1.4 is "
            "the bring-up that pulls its images and takes --forgejo-image (library CP-62).",
            "pip install -U 'gsj-harness-rollout-server>=0.1.4' pyarrow")
    # the WHEEL shape: the bring-up, the pipeline and the packaged pins are
    # force-included at build time — a source/editable checkout of the
    # library has none of them under gsj_rollout/
    from importlib.util import find_spec
    root = Path(find_spec("gsj_rollout").origin).parent
    if find_spec("gsj_rollout.bringup") is None or not (root / "pins" / "pins.gsj.json").is_file():
        die(f"this python has the library as a source checkout ({root}), not the wheel — "
            "the bring-up, the corpus pipeline and the packaged pins ship only in the wheel.",
            "pip install 'gsj-harness-rollout-server>=0.1.4' pyarrow  (from PyPI, into the "
            "environment you run bootstrap.py from)")
    # what the bring-up refuses on, checked here BEFORE the image pulls
    try:
        import pyarrow  # noqa: F401 — the taskbank's parquet writer
    except ImportError:
        die("pyarrow is not importable from this python (the taskbank's parquet writer).",
            "pip install pyarrow  (same environment)")
    if shutil.which("git") is None:
        die("`git` is not on PATH (the bring-up scaffolds the corpus into git repos).",
            "install git and re-run")


def load_demo_config(path: Path) -> dict:
    if not path.is_file():
        die(f"{path} does not exist.",
            "copy config.yaml.example to config.yaml and fill in the three values")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        die(f"{path} is not valid YAML: {exc}", "fix the syntax and re-run")
    allowed = {"corpus", "inference", "context_window", "max_tokens",
               "end_of_turn_token_id", "thinking", "generation_prompt_glue_ids"}
    unknown = set(raw) - allowed
    if unknown:
        die(f"{path}: unknown key(s) {sorted(unknown)}.",
            f"allowed keys: {sorted(allowed)} — see config.yaml.example")
    for key in ("corpus", "inference"):
        if key not in raw:
            die(f"{path}: required key '{key}' is missing.",
                "see config.yaml.example — corpus (path), inference.base_url, inference.model")
    inf = raw["inference"]
    if not isinstance(inf, dict) or "base_url" not in inf or "model" not in inf:
        die(f"{path}: 'inference' must be a mapping with base_url and model.",
            "see config.yaml.example")
    bad = set(inf) - {"base_url", "model"}
    if bad:
        die(f"{path}: inference: unknown key(s) {sorted(bad)}.",
            "inference takes exactly base_url and model")
    for key in ("context_window", "max_tokens", "end_of_turn_token_id"):
        if key in raw and (isinstance(raw[key], bool)
                           or not isinstance(raw[key], int)):
            die(f"{path}: {key} must be an integer, got {raw[key]!r}.",
                f"e.g. {key}: 32768 — see config.yaml.example")
    if "generation_prompt_glue_ids" in raw:
        glue = raw["generation_prompt_glue_ids"]
        if not (isinstance(glue, list) and glue
                and all(isinstance(t, int) and not isinstance(t, bool)
                        for t in glue)):
            die(f"{path}: generation_prompt_glue_ids must be a non-empty "
                "list of token ids (YAML booleans like `on` are not ids).",
                "./preflight.py's template row prints the exact list when "
                "the stitch applies; delete the key if it does not")
    if "thinking" in raw:
        # YAML 1.1: bare off/no/false arrive as boolean False — the library
        # deliberately maps that to "off", so accept it; bare `on` (True) is
        # the clamp trap, rejected by name before the library ever sees it.
        if raw["thinking"] is False:
            raw["thinking"] = "off"
        elif raw["thinking"] is True:
            die(f"{path}: `thinking: on` (unquoted) is a YAML boolean, "
                "not a pi level.",
                "use   thinking: medium   (the conventional ON — every "
                "non-off pi level is wire-equivalent) or delete the key")
        elif raw["thinking"] not in (
                "off", "minimal", "low", "medium", "high", "xhigh", "max"):
            die(f"{path}: thinking: {raw['thinking']!r} is not a pi level.",
                "one of off|minimal|low|medium|high|xhigh|max — `medium` is "
                "the conventional ON; delete the key for off")
    if str(inf["base_url"]).rstrip("/").endswith("/v1"):
        die(f"{path}: inference.base_url must NOT end in /v1 — Polar's gateway "
            "appends /v1/chat/completions itself (a suffixed URL dies at run "
            "time as a 404 on /v1/v1/...).",
            f"drop the suffix: base_url: {str(inf['base_url']).rstrip('/')[:-3]}")
    return raw


def corpus_path(demo: dict) -> Path:
    p = Path(demo["corpus"])
    return p if p.is_absolute() else (HERE / p).resolve()


def corpus_sandbox_image(corpus: Path) -> str:
    """The image every task row names (corpus.yaml `sandbox_image`, a
    contract-required key): the bring-up checks THAT one is present."""
    doc = yaml.safe_load((corpus / "corpus.yaml").read_text()) or {}
    image = doc.get("sandbox_image")
    if not isinstance(image, str) or not image:
        die(f"{corpus / 'corpus.yaml'} names no sandbox_image.",
            f"set   sandbox_image: {SANDBOX_IMAGE}   (the published harness image)")
    return image


# ------------------------------------------------------------------ validate

def phase_validate(corpus: Path) -> None:
    say(f"validate — the contract, against {corpus} (host-side, before anything runs)")
    if not (corpus / "corpus.yaml").is_file():
        die(f"{corpus / 'corpus.yaml'} does not exist — is '{corpus}' a corpus root?",
            "point config.yaml's `corpus:` at a tree in the contract's shape, "
            "or generate the worked example: ./synthetic/make_corpus.py")
    env = dict(os.environ)
    # the pipeline never consults pins (the warning is about trace gates)
    env["PYTHONWARNINGS"] = "ignore:gsj_rollout.checks"
    proc = run([sys.executable, "-m", "gsj_rollout.ingest_corpus",
                "validate", "--corpus", str(corpus)], env=env)
    if proc.returncode != 0:
        die("the corpus tree failed validation — nothing was stood up, nothing runs "
            "against an invalid tree.",
            "fix the rows marked FAIL above (each names its file and rule) and re-run; "
            "the contract lives at "
            "https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md")


# -------------------------------------------------------------------- images

def daemon_arch() -> str:
    """The DAEMON's architecture — the one that picks pull platforms. The
    client python's platform.machine() lies in two real shapes (a Rosetta
    x86_64 python on an Apple Silicon Mac; Windows-on-ARM reporting 'ARM64'
    uppercase) and says nothing about a remote DOCKER_HOST; ask docker, fall
    back to the interpreter only if the daemon is unreachable."""
    proc = run(["docker", "version", "--format", "{{.Server.Arch}}"],
               capture_output=True)
    arch = proc.stdout.strip() if proc.returncode == 0 and proc.stdout else ""
    return arch or platform.machine().lower()


def image_present(image: str) -> bool:
    return run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


def ensure_image(image: str, what: str, amd64_only: bool = False) -> None:
    """Pull every published image up front: the first episode must not be
    the moment you learn your registry path is broken. (The bring-up now
    pulls a registry reference itself when absent — library CP-62 — but
    the Polar and sandbox images are this script's to manage, and the
    pre-pull keeps one progress line per image.) F-54's cure survives here: an
    ARM docker REFUSES a manifest with no arm64 variant instead of
    emulating — pull the amd64 variant explicitly and say so (Docker
    Desktop then runs it under emulation; measured at library CP-36, and
    since CP-61 only the sandbox image still needs it)."""
    if image_present(image):
        say(f"images — {image} present ({what})")
        return
    say(f"images — pulling {image} ({what})")
    if run(["docker", "pull", image]).returncode == 0:
        return
    if amd64_only and daemon_arch() in ("arm64", "aarch64"):
        say(f"arm64 — {image} publishes linux/amd64 only; pulling it explicitly "
            "for emulation (slower to start; episode speed is unaffected — the "
            "agent talks to your endpoint over HTTP)")
        if run(["docker", "pull", "--platform", "linux/amd64", image]).returncode == 0:
            return
    die(f"could not pull {image} (the docker error above is authoritative).",
        "if this host cannot reach ghcr.io, load the image out-of-band "
        "(docker save/load or skopeo) and re-run — local images are used as-is"
        + ("" if amd64_only else "; a `no matching manifest` error would mean the "
           "registry lost this image's variant for your platform — report it"))


# ---------------------------------------------------------------------- pins

def _endpoint_json(url: str, payload: dict, timeout: float = 15.0):
    """POST json -> (status|None, parsed|error-string). Never raises."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode(errors="replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")[:200]
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


# The probe history, shaped like the pi wire (system, user,
# assistant-with-tool-call, tool result). What matters is the template
# constants AROUND these strings, not the strings.
_PROBE_H1 = [
    {"role": "system", "content": "You are a careful assistant working a case file."},
    {"role": "user", "content": "Summarize the case status. Use the status tool first."},
]
_PROBE_H2 = _PROBE_H1 + [
    {"role": "assistant", "content": "Checking the status now.",
     "tool_calls": [{"id": "call_0001", "type": "function",
                     "function": {"name": "case_status",
                                  "arguments": "{\"case\": \"demo\"}"}}]},
    {"role": "tool", "tool_call_id": "call_0001",
     "content": "OPEN since 2024; 3 filings."},
]
_PROBE_MARKER = "GSJPROBEMARKERXYZ"


def derive_endpoint_pins(base_url: str, model: str, thinking: str) -> dict:
    """Derive the tokenizer-bound values from the SERVED artifact itself,
    over vLLM's /tokenize + /detokenize (the only API surface that renders
    the actual served chat template). Returns a dict with either every
    derived value or a `why` naming exactly what could not be derived —
    a value that cannot be derived is named, never defaulted (the CP-19
    packaged-pins rule; these feed gates).

      tail_ids/tail_text  what the template appends for a new assistant
                          turn (add_generation_prompt delta) — G6's subject
      eot_id/eot_text     the turn terminator: the first non-whitespace
                          token the template emits after assistant content
                          — the RENDER-side closer, the value
                          reconstruction matches against. It need NOT be
                          the id the engine stops on: Llama-3.1 stops
                          tool-call turns at <|eom_id|> while its template
                          re-renders them closed with <|eot_id|>, and the
                          derived render-side id is the correct one
                          (measured at CP-38; docs/MODEL-SURFACE.md owns
                          the full story)
    """
    base = base_url.rstrip("/")

    def tokenize_messages(msgs, agp):
        status, body = _endpoint_json(f"{base}/tokenize", {
            "model": model, "messages": msgs, "add_generation_prompt": agp,
            "chat_template_kwargs": {"enable_thinking": thinking != "off"}})
        if (status != 200 or not isinstance(body, dict)
                or not isinstance(body.get("tokens"), list)):
            return None, f"POST /tokenize (messages) answered {status}: {body}"
        return body["tokens"], None

    def detokenize(ids):
        status, body = _endpoint_json(f"{base}/detokenize",
                                      {"model": model, "tokens": ids})
        if (status != 200 or not isinstance(body, dict)
                or not isinstance(body.get("prompt"), str)):
            return None, f"POST /detokenize answered {status}: {body}"
        return body["prompt"], None

    a, why = tokenize_messages(_PROBE_H1, False)
    if why:
        return {"why": why + " — this endpoint cannot render its own chat "
                             "template over the API (not vLLM?)"}
    b, why = tokenize_messages(_PROBE_H1, True)
    if why:
        return {"why": why}
    if b[:len(a)] != a:
        return {"why": "the add_generation_prompt render does not extend the "
                       "plain render — this template's generation prompt is "
                       "not a suffix, so a G6 tail does not exist for it"}
    if len(b) == len(a):
        return {"why": "add_generation_prompt changes nothing — this template "
                       "ignores it (seen in the wild on simplified mirror "
                       "templates); no tail exists to pin, and G6 treats an "
                       "empty tail as fail-closed (every turn would offend), "
                       "so nothing is written"}
    tail = b[len(a):]
    tail_text, why = detokenize(tail)
    if why:
        return {"why": why}
    status, rt = _endpoint_json(f"{base}/tokenize", {
        "model": model, "prompt": tail_text, "add_special_tokens": False})
    if status != 200 or not isinstance(rt, dict) or rt.get("tokens") != tail:
        return {"why": f"the tail's text form does not round-trip "
                       f"({tail_text!r} -> {rt.get('tokens') if isinstance(rt, dict) else rt}, "
                       f"expected {tail}) — the ids are sound but the text pin "
                       "would lie; not writing either"}

    c, why = tokenize_messages(
        _PROBE_H1 + [{"role": "assistant", "content": _PROBE_MARKER}], False)
    if why:
        return {"why": why}
    if c[:len(a)] != a:
        return {"why": "an assistant-message render does not extend the "
                       "history render — cannot isolate the turn terminator"}
    block = c[len(a):]
    status, m = _endpoint_json(f"{base}/tokenize", {
        "model": model, "prompt": _PROBE_MARKER, "add_special_tokens": False})
    marker = m.get("tokens") if isinstance(m, dict) else None
    pos = next((k for k in range(len(block) - len(marker or []) + 1)
                if marker and block[k:k + len(marker)] == marker), None)
    if pos is None:
        return {"why": f"the probe marker's ids were not found in the "
                       f"assistant render ({block}) — cannot isolate the "
                       "turn terminator"}
    eot_id = None
    for tok_id in block[pos + len(marker):]:
        text, why = detokenize([tok_id])
        if why:
            return {"why": why}
        if text.strip():
            eot_id, eot_text = tok_id, text
            break
    if eot_id is None:
        return {"why": "no non-whitespace token follows assistant content in "
                       "this template — cannot derive the turn terminator"}
    status, models_body = _endpoint_json(f"{base}/tokenize", {
        "model": model, "prompt": "x", "add_special_tokens": False})
    max_len = models_body.get("max_model_len") if isinstance(models_body, dict) else None
    return {"tail_ids": tail, "tail_text": tail_text,
            "eot_id": eot_id, "eot_text": eot_text,
            "max_model_len": max_len, "why": None}


# pi embeds the workspace's AGENTS.md verbatim between these two markers
# in the system prompt it sends (pi 0.83.0, pinned by the sandbox image);
# the packaged capture holds the reference corpus's AGENTS.md there.
_AGENTS_OPEN = b'<project_instructions path="/workspace/AGENTS.md">\n'
_AGENTS_CLOSE = b"\n</project_instructions>"


def reference_capture() -> "tuple[bytes, int, int]":
    """The wheel's packaged G2 capture and the [i, j) span of its embedded
    AGENTS.md — read from the installed library (library CP-60 ships it
    beside the pins; CP-43's find_spec pattern), no demo-side copy since
    CP-61. Tripwires before trust: the capture must hash into the packaged
    approved set, and the AGENTS markers must occur exactly once."""
    from importlib.util import find_spec
    spec = find_spec("gsj_rollout")
    if spec is None or not spec.origin:
        die(f"the gsj-harness-rollout-server library is not importable from this python "
            f"({sys.executable}).",
            "pip install 'gsj-harness-rollout-server>=0.1.4' pyarrow  (same environment)")
    pins_root = Path(spec.origin).parent / "pins"
    cap = pins_root / "container" / "system_prompt.container.derived.txt"
    if not cap.is_file():
        die(f"the installed library ships no G2 capture at {cap}.",
            "pip install -U 'gsj-harness-rollout-server>=0.1.4' (the capture ships "
            "since 0.1.3)")
    ref_prompt = cap.read_bytes()
    approved = json.loads((pins_root / "pins.gsj.json").read_text())["pins"]["system_prompt_hash"]
    if hashlib.sha256(ref_prompt).hexdigest() not in approved:
        die("the library's packaged G2 capture does not hash into its own packaged "
            "system_prompt_hash — the installed wheel is inconsistent.",
            "reinstall the library (pip install -U --force-reinstall "
            "'gsj-harness-rollout-server>=0.1.4') and report it if that does not cure it")
    if ref_prompt.count(_AGENTS_OPEN) != 1 or ref_prompt.count(_AGENTS_CLOSE) != 1:
        die("the packaged G2 capture does not embed AGENTS.md between pi's "
            "<project_instructions> markers exactly once — the substitution "
            "derivation is unsound against this capture.",
            "a library whose capture came from a different pi: report it")
    i = ref_prompt.index(_AGENTS_OPEN) + len(_AGENTS_OPEN)
    return ref_prompt, i, ref_prompt.index(_AGENTS_CLOSE, i)


def derive_pins(corpus: Path, model: str, thinking: str,
                base_url: "str | None" = None) -> "int | None":
    from importlib.util import find_spec
    pins_root = Path(find_spec("gsj_rollout").origin).parent / "pins"
    # ADR-0024: a non-off thinking level needs the thinking-on pins on both
    # law-6 legs; the pins document's own `mode` key keeps the receiver's
    # archive stamp truthful about which mode landed each trace.
    packaged = (pins_root / "thinking-on" / "pins.gsj.json"
                if thinking != "off" else pins_root / "pins.gsj.json")
    doc = json.loads(packaged.read_text())

    ref_prompt, i, j = reference_capture()
    if hashlib.sha256(ref_prompt).hexdigest() not in doc["pins"]["system_prompt_hash"]:
        die(f"{packaged} does not pin the packaged G2 capture — the library's two "
            "packaged pins documents disagree about the reference system prompt.",
            "reinstall the library and report it if that does not cure it")
    ref_agents = ref_prompt[i:j]
    corpus_agents = (corpus / "AGENTS.md").read_bytes()
    derived_prompt = ref_prompt[:i] + corpus_agents + ref_prompt[j:]
    doc["pins"]["system_prompt_hash"] = [hashlib.sha256(derived_prompt).hexdigest()]

    cards = sorted(
        hashlib.sha256(card.read_bytes()).hexdigest()
        for card in sorted((corpus / "skills").glob("*/SKILL.md")))
    doc["pins"]["skill_card_hash"] = cards

    doc["derived_at"] = "gsj-rollout-demo bootstrap (G1 from the corpus's skill cards; " \
                        "G2 by AGENTS.md byte-substitution on the packaged reference " \
                        "capture; all other sets are the reference estate's)"

    # This generated artifact must not claim the reference estate's
    # provenance for values derived here (audit C11): the estate identity,
    # the walk status, and the rewritten sets' provenance blocks follow the
    # values. Sets that DO keep reference values keep their reference
    # provenance blocks — those say which estate measured them.
    doc["host"] = (
        "this gsj-rollout-demo estate — pins.gsj.json generated by "
        "./bootstrap.py up on this host. G1/G2 are derived HERE from the "
        "corpus; each remaining set is derived HERE from the endpoint's "
        "own render, carried from the reference estate, or emptied on "
        "purpose — the provenance blocks record which, and the derived_at "
        "line narrates what this run derived, carried, or could not "
        "derive.")
    doc["walk_status"] = {
        "derive": "done at every ./bootstrap.py up — this file is "
                  "regenerated each run; the reference estate's walk "
                  "history does not apply to it",
        "re_pin": "not applicable — never edit this file: change the "
                  "corpus or config.yaml and re-run ./bootstrap.py up",
        "first_episode_validate": "yours — the receiver validates every "
                  "episode against this file; ./read.py quarantine "
                  "explains any rejection",
    }
    prov = doc.setdefault("provenance", {})
    prov["skill_card_hash"] = {
        "algo": "sha256_bytes",
        "artifacts": sorted(f"<corpus>/{card.relative_to(corpus)}"
                            for card in (corpus / "skills").glob("*/SKILL.md")),
        "notes": "G1 — derived by this bootstrap from THIS corpus's skill "
                 "cards (sha256 of each card's bytes), replacing the "
                 "reference estate's set.",
    }
    prov["system_prompt_hash"] = {
        "algo": "sha256_bytes",
        "artifacts": ["the installed library's gsj_rollout/pins/container/"
                      "system_prompt.container.derived.txt with its "
                      "<project_instructions path=\"/workspace/AGENTS.md\"> span "
                      "replaced by <corpus>/AGENTS.md"],
        "notes": "G2 — derived by this bootstrap: byte-substitution of "
                 "this corpus's AGENTS.md into the packaged reference "
                 "capture (which embeds the reference AGENTS.md between "
                 "pi's markers exactly once — verified before substituting).",
    }
    if "non_g6_sets" in prov:
        # the thinking-on packaged doc carries one collective block whose
        # inherited-byte-equal claim is about the two PACKAGED pins files,
        # not this generated one — where G1/G2 (and, non-reference, G4)
        # have just diverged from it by design
        carried = ["settings_hash", "tool_roster_hash"] + (
            ["tokenizer_hash", "chat_template_hash"]
            if model == REFERENCE_MODEL else [])
        prov["non_g6_sets"] = {
            "notes": "Rewritten by this bootstrap (the packaged block's "
                     "byte-equal claim describes the two packaged pins "
                     "files, not this generated one): "
                     + ", ".join(carried) +
                     " are carried from the reference estate's measured "
                     "values; every other set's own block records who "
                     "derived or emptied it here."}

    derived_eot = None
    if model != REFERENCE_MODEL:
        # G4's two hashes CANNOT be derived over an API — they are the
        # bytes of tokenizer.json and of the served template, which no
        # endpoint exposes — and the reference estate's values would be a
        # lie for this model whether or not the endpoint derivation below
        # succeeds (audit W6). Named, not defaulted (empty approved sets;
        # no receiver gate reads them — their gate is the estate-side
        # walk, docs/MODEL-SURFACE.md says how).
        doc["pins"]["tokenizer_hash"] = []
        doc["pins"]["chat_template_hash"] = []
        doc["derived_at"] += (
            f"; G4's tokenizer/chat-template hashes emptied for {model!r} "
            "(not derivable over an API)")
        for key, ref_algo in (("tokenizer_hash", "git_blob_oid"),
                              ("chat_template_hash", "sha256_bytes")):
            prov[key] = {
                # the thinking-on packaged doc carries no per-key G4
                # provenance block, so the reference algo is the fallback
                "algo": prov.get(key, {}).get("algo", ref_algo),
                "artifacts": [],
                "notes": "EMPTY on purpose: not derivable over the API and "
                         "the reference estate's value would be a lie for "
                         f"{model!r}. Derive from a local snapshot "
                         "(docs/MODEL-SURFACE.md) if you want the "
                         "estate-side G4 walk."}
    if model != REFERENCE_MODEL and base_url:
        derived = derive_endpoint_pins(base_url.rstrip("/"), model, thinking)
        if derived["why"] is None:
            doc["pins"]["g6_expected_tail"] = [derived["tail_text"]]
            doc["pins"]["g6_expected_tail_ids"] = [derived["tail_ids"]]
            prov["g6_expected_tail"] = {
                "algo": "verbatim_text",
                "artifacts": [f"{base_url}/detokenize over the derived tail ids"],
                "notes": f"Derived by this bootstrap from the SERVED template: the "
                         f"add_generation_prompt delta of a two-turn probe render, "
                         f"mode `thinking: {thinking}`. Round-trips through "
                         f"/tokenize. On a non-Qwen family this pin asserts "
                         f"TEMPLATE INTEGRITY of every assistant-turn opening — "
                         f"not thinking-off (that meaning is Qwen-specific)."}
            prov["g6_expected_tail_ids"] = {
                "algo": "token_ids",
                "artifacts": [f"{base_url}/tokenize (messages form) against "
                              f"{model!r}, chat_template_kwargs enable_thinking="
                              f"{str(thinking != 'off').lower()}"],
                "notes": "The generation-prompt suffix under the served "
                         "template, derived at bootstrap time. G6 compares "
                         "every assistant-turn opening against exactly this."}
            doc["derived_at"] += (
                f"; G6 tail + end-of-turn id derived from the endpoint's own "
                f"template render ({base_url}/tokenize) for {model!r}")
            derived_eot = derived["eot_id"]
            say(f"pins — {model!r} is not the reference model; derived from the "
                f"endpoint's own template render:")
            say(f"pins —   g6_expected_tail_ids = {derived['tail_ids']}  "
                f"({derived['tail_text']!r})")
            say(f"pins —   end_of_turn_token_id = {derived['eot_id']}  "
                f"({derived['eot_text']!r}) -> rollout.yaml builder")
            say("pins — NOT derivable and left empty, on purpose: G4's "
                "tokenizer/chat-template hashes (byte identities no API exposes "
                "— docs/MODEL-SURFACE.md has the local-snapshot walk). Also "
                "still yours to own: sampling defaults (engine-side, "
                "unprobeable) and the template's prefix-extension property — "
                "./preflight.py probes that one, run it before spending "
                "episodes.")
        else:
            # the artifact itself must record the failure, not just the
            # console (the console scrolls away; the pins file is what an
            # operator opens after the G6 quarantine this path predicts)
            doc["derived_at"] += (
                f"; G6 tail + end_of_turn_token_id derivation from the "
                f"endpoint FAILED for {model!r} — the REFERENCE estate's "
                f"G6 values remain (episodes will likely quarantine at "
                f"G6); re-run ./bootstrap.py up with the endpoint live")
            say(f"pins — NOTE: your model is {model!r}, not the reference "
                f"{REFERENCE_MODEL}, and deriving the tokenizer-bound pins from "
                f"the endpoint FAILED: {derived['why']}")
            say("pins — the G6 tail and builder.end_of_turn_token_id remain the "
                "REFERENCE estate's values, so the first episode will likely be "
                "quarantined at G6 naming those digests — the gate working, not "
                "an accident. G4's tokenizer/chat-template hashes are emptied "
                "either way (never derivable over an API; the reference's "
                "values would be a lie for your model). Cure: bring the "
                "endpoint up (vLLM exposes "
                "/tokenize and /detokenize; those are all the derivation "
                "needs) and re-run ./bootstrap.py up, or derive from a local "
                "snapshot per docs/MODEL-SURFACE.md.")

    out = ESTATE / "pins.gsj.json"
    out.write_text(json.dumps(doc, indent=2) + "\n")
    say(f"pins — derived for THIS estate at {out}: {len(cards)} skill card(s) approved "
        f"(G1), system prompt re-derived for your AGENTS.md (G2); mode "
        f"{doc.get('mode', 'thinking-off')} (from config `thinking: {thinking}`)")
    if corpus_agents == ref_agents:
        say("pins — your AGENTS.md is the reference text, so G2 equals the packaged pin")
    return derived_eot


# --------------------------------------------------- the library's bring-up

def write_answers(demo: dict, corpus: Path, derived_eot: "int | None") -> Path:
    """config.yaml's three values, mapped onto the bring-up's answers file
    (keys are its long flag names): everything else it asks — owner,
    create-vs-adopt, ports, embedding identity, chunking — takes the
    tool's own default, which is what the demo estate is."""
    answers = {
        "corpus": str(corpus),
        "name": RUN,
        "forgejo": "create",           # the demo always CREATES its estate
        "mcp": "create",
        "mcp_image": MCP_IMAGE,        # pre-pulled above for the progress line — the
                                       # bring-up pulls a registry ref when absent anyway
        "engine_url": str(demo["inference"]["base_url"]).rstrip("/"),
        "engine_model": demo["inference"]["model"],
        "thinking": str(demo.get("thinking", "off")),
        # the gateway's public URL must be ONE address the rollout server and
        # every sandbox dial (library CP-03); all three are containers on the
        # estate network here, so the compose DNS name is that address and the
        # bring-up's host-address probe is skipped
        "gateway_host": GATEWAY_HOST,
        # library CP-62: Polar's leg runs in containers here, so the
        # bring-up binds 0.0.0.0 and writes the conventional ports unscanned
        # instead of scanning HOST ports for a leg that never uses them (its
        # `8080 is busy on this host; using 8081` line, library wishlist 51 (h));
        # containerize_rollout_yaml re-addresses the same values either way
        "polar_leg": "container",
    }
    # every harness value is answered on EVERY run — an omitted answer would
    # take the previous run's recorded value, not the library default, and
    # config.yaml (not run.json) is the source of truth here: a key deleted
    # from it, or a model switched back to the reference, must take effect
    from gsj_rollout.config import BuilderConfig, HarnessConfig
    answers["context_window"] = int(demo.get("context_window", HarnessConfig().context_window))
    answers["max_tokens"] = int(demo.get("max_tokens", HarnessConfig().max_tokens))
    if "end_of_turn_token_id" in demo:
        explicit = int(demo["end_of_turn_token_id"])
        answers["end_of_turn_token_id"] = explicit
        if derived_eot is not None and derived_eot != explicit:
            say(f"config — WARNING: config.yaml pins end_of_turn_token_id "
                f"{explicit}, but the endpoint's own template render derives "
                f"{derived_eot}. The explicit value wins; if it is wrong, "
                "reconstruction mis-splits every multi-turn episode. Delete "
                "the key from config.yaml to use the derived value.")
    elif derived_eot is not None:
        answers["end_of_turn_token_id"] = int(derived_eot)
    else:
        # the reference model's id (the library default) — also what a
        # non-reference model gets when the endpoint derivation failed
        # (derive_pins said so out loud; the pins file records it)
        answers["end_of_turn_token_id"] = BuilderConfig().end_of_turn_token_id
    out = WORK / "bringup-answers.yaml"
    out.write_text("# GENERATED by bootstrap.py from config.yaml — the answers handed to\n"
                   "# `python -m gsj_rollout.bringup up --answers` (no secrets here; the\n"
                   f"# bring-up mints its own into {RUNDIR / '.env'}).\n"
                   + yaml.safe_dump(answers, sort_keys=False))
    return out


def bringup(*args: str) -> None:
    """The library's own bring-up (gsj_rollout.bringup, in the wheel since
    0.1.3), run as a subprocess from work/: its runs land under
    ./runs/<name>/ of the cwd — the demo keeps that default (0.1.4 grew
    --runs-dir; the cwd shape needs no flag), so work/runs/demo/ is this
    estate's run directory. GSJ_PINS_PATH names THIS estate's pins —
    derived before the call — which silences the library's import-time
    packaged-pins warning; the bring-up's own G1 check reads the same
    named set.
    Its closing block prescribes host-run Polar commands; the demo runs
    that leg itself, in containers, right after — so that block (from its
    `next —` line, after the `== run <name> ==` header) is not
    echoed."""
    env = {**scrubbed_env(), "GSJ_PINS_PATH": str(ESTATE / "pins.gsj.json")}
    verb = args[0]
    say("bring-up — python -m gsj_rollout.bringup " + " ".join(args)
        + f"  (the library's production tool; cwd {WORK})")
    proc = subprocess.Popen([sys.executable, "-m", "gsj_rollout.bringup", *args],
                            cwd=WORK, env=env, stdout=subprocess.PIPE, text=True, bufsize=1)
    header = muted = False
    for line in proc.stdout:
        header = header or line.startswith(f"== run {RUN} ==")
        if header and line.startswith("next — "):
            muted = True
        if not muted:
            print(line, end="", flush=True)
    proc.wait()
    if proc.returncode != 0:
        die(f"the library's bring-up exited {proc.returncode} on `{verb}` — its REFUSED "
            "block above names what it found, what it expected, and what to do.",
            f"fix what it names and re-run ./bootstrap.py {verb} — every phase is "
            "idempotent. If it names a bring-up flag this script does not pass "
            "(--overwrite-repos, --rebuild, --retarget and --forgejo-image <ref> are "
            "forwarded from ./bootstrap.py up; others are not), either pass one of those, run "
            "`./bootstrap.py down --wipe` for a fresh estate, or run the tool "
            "directly: python -m gsj_rollout.bringup up --help")


def scrubbed_env() -> dict:
    """The environment for the bring-up and for compose, minus every estate
    secret name: a value exported into this shell (a sourced .env of an
    earlier estate, say) would otherwise beat the run's own .env in
    compose's interpolation — silently, mid-episode."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith("GSJ_FORGEJO_") and k != "GSJ_MCP_TOKEN_SECRET"}


def load_run() -> dict:
    rec = RUNDIR / "run.json"
    if not rec.is_file():
        die(f"the bring-up left no record at {rec}.",
            "this is a bootstrap bug — report it with the output above")
    return json.loads(rec.read_text())


# ------------------------------------------------------------ rollout config

def containerize_rollout_yaml(demo: dict, rec: dict) -> str:
    """The bring-up's rollout.yaml addresses a Polar that runs on the
    host (loopback rollout server and receiver, host paths). This estate
    runs that leg as three containers of one image on the estate network,
    so the demo re-addresses exactly those values and keeps everything
    else the bring-up wrote — the credentialed clone (clone_credential_env
    names the read token; the value stays in the run's .env), the
    in-network Forgejo/MCP URLs, the harness values, the ports."""
    src = yaml.safe_load((RUNDIR / "rollout.yaml").read_text())
    cfg = json.loads(json.dumps(src))          # a deep copy
    est = cfg["estate"]
    if est.get("clone_credential_env") != rec["forgejo"]["read_token_env"]:
        die("the bring-up's rollout.yaml does not name the read token the run "
            "minted (estate.clone_credential_env).",
            "this is a bootstrap bug — report it with work/runs/demo/rollout.yaml")
    base_url = str(demo["inference"]["base_url"]).rstrip("/")
    rewritten = re.sub(r"^(https?://)(localhost|127\.0\.0\.1)(?=[:/]|$)",
                       r"\1host.docker.internal", base_url)
    if rewritten != base_url:
        say(f"engine — {base_url} is host-local; inside containers it is reached as "
            f"{rewritten} (the gateway maps host.docker.internal to your host)")
    est["serving_base_url"] = rewritten
    ro = cfg["polar"]["rollout"]
    ro["host"], ro["public_url"] = "0.0.0.0", f"http://{ROLLOUT_HOST}:{ro['port']}"
    gw = cfg["polar"]["gateway"]
    if gw.get("public_url") != f"http://{GATEWAY_HOST}:{gw['port']}":
        die(f"the bring-up wrote gateway.public_url {gw.get('public_url')!r}; the demo "
            f"asked for http://{GATEWAY_HOST}:{gw['port']}.",
            "this is a bootstrap bug — report it with work/runs/demo/rollout.yaml")
    rc = cfg["receiver"]
    rc["host"], rc["public_url"] = "0.0.0.0", f"http://{RECEIVER_HOST}:{rc['port']}"
    rc["traces_dir"] = "/estate/traces"
    cfg["harness"]["artifacts_dir"] = "/estate/artifacts"
    if "generation_prompt_glue_ids" in demo:
        glue = [int(t) for t in demo["generation_prompt_glue_ids"]]
        cfg.setdefault("builder", {})["generation_prompt_glue_ids"] = glue
        say(f"config — glue stitch armed: reconstruction re-inserts "
            f"{glue} at each turn opening (set from config.yaml because "
            "./preflight.py measured a constant template divergence)")
    text = ("# GENERATED by bootstrap.py — do not edit; edit config.yaml and re-run\n"
            "# ./bootstrap.py up. The library's bring-up wrote work/runs/demo/rollout.yaml\n"
            "# for a host-run Polar; this copy re-addresses the rollout server, the\n"
            "# receiver and the paths for the three containers that run that leg here.\n"
            "# Schema: the library's `one YAML` (gsj_rollout/config.py). Secrets are\n"
            f"# named, never written: {est['clone_credential_env']} and\n"
            f"# {est['mcp_token_secret_env']} live in work/runs/demo/.env.\n"
            + yaml.safe_dump(cfg, sort_keys=False))
    (ESTATE / "rollout.yaml").write_text(text)
    # the receiver's `serve` re-renders topology.rendered.yaml beside ITS
    # config at every start; Polar's two containers read the one rendered
    # below, so the receiver gets its own copy in its own directory and the
    # two never alias (library wishlist 51 (g))
    (ESTATE / "receiver").mkdir(exist_ok=True)
    (ESTATE / "receiver" / "rollout.yaml").write_text(text)
    say(f"config — rollout.yaml re-addressed for containers at {ESTATE / 'rollout.yaml'}")
    return rewritten


def render_topology() -> None:
    # rendered by the image's own library — the version the rollout server
    # and the receiver will read it with
    proc = run(["docker", "run", "--rm", "-v", f"{ESTATE}:/estate",
                "-e", "GSJ_PINS_PATH=/estate/pins.gsj.json", POLAR_IMAGE,
                "gsj-rollout", "serve", "--config", "/estate/rollout.yaml",
                "--render-only"], capture_output=True)
    if proc.returncode != 0:
        die("the library rejected the generated rollout.yaml.",
            f"this is a bootstrap bug — report it with this output:\n{proc.stderr}")
    say("config — Polar topology rendered (topology.rendered.yaml)")


# --------------------------------------------------------------------- polar

def write_polar_env() -> None:
    WORK.mkdir(exist_ok=True)
    POLAR_ENV.write_text(f"GSJ_DEMO_WORK={WORK}\n"
                         f"GSJ_DEMO_SESSIONS={WORK / 'sessions'}\n"
                         f"GSJ_POLAR_IMAGE={POLAR_IMAGE}\n")
    for d in (WORK / "sessions", WORK / "traces", ESTATE, ESTATE / "artifacts"):
        d.mkdir(exist_ok=True)


def estate_digest() -> str:
    """The generated files the Polar services read at START (the receiver
    reads pins at construction — the archive's mode stamp; the rollout server
    reads the rendered topology). When these change on a running estate,
    `up -d` alone would leave the services running on the OLD bytes. The
    comparison baseline is the digest RECORDED at the last successful polar
    bring-up (work/estate/.polar-digest) — not the disk at the start of this
    run, which an interrupted `up` could have already overwritten."""
    digest = hashlib.sha256()
    for name in ("pins.gsj.json", "rollout.yaml", "topology.rendered.yaml"):
        f = ESTATE / name
        if f.is_file():
            digest.update(name.encode() + f.read_bytes())
    return digest.hexdigest()


DIGEST_FILE_NAME = ".polar-digest"


def polar_up(rec: dict, recreate: bool = False) -> None:
    say("polar — docker compose up (rollout server, gateway, receiver)"
        + (" — generated estate files changed since the last bring-up, so "
           "the three are RECREATED (the receiver reads pins at start — "
           "the archive's mode stamp depends on it)" if recreate else ""))
    up = ["up", "-d"] + (["--force-recreate"] if recreate else [])
    if run(compose_cmd(*up)).returncode != 0:
        die("`docker compose up` of the Polar services failed.",
            f"the compose error above is authoritative; if the pull failed, load {POLAR_IMAGE} "
            "out-of-band and re-run")
    ports = rec["ports"]
    code = (
        "import httpx,sys,time\n"
        "deadline=time.time()+60\n"
        "ok_r=ok_g=False\n"
        "while time.time()<deadline and not(ok_r and ok_g):\n"
        "    try:\n"
        f"        h=httpx.get('http://{ROLLOUT_HOST}:{ports['rollout']}/health',timeout=3).json()\n"
        "        ok_r = h.get('status')=='ok' and h.get('nodes',0)>=1\n"
        "    except Exception: pass\n"
        "    try:\n"
        f"        httpx.get('http://{RECEIVER_HOST}:{ports['receiver']}/',timeout=3); ok_g=True\n"
        "    except Exception: pass\n"
        "    time.sleep(2)\n"
        "print('rollout ok' if ok_r else 'rollout NOT READY',"
        "'| receiver ok' if ok_g else '| receiver NOT READY',flush=True)\n"
        "sys.exit(0 if ok_r and ok_g else 1)\n")
    if in_net_python(code, timeout=90).returncode != 0:
        die("the Polar leg did not come up (rollout /health with a registered node, "
            "and a listening receiver, within 60 s).",
            "docker logs gsj-demo-polar-rollout / gsj-demo-polar-gateway / "
            "gsj-demo-receiver — the gateway registers itself with the rollout server; "
            "no node usually means the gateway crashed (the receiver's log opens with "
            "the library's `run Polar's two processes yourself` block: not for you — "
            "those two ARE the containers beside it)")
    say("polar — rollout server reports its gateway node; receiver is listening")
    (ESTATE / DIGEST_FILE_NAME).write_text(estate_digest() + "\n")


def check_engine(url: str, model: str) -> str:
    """The endpoint as a CONTAINER reaches it (the bring-up probed it from
    the host; the gateway dials it from inside the estate network)."""
    code = (
        "import httpx,sys\n"
        f"r=httpx.get('{url}/v1/models',timeout=10)\n"
        "ids=[m.get('id') for m in r.json().get('data',[])]\n"
        "print(','.join(ids))\n"
        f"sys.exit(0 if {model!r} in ids else 3)\n")
    try:
        proc = in_net_python(code, timeout=30)
    except subprocess.TimeoutExpired:
        return "UNREACHABLE"
    if proc.returncode == 0:
        return "ok"
    if proc.returncode == 3:
        return f"reachable, but served models are [{proc.stdout.strip()}]"
    return "UNREACHABLE"


# -------------------------------------------------------------------- status

def print_status(demo: "dict | None", engine_state: "str | None",
                 rec: "dict | None") -> None:
    print("\n== the estate ==")
    for project in (f"gsj-{RUN}", POLAR_PROJECT):
        ps = run(["docker", "compose", "-p", project, "ps", "--format",
                  "table {{.Name}}\t{{.Status}}\t{{.Ports}}"], capture_output=True)
        body = "\n".join(ps.stdout.rstrip().splitlines()[1:])
        print(body or f"({project}: nothing running — ./bootstrap.py up)")
    if rec is None:
        print(f"\n(no bring-up record at {RUNDIR / 'run.json'} — ./bootstrap.py up)")
    else:
        fj, mcp, ports = rec["forgejo"], rec["mcp"], rec["ports"]
        owner = fj["owner"]
        print(f"""
the library's bring-up created Forgejo and the retrieval service on 127.0.0.1
host ports (its own recipe); the Polar leg publishes none. From inside the
estate network (docker run --rm --network {NETWORK} <image> ...):
  forgejo    {fj['container_url']}     case repos under /{owner}/   (host: {fj['url']})
  mcp        {mcp['container_url']}        retrieval; /health for state   (host: {mcp['url']})
  rollout    http://{ROLLOUT_HOST}:{ports['rollout']}         submit dials this
  gateway    http://{GATEWAY_HOST}:{ports['gateway']}         episodes' OpenAI-compatible proxy
  receiver   http://{RECEIVER_HOST}:{ports['receiver']}              traces land here first

on disk (all under {WORK}):
  runs/{RUN}/.env                 every secret of the estate, KEY='value', mode 0600 — the only
                                  place a value is written on purpose (the retrieval service's
                                  clone cache under runs/{RUN}/mcp-data/ also carries the read
                                  token in its bare clones' config — library wishlist 47 — which
                                  is why the whole run directory is mode 0700)
  runs/{RUN}/run.json             the bring-up's record: what it created, every URL, no values
  runs/{RUN}/rollout.yaml         the bring-up's config (for a host-run Polar; kept as written)
  estate/rollout.yaml             the same config, re-addressed for the Polar containers
  estate/pins.gsj.json            THIS estate's approved sets (GSJ_PINS_PATH)
  traces/                         validated traces (receiver-side leg)
  sessions/                       per-episode session dirs + agent logs

stop:      ./bootstrap.py down          (data survives)
reset:     ./bootstrap.py down --wipe   (deletes {WORK})
re-run:    ./bootstrap.py up            (idempotent — safe on a running estate)""")
    if engine_state is not None and demo is not None:
        mark = "ok" if engine_state == "ok" else f"NOT OK — {engine_state}"
        print(f"\nengine     {demo['inference']['base_url']}  ->  {mark} (dialed from a container)")
        if engine_state != "ok":
            print("  what to do: the estate stands either way, but episodes need the "
                  "endpoint.\n  Serve the model under EXACTLY the configured name "
                  f"({demo['inference']['model']!r} must appear in GET /v1/models), "
                  "then re-run ./bootstrap.py up (idempotent) or just retry an episode.")
        print("""
the endpoint must satisfy (the library's CP-04' engine legs):
  - a tool-call parser (the agent's tools arrive as OpenAI tool definitions)
  - a context window >= the config's harness.context_window (default 32768)
  - pinned sampling defaults: pi sends NO sampling parameters, so YOUR
    server's generation defaults ARE the sampling policy — pin them
    (e.g. vLLM --generation-config) or your rollouts sample at whatever
    the engine happens to default to.""")
    if demo is not None and rec is not None:
        corpus = corpus_path(demo)
        read_env = rec["forgejo"]["read_token_env"]   # follows the corpus's owner
        print(f"""
submit one episode (the README's walkthrough reads it afterwards). The estate
requires sign-in for read; submit presents the read token by NAME
({read_env} — the name follows your corpus's owner) and the value comes from
the run's .env, sourced inside a subshell so nothing stays exported:
  ( set -a; . {WORK}/runs/{RUN}/.env; set +a
    docker run --rm --network {NETWORK} \\
      -v {WORK}/estate:/estate -v {corpus}:/corpus \\
      -e GSJ_PINS_PATH=/estate/pins.gsj.json -e {read_env} \\
      {POLAR_IMAGE} \\
      gsj-rollout submit --config /estate/rollout.yaml \\
        --from-bank /corpus/taskbank.parquet --row 0 )
one episode at a time under a fixed task id (a second concurrent submit is
refused 409 — add --task-id <another>); ./bootstrap.py status reprints this.

then read it (the receiver archived it under work/traces/):
  ./read.py                      what landed, accepted and quarantined
  ./read.py show                 the latest episode, as a transcript
  ./read.py quarantine           why anything was rejected, explained
and before spending episodes on a new endpoint:  ./preflight.py""")


# ------------------------------------------------------------------ commands

def cmd_validate(args) -> None:
    check_library()
    demo = load_demo_config(Path(args.config))
    phase_validate(corpus_path(demo))
    say("validate — PASS; the estate is one `./bootstrap.py up` away")


def cmd_up(args) -> None:
    check_docker()
    check_library()
    demo = load_demo_config(Path(args.config))
    corpus = corpus_path(demo)
    if (WORK / "estate.env").is_file():
        die(f"{WORK} holds an estate from a bootstrap older than library 0.1.3 "
            "(work/estate.env) — its layout is not this one's.",
            "./bootstrap.py down --wipe stops those containers and clears work/; "
            "then ./bootstrap.py up")
    phase_validate(corpus)
    write_polar_env()

    ensure_image(POLAR_IMAGE, "Polar + the library: rollout server, gateway, receiver")
    ensure_image(MCP_IMAGE, "the retrieval service")
    sandbox = corpus_sandbox_image(corpus)
    ensure_image(sandbox, "the per-episode sandbox, from corpus.yaml",
                 amd64_only=(sandbox == SANDBOX_IMAGE))

    # pins first: the bring-up runs with THIS estate's pins named, and the
    # endpoint-derived end-of-turn id is one of its answers
    derived_eot = derive_pins(corpus, demo["inference"]["model"],
                              str(demo.get("thinking", "off")),
                              str(demo["inference"]["base_url"]))
    answers = write_answers(demo, corpus, derived_eot)
    forwarded = [f for f in ("--overwrite-repos", "--rebuild", "--retarget")
                 if getattr(args, f[2:].replace("-", "_"), False)]
    if args.forgejo_image:
        # the route around a registry event (library CP-62): the bring-up's
        # own pin is a tag on codeberg, and a tag's platform manifests can
        # vanish under it (F-78) — the value is any pullable reference
        forwarded += ["--forgejo-image", args.forgejo_image]
    bringup("up", "--answers", str(answers), "-y", *forwarded)
    rec = load_run()
    digest_file = ESTATE / DIGEST_FILE_NAME
    served_digest = digest_file.read_text().strip() if digest_file.is_file() else None
    engine_container_url = containerize_rollout_yaml(demo, rec)
    render_topology()
    polar_up(rec, recreate=served_digest is not None and served_digest != estate_digest())

    engine_state = check_engine(engine_container_url, demo["inference"]["model"])
    say(f"up — complete in {time.monotonic() - _T0:.1f}s total")
    print_status(demo, engine_state, rec)


def cmd_status(args) -> None:
    demo = None
    cfg = Path(args.config)
    if cfg.is_file():
        try:
            demo = load_demo_config(cfg)
        except SystemExit:
            demo = None
    rec = json.loads((RUNDIR / "run.json").read_text()) if (RUNDIR / "run.json").is_file() else None
    print_status(demo, None, rec)


def cmd_down(args) -> None:
    check_docker()
    # the Polar leg: by project name, so a half-built work/ still comes down
    run(["docker", "compose", "-p", POLAR_PROJECT, "down", "--remove-orphans"])
    say("down — the Polar leg stopped")
    if RUNDIR.is_dir():
        check_library()
        bringup("down", "--name", RUN, *(["--wipe"] if args.wipe else []))
    else:
        # no run record (a bring-up that died before writing it, a hand-deleted
        # work/, or a pre-0.1.3 estate — whose five containers were one compose
        # project of this same name): the project-name form needs no files
        run(["docker", "compose", "-p", f"gsj-{RUN}", "down", "--remove-orphans"])
        run(["docker", "network", "rm", NETWORK], capture_output=True)
        say(f"down — the {f'gsj-{RUN}'} compose project stopped by name (no run record)")
    say("down — estate stopped (data under work/ survives)")
    if args.wipe:
        say(f"wipe — deleting {WORK}")
        try:
            shutil.rmtree(WORK)
        except PermissionError:
            # linux: container-written files may be root-owned; delete via a
            # container that mounts the dir (the library's down.sh precedent)
            run(["docker", "run", "--rm", "-v", f"{WORK}:/wipe", "alpine:latest",
                 "sh", "-c", "rm -rf /wipe/* /wipe/.[!.]* 2>/dev/null || true"])
            shutil.rmtree(WORK, ignore_errors=True)
        say("wipe — done; the next `up` builds a fresh estate")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.yaml"),
                    help="the stranger's three values (default: ./config.yaml)")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="check the corpus tree; stand up nothing"
                   ).set_defaults(func=cmd_validate)
    up = sub.add_parser("up", help="the whole estate, idempotently")
    for flag, help_ in (("--overwrite-repos", "forwarded to the bring-up: push over case repos "
                                              "whose content is not what this corpus builds"),
                        ("--rebuild", "forwarded to the bring-up: re-embed the retrieval index"),
                        ("--retarget", "forwarded to the bring-up: let a re-run change the "
                                       "recorded estate identity")):
        up.add_argument(flag, action="store_true", help=help_)
    up.add_argument("--forgejo-image", metavar="REF",
                    help="forwarded to the bring-up: the Forgejo image, any pullable "
                         "reference — the route around a registry that lost the pinned "
                         "tag's manifests (F-78; README 'Historical')")
    up.set_defaults(func=cmd_up)
    sub.add_parser("status", help="what is running, where, how to stop"
                   ).set_defaults(func=cmd_status)
    down = sub.add_parser("down", help="stop the estate")
    down.add_argument("--wipe", action="store_true",
                      help="also delete work/ — secrets, data, traces, everything")
    down.set_defaults(func=cmd_down)
    args = ap.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nbootstrap: interrupted — re-run `up`; every phase is idempotent",
              file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
