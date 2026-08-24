#!/usr/bin/env python3
"""gsj-rollout-demo bootstrap — a corpus, a config, an inference endpoint,
and one command later: a running estate with the corpus ingested and
verified.

    ./bootstrap.py validate   # check the corpus tree, nothing stood up
    ./bootstrap.py up         # the whole estate: validate -> Forgejo ->
                              # scaffold -> MCP -> ingest -> taskbank ->
                              # verify -> pins -> Polar -> status
    ./bootstrap.py status     # what is running, where, and how to stop it
    ./bootstrap.py down       # stop the estate (data survives)
    ./bootstrap.py down --wipe  # stop AND delete <work>/ — a fresh estate

Running `up` twice is safe: every step detects existing state and says so.
Every failure states what to do next — a bootstrap that fails mute has
failed twice.

The stranger's three inputs (config.yaml — see config.yaml.example):
a corpus in the contract's shape, an inference endpoint URL, and the
served model's name. Everything else about the estate is stood up by this
script and therefore derived by it.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("bootstrap: PyYAML is missing. It rides the library install:\n"
          "  pip install 'gsj-harness-rollout-server>=0.1.2'", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent

# ---- the estate's published artifacts, pinned -------------------------------
POLAR_IMAGE = "ghcr.io/mhganainy/gsj-polar:f0e8343a-gsj0.1.2"
MCP_IMAGE = "ghcr.io/mhganainy/gsj-mcp-service:0.3.0"
SANDBOX_IMAGE = "ghcr.io/mhganainy/gsj-pi-harness:pi0.83.0-3"
LIB_MIN = (0, 1, 2)          # first wheel that ships the corpus pipeline
NETWORK = "gsj-demo-net"
REFERENCE_MODEL = "Qwen/Qwen3-0.6B"   # the estate every packaged pin came from

# ---- the estate's fixed in-network facts (derived, never the stranger's) ----
OWNER = "gsj-staging"        # the pipeline's staging owner (contract)
TOKEN_ENV = "GSJ_FORGEJO_TOKEN_GSJ_STAGING"
FORGEJO_URL = "http://forgejo:3000"
MCP_URL = "http://mcp:8790"
ROLLOUT_URL = "http://polar-rollout:8080"
GATEWAY_URL = "http://polar-gateway:8100"
RECEIVER_URL = "http://receiver:8300"

WORK = HERE / "work"
SECRETS = WORK / "secrets"
ESTATE = WORK / "estate"
COMPOSE = HERE / "estate" / "compose.yaml"
ENV_FILE = WORK / "estate.env"

_T0 = time.monotonic()


def say(msg: str) -> None:
    print(f"[bootstrap +{time.monotonic() - _T0:6.1f}s] {msg}", flush=True)


def die(what: str, fix: str) -> "None":
    print(f"\nbootstrap: FAIL — {what}", file=sys.stderr)
    print(f"  what to do: {fix}", file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, **kw)


def compose_cmd(*args: str) -> list:
    return ["docker", "compose", "-f", str(COMPOSE),
            "--env-file", str(ENV_FILE), *args]


def in_net_python(code: str, timeout: float = 600.0) -> subprocess.CompletedProcess:
    """Run a python snippet on the estate network (the estate publishes no
    host ports — from outside, you join the network; so does this script)."""
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
    # the packaged-pins UserWarning warns about trace-validation gates; this
    # estate derives its own pins and sets GSJ_PINS_PATH on every leg that
    # validates traces, so in the bootstrap's own process it is pure noise
    warnings.filterwarnings("ignore", message="gsj_rollout.checks")
    try:
        import gsj_rollout  # noqa: F401
    except ImportError:
        die("the gsj-harness-rollout-server library is not importable from this python "
            f"({sys.executable}).",
            "pip install 'gsj-harness-rollout-server>=0.1.2'  (same environment you run bootstrap.py from)")
    import gsj_rollout
    have = tuple(int(x) for x in gsj_rollout.__version__.split("."))
    if have < LIB_MIN:
        die(f"library {gsj_rollout.__version__} predates the packaged corpus pipeline.",
            "pip install -U 'gsj-harness-rollout-server>=0.1.2'")


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


def check_corpus_yaml(corpus: Path) -> dict:
    cy = corpus / "corpus.yaml"
    if not cy.is_file():
        die(f"{cy} does not exist — is '{corpus}' a corpus root?",
            "point config.yaml's `corpus:` at a tree in the contract's shape, "
            "or generate the worked example: ./synthetic/make_corpus.py")
    doc = yaml.safe_load(cy.read_text()) or {}
    fb = (doc.get("forgejo") or {}).get("base_url")
    if fb != FORGEJO_URL:
        die(f"{cy}: forgejo.base_url is {fb!r}, but this estate's Forgejo lives at "
            f"{FORGEJO_URL} (in-network DNS).",
            f"set   forgejo:\n              base_url: {FORGEJO_URL}")
    mu = (doc.get("mcp") or {}).get("url_base")
    if mu != MCP_URL:
        die(f"{cy}: mcp.url_base is {mu!r}, but this estate serves retrieval at {MCP_URL}.",
            f"set   mcp:\n              url_base: {MCP_URL}")
    if doc.get("owner") != OWNER:
        die(f"{cy}: owner is {doc.get('owner')!r}; this estate creates the owner '{OWNER}'.",
            f"set   owner: {OWNER}")
    if doc.get("sandbox_image") != SANDBOX_IMAGE:
        die(f"{cy}: sandbox_image is {doc.get('sandbox_image')!r}; this estate runs episodes in "
            f"the published harness image.",
            f"set   sandbox_image: {SANDBOX_IMAGE}")
    return doc


def case_ids(corpus: Path) -> list:
    ids = []
    for split in ("train", "eval"):
        cases = corpus / split / "cases"
        if cases.is_dir():
            ids += sorted(p.name for p in cases.iterdir() if p.is_dir())
    if not ids:
        die(f"no cases found under {corpus}/{{train,eval}}/cases/.",
            "the contract needs at least one case somewhere — `validate` names the rules")
    return ids


# ------------------------------------------------------------------ validate

def phase_validate(corpus: Path) -> None:
    say(f"validate — the contract, against {corpus} (host-side, before anything runs)")
    env = dict(os.environ)
    # the packaged-pins UserWarning is about trace-validation gates; the
    # corpus pipeline never consults pins, and the estate's legs get their
    # derived pins via GSJ_PINS_PATH — so here it is pure noise
    env["PYTHONWARNINGS"] = "ignore:gsj_rollout.checks"
    proc = run([sys.executable, "-m", "gsj_rollout.ingest_corpus",
                "validate", "--corpus", str(corpus)], env=env)
    if proc.returncode != 0:
        die("the corpus tree failed validation — nothing was stood up, nothing runs "
            "against an invalid tree.",
            "fix the rows marked FAIL above (each names its file and rule) and re-run; "
            "the contract lives at "
            "https://github.com/MHGanainy/gsj-harness-rollout-server/blob/main/docs/corpus-contract.md")


# ------------------------------------------------------------------- secrets

def ensure_secret() -> str:
    SECRETS.mkdir(parents=True, exist_ok=True)
    f = SECRETS / "mcp-token-secret"
    if f.is_file() and f.read_text().strip():
        say(f"mcp secret — already at {f} (reusing)")
    else:
        f.write_text(secrets.token_hex(32) + "\n")
        f.chmod(0o600)
        say(f"mcp secret — generated, lives at {f} (chmod 600); the MCP service and "
            "the gateway share it; episodes mint their tokens from it")
    return f.read_text().strip()


def write_env_file(secret: str) -> None:
    WORK.mkdir(exist_ok=True)
    ENV_FILE.write_text(
        f"GSJ_DEMO_WORK={WORK}\n"
        f"GSJ_DEMO_SESSIONS={WORK / 'sessions'}\n"
        f"GSJ_POLAR_IMAGE={POLAR_IMAGE}\n"
        f"GSJ_MCP_IMAGE={MCP_IMAGE}\n"
        f"GSJ_MCP_TOKEN_SECRET={secret}\n")
    ENV_FILE.chmod(0o600)
    (WORK / "sessions").mkdir(exist_ok=True)
    (WORK / "traces").mkdir(exist_ok=True)
    ESTATE.mkdir(exist_ok=True)


# ------------------------------------------------------------------- forgejo

def forgejo_up() -> None:
    say("forgejo — docker compose up")
    if run(compose_cmd("up", "-d", "forgejo")).returncode != 0:
        die("`docker compose up forgejo` failed.",
            "the compose error above is authoritative; if the image pull failed and "
            "this host cannot reach registries, load codeberg.org/forgejo/forgejo:16.0.2 "
            "out-of-band (docker save/load or skopeo) and re-run — local images are used as-is")
    code = (
        "import httpx,sys,time\n"
        "deadline=time.time()+90\n"
        "while time.time()<deadline:\n"
        "    try:\n"
        "        if httpx.get('http://forgejo:3000/api/healthz',timeout=3).status_code==200: sys.exit(0)\n"
        "    except Exception: pass\n"
        "    time.sleep(2)\n"
        "sys.exit(1)\n")
    if in_net_python(code, timeout=120).returncode != 0:
        die("Forgejo did not answer /api/healthz within 90 s.",
            "docker logs gsj-demo-forgejo — the first start initialises the instance; "
            "re-run once it settles, or `./bootstrap.py down --wipe` for a clean slate")
    say("forgejo — healthy at http://forgejo:3000 (in-network)")


def fcli(script: str) -> subprocess.CompletedProcess:
    # forgejo's CLI must run as the in-container `git` user
    return run(compose_cmd("exec", "-T", "forgejo", "su", "git", "-c", script),
               capture_output=True)


def ensure_owner_token() -> str:
    tok_file = SECRETS / f"forgejo-token-{OWNER}"

    def token_ok() -> bool:
        if not (tok_file.is_file() and tok_file.read_text().strip()):
            return False
        code = (
            "import httpx,sys\n"
            f"r=httpx.get('{FORGEJO_URL}/api/v1/user',"
            f"headers={{'Authorization':'token {tok_file.read_text().strip()}'}},timeout=5)\n"
            f"sys.exit(0 if r.status_code==200 and r.json().get('login')=='{OWNER}' else 1)\n")
        return in_net_python(code, timeout=30).returncode == 0

    listing = fcli("forgejo admin user list")
    if listing.returncode != 0:
        die("forgejo's CLI did not answer inside the container.",
            f"docker logs gsj-demo-forgejo; then re-run — stderr was: {listing.stderr.strip()}")
    if not re.search(rf"\b{OWNER}\b", listing.stdout):
        say(f"forgejo — creating owner '{OWNER}'")
        made = fcli(f"forgejo admin user create --username {OWNER} "
                    f"--password {OWNER}-1 --email {OWNER}@gsj.invalid "
                    f"--must-change-password=false")
        if made.returncode != 0:
            die(f"could not create the Forgejo owner '{OWNER}'.",
                f"forgejo said: {made.stderr.strip() or made.stdout.strip()}")
    else:
        say(f"forgejo — owner '{OWNER}' already exists")

    if token_ok():
        say(f"forgejo — push token already at {tok_file} (verified against the API)")
    else:
        say("forgejo — generating a push token")
        gen = fcli(f"forgejo admin user generate-access-token --username {OWNER} "
                   f"--token-name demo-bootstrap-{int(time.time())} "
                   f"--scopes write:repository,write:user --raw")
        if gen.returncode != 0:
            die("token generation failed.",
                f"forgejo said: {gen.stderr.strip() or gen.stdout.strip()}")
        tok_file.write_text(gen.stdout.strip().splitlines()[-1] + "\n")
        tok_file.chmod(0o600)
        if not token_ok():
            die("the freshly generated token does not authenticate.",
                f"docker logs gsj-demo-forgejo; token lives at {tok_file}")
        say(f"forgejo — push token verified, lives at {tok_file} (chmod 600)")
    return tok_file.read_text().strip()


# ------------------------------------------------------------------ pipeline

def pipeline(phase: str, corpus: Path, token: str, secret: str,
             extra: list = ()) -> None:
    say(f"{phase} — python -m gsj_rollout.ingest_corpus, on the estate network")
    t0 = time.monotonic()
    proc = run(["docker", "run", "--rm", "--network", NETWORK,
                "-v", f"{corpus}:/corpus",
                "-e", f"{TOKEN_ENV}={token}",
                "-e", f"GSJ_MCP_TOKEN_SECRET={secret}",
                "-e", "PYTHONWARNINGS=ignore:gsj_rollout.checks",
                POLAR_IMAGE, "python", "-m", "gsj_rollout.ingest_corpus",
                phase, "--corpus", "/corpus", *extra])
    if proc.returncode != 0:
        die(f"the corpus pipeline's `{phase}` phase failed (exit {proc.returncode}).",
            "the findings table above names each failing file and rule; fix and re-run "
            "`./bootstrap.py up` — every phase is idempotent")
    say(f"{phase} — done in {time.monotonic() - t0:.1f}s")


# ----------------------------------------------------------------------- mcp

MCP_CONFIG_TEMPLATE = """\
# GENERATED by bootstrap.py — do not edit (re-run ./bootstrap.py up instead).
# The service's schema is the library's mcp-service/config.yaml; the values
# here are the demo estate's: in-network URLs, and the repo list read from
# YOUR corpus tree. Everything pinned (embedding revision, chunking, index
# method) is kept byte-identical to the published image's reference config —
# those pins are part of what makes retrieval reproducible.

source:
  base_url: {forgejo_url}
  owner: {owner}
  repos: {repos}
  ref_main: main
  ref_pattern: "timestep-{{T}}"
  auth_token_env: null          # repos are public inside the estate
  clone_cache_dir: ./data/clones

embedding:
  model: sentence-transformers/all-MiniLM-L6-v2
  revision: 1110a243fdf4706b3f48f1d95db1a4f5529b4d41   # baked into the image
  device: cpu
  batch_size: 32
  normalize: true

chunking:
  max_tokens: 220
  overlap: 40
  respect_page_boundaries: true

index:
  path: ./data/index
  rebuild: if-stale

search:
  default_k: 5
  max_k: 20
  method: chroma

decisions:
  seed: 20260204
  corpus_size: 30

auth:
  token_secret_env: GSJ_MCP_TOKEN_SECRET
  leeway_s: 30

server:
  host: 0.0.0.0
  port: 8790
  log_level: info
  request_log_fields: [episode_id, case_id, timestep, tool, k, n_results,
                       latency_ms, cache_hit]
"""


def write_mcp_config(ids: list) -> None:
    (WORK / "mcp-config.yaml").write_text(MCP_CONFIG_TEMPLATE.format(
        forgejo_url=FORGEJO_URL, owner=OWNER,
        repos="[" + ", ".join(ids) + "]"))
    say(f"mcp — config generated for {len(ids)} case repo(s): {', '.join(ids)}")


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


def ensure_amd64_image(image: str) -> bool:
    """F-54 (CP-36): two of the published images carry linux/amd64 only, and
    an ARM docker REFUSES a manifest list with no matching platform instead
    of falling back to emulation — `up` dies at the pull on every Apple
    Silicon box. Cure it here: pull the amd64 variant explicitly (local
    images are used as-is; Docker Desktop runs them under emulation —
    measured on the CP-36 stranger run: first MCP embed ~2 min emulated,
    episodes unaffected since they talk to your endpoint over HTTP).
    Returns True when it pulled the image in this call."""
    if daemon_arch() not in ("arm64", "aarch64"):
        return False
    if run(["docker", "image", "inspect", image],
           capture_output=True).returncode == 0:
        return False
    say(f"arm64 — {image} publishes linux/amd64 only; pulling it explicitly "
        "for emulation (first start is slower; rollout speed is unaffected)")
    if run(["docker", "pull", "--platform", "linux/amd64", image]).returncode != 0:
        die(f"could not pull {image} (linux/amd64) on this ARM host.",
            "if this host cannot reach ghcr.io, load the image out-of-band "
            "(docker save/load or skopeo) and re-run — local images are "
            "used as-is")
    return True


def mcp_up_wait() -> None:
    say("mcp — docker compose up (first start clones and embeds; later starts "
        "reuse the index via fingerprint)")
    ensure_amd64_image(MCP_IMAGE)
    if run(compose_cmd("up", "-d", "mcp")).returncode != 0:
        die("`docker compose up mcp` failed.",
            f"the compose error above is authoritative; if the pull failed, load {MCP_IMAGE} "
            "out-of-band and re-run — and a `no matching manifest for "
            "linux/arm64` error means this image has no ARM variant: "
            f"docker pull --platform linux/amd64 {MCP_IMAGE}")
    code = (
        "import httpx,sys,time\n"
        "deadline=time.time()+900; last=''\n"
        "while time.time()<deadline:\n"
        "    try:\n"
        "        h=httpx.get('http://mcp:8790/health',timeout=5).json()\n"
        "        line=f\"{h.get('state')} {h.get('progress','')}\"\n"
        "        if line!=last: print(line,flush=True); last=line\n"
        "        if h.get('state')=='ready':\n"
        "            print('index_reused:',h.get('index_reused'),flush=True); sys.exit(0)\n"
        "        if h.get('state')=='error': print(h,flush=True); sys.exit(2)\n"
        "    except Exception: pass\n"
        "    time.sleep(3)\n"
        "sys.exit(1)\n")
    proc = run(["docker", "run", "--rm", "--network", NETWORK, POLAR_IMAGE,
                "python", "-c", code], timeout=960)
    if proc.returncode == 2:
        die("the MCP service reached state=error while indexing.",
            "docker logs gsj-demo-mcp — a missing case repo means the scaffold phase "
            "did not push what the generated config lists; re-run ./bootstrap.py up")
    if proc.returncode != 0:
        die("the MCP service did not reach state=ready within 900 s.",
            "docker logs gsj-demo-mcp for the indexing state; large corpora embed for "
            "a while on cpu — re-run to keep waiting (the index survives restarts)")
    say("mcp — ready at http://mcp:8790 (in-network)")


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


def derive_pins(corpus: Path, model: str, thinking: str,
                base_url: str | None = None) -> "int | None":
    from importlib.util import find_spec
    pins_root = Path(find_spec("gsj_rollout").origin).parent / "pins"
    # ADR-0024: a non-off thinking level needs the thinking-on pins on both
    # law-6 legs; the pins document's own `mode` key keeps the receiver's
    # archive stamp truthful about which mode landed each trace.
    packaged = (pins_root / "thinking-on" / "pins.gsj.json"
                if thinking != "off" else pins_root / "pins.gsj.json")
    doc = json.loads(packaged.read_text())

    ref_prompt = (HERE / "estate" / "system_prompt.reference.txt").read_bytes()
    ref_agents = (HERE / "estate" / "AGENTS.reference.md").read_bytes()
    # Tripwires before trust (the derive_pins.py discipline): the reference
    # artifacts must still agree with the wheel's packaged singleton, and the
    # AGENTS span must occur exactly once or substitution is meaningless.
    if hashlib.sha256(ref_prompt).hexdigest() not in doc["pins"]["system_prompt_hash"]:
        die("estate/system_prompt.reference.txt no longer matches the wheel's packaged "
            "G2 singleton — the reference artifact drifted from the library.",
            "update the demo repo (the artifact is a provenance-stamped copy of the "
            "library's pins/container/ capture) — do not hand-edit pins")
    if ref_prompt.count(ref_agents) != 1:
        die("the reference system prompt does not embed the reference AGENTS.md exactly "
            "once — the substitution derivation is unsound here.",
            "update the demo repo's estate/ reference artifacts together")

    corpus_agents = (corpus / "AGENTS.md").read_bytes()
    derived_prompt = ref_prompt.replace(ref_agents, corpus_agents)
    doc["pins"]["system_prompt_hash"] = [hashlib.sha256(derived_prompt).hexdigest()]

    cards = sorted(
        hashlib.sha256(card.read_bytes()).hexdigest()
        for card in sorted((corpus / "skills").glob("*/SKILL.md")))
    doc["pins"]["skill_card_hash"] = cards

    doc["derived_at"] = "gsj-rollout-demo bootstrap (G1 from the corpus's skill cards; " \
                        "G2 by AGENTS.md byte-substitution on the reference capture; " \
                        "all other sets are the reference estate's)"

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
        "artifacts": ["estate/system_prompt.reference.txt with its "
                      "AGENTS.md span replaced by <corpus>/AGENTS.md"],
        "notes": "G2 — derived by this bootstrap: byte-substitution of "
                 "this corpus's AGENTS.md into the reference capture "
                 "(which embeds the reference AGENTS.md exactly once — "
                 "verified before substituting).",
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


# ------------------------------------------------------------ rollout config

def write_rollout_yaml(demo: dict, derived_eot: "int | None" = None) -> str:
    base_url = str(demo["inference"]["base_url"]).rstrip("/")
    rewritten = re.sub(r"^(https?://)(localhost|127\.0\.0\.1)(?=[:/]|$)",
                       r"\1host.docker.internal", base_url)
    if rewritten != base_url:
        say(f"engine — {base_url} is host-local; inside containers it is reached as "
            f"{rewritten} (the gateway maps host.docker.internal to your host)")
    cfg = {
        "estate": {
            "clone_url_for": f"{FORGEJO_URL}/{OWNER}/{{case_id}}.git",
            "mcp_url_base": MCP_URL,
            "serving_base_url": rewritten,
            "model": demo["inference"]["model"],
        },
        "runtime": {"image": SANDBOX_IMAGE, "network": NETWORK},
        "polar": {
            "rollout": {"host": "0.0.0.0", "port": 8080,
                        "public_url": ROLLOUT_URL},
            "gateway": {"id": "gsj-demo-node", "host": "0.0.0.0", "port": 8100,
                        "public_url": GATEWAY_URL},
        },
        "receiver": {"host": "0.0.0.0", "port": 8300,
                     "public_url": RECEIVER_URL,
                     "traces_dir": "/estate/traces"},
    }
    harness = {}
    if demo.get("thinking", "off") != "off":
        harness["thinking"] = str(demo["thinking"])
    if "context_window" in demo:
        harness["context_window"] = int(demo["context_window"])
    if "max_tokens" in demo:
        harness["max_tokens"] = int(demo["max_tokens"])
    if harness:
        cfg["harness"] = harness
    if "end_of_turn_token_id" in demo:
        explicit = int(demo["end_of_turn_token_id"])
        cfg["builder"] = {"end_of_turn_token_id": explicit}
        if derived_eot is not None and derived_eot != explicit:
            say(f"config — WARNING: config.yaml pins end_of_turn_token_id "
                f"{explicit}, but the endpoint's own template render derives "
                f"{derived_eot}. The explicit value wins; if it is wrong, "
                "reconstruction mis-splits every multi-turn episode. Delete "
                "the key from config.yaml to use the derived value.")
    elif derived_eot is not None:
        cfg["builder"] = {"end_of_turn_token_id": int(derived_eot)}
    if "generation_prompt_glue_ids" in demo:
        glue = demo["generation_prompt_glue_ids"]
        if not (isinstance(glue, list) and glue
                and all(isinstance(t, int) and not isinstance(t, bool)
                        for t in glue)):
            die("config.yaml: generation_prompt_glue_ids must be a non-empty "
                "list of token ids.",
                "./preflight.py's template row prints the exact list when the "
                "stitch applies; delete the key if it does not")
        cfg.setdefault("builder", {})["generation_prompt_glue_ids"] = \
            [int(t) for t in glue]
        say(f"config — glue stitch armed: reconstruction re-inserts "
            f"{glue} at each turn opening (set from config.yaml because "
            "./preflight.py measured a constant template divergence)")
    text = ("# GENERATED by bootstrap.py from config.yaml — do not edit; edit\n"
            "# config.yaml and re-run ./bootstrap.py up. Schema: the library's\n"
            "# `one YAML` (gsj_rollout/config.py).\n"
            + yaml.safe_dump(cfg, sort_keys=False))
    (ESTATE / "rollout.yaml").write_text(text)
    say(f"config — rollout.yaml generated at {ESTATE / 'rollout.yaml'}")
    return rewritten


def render_topology() -> None:
    proc = run(["docker", "run", "--rm", "-v", f"{ESTATE}:/estate", POLAR_IMAGE,
                "gsj-rollout", "serve", "--config", "/estate/rollout.yaml",
                "--render-only"], capture_output=True)
    if proc.returncode != 0:
        die("the library rejected the generated rollout.yaml.",
            f"this is a bootstrap bug — report it with this output:\n{proc.stderr}")
    say("config — Polar topology rendered (topology.rendered.yaml)")


# --------------------------------------------------------------------- polar

def ensure_sandbox_image() -> None:
    if ensure_amd64_image(SANDBOX_IMAGE):   # F-54: amd64-only publish, ARM
        say(f"sandbox — {SANDBOX_IMAGE} pulled (amd64) — episodes run in it")
        return
    if run(["docker", "image", "inspect", SANDBOX_IMAGE],
           capture_output=True).returncode == 0:
        say(f"sandbox — {SANDBOX_IMAGE} already present")
        return
    say(f"sandbox — pulling {SANDBOX_IMAGE} (episodes run in it; pulling now so the "
        "first episode is not the moment you learn your registry path is broken)")
    if run(["docker", "pull", SANDBOX_IMAGE]).returncode != 0:
        die(f"could not pull {SANDBOX_IMAGE}.",
            "if this host cannot reach ghcr.io, load the image out-of-band "
            "(docker save/load or skopeo) and re-run — local images are used "
            "as-is; a `no matching manifest for linux/arm64` error means "
            "this image has no ARM variant: docker pull --platform "
            f"linux/amd64 {SANDBOX_IMAGE}")


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


def polar_up(recreate: bool = False) -> None:
    say("polar — docker compose up (rollout server, gateway, receiver)"
        + (" — generated estate files changed since the last bring-up, so "
           "the three are RECREATED (the receiver reads pins at start — "
           "the archive's mode stamp depends on it)" if recreate else ""))
    up = ["up", "-d"] + (["--force-recreate"] if recreate else [])         + ["polar-rollout", "polar-gateway", "receiver"]
    if run(compose_cmd(*up)).returncode != 0:
        die("`docker compose up` of the Polar services failed.",
            f"the compose error above is authoritative; if the pull failed, load {POLAR_IMAGE} "
            "out-of-band and re-run")
    code = (
        "import httpx,sys,time\n"
        "deadline=time.time()+60\n"
        "ok_r=ok_g=False\n"
        "while time.time()<deadline and not(ok_r and ok_g):\n"
        "    try:\n"
        "        h=httpx.get('http://polar-rollout:8080/health',timeout=3).json()\n"
        "        ok_r = h.get('status')=='ok' and h.get('nodes',0)>=1\n"
        "    except Exception: pass\n"
        "    try:\n"
        "        httpx.get('http://receiver:8300/',timeout=3); ok_g=True\n"
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
            "no node usually means the gateway crashed")
    say("polar — rollout server reports its gateway node; receiver is listening")
    (ESTATE / DIGEST_FILE_NAME).write_text(estate_digest() + "\n")


def check_engine(url: str, model: str) -> str:
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

def print_status(demo: dict | None, engine_state: str | None) -> None:
    ps = run(compose_cmd("ps", "--format",
                         "table {{.Name}}\t{{.Status}}"), capture_output=True)
    print("\n== the estate ==")
    print(ps.stdout.rstrip() or "(nothing running — ./bootstrap.py up)")
    print(f"""
in-network URLs (the estate publishes NO host ports; join the network to talk
to it: docker run --rm --network {NETWORK} <image> ...):
  forgejo    {FORGEJO_URL}     case repos under /{OWNER}/
  mcp        {MCP_URL}      retrieval; /health for state
  rollout    {ROLLOUT_URL}   submit dials this
  gateway    {GATEWAY_URL}   episodes' OpenAI-compatible proxy
  receiver   {RECEIVER_URL}   traces land here first

on disk (all under {WORK}):
  secrets/mcp-token-secret        the estate's HMAC secret (chmod 600)
  secrets/forgejo-token-{OWNER}  the pipeline's push token
  estate/rollout.yaml             the generated library config
  estate/pins.gsj.json            THIS estate's approved sets (GSJ_PINS_PATH)
  traces/                         validated traces (receiver-side leg)
  sessions/                       per-episode session dirs + agent logs

stop:      ./bootstrap.py down          (data survives)
reset:     ./bootstrap.py down --wipe   (deletes {WORK})
re-run:    ./bootstrap.py up            (idempotent — safe on a running estate)""")
    if engine_state is not None:
        mark = "ok" if engine_state == "ok" else f"NOT OK — {engine_state}"
        print(f"\nengine     {demo['inference']['base_url']}  ->  {mark}")
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
        corpus = Path(demo["corpus"]).resolve()
        print(f"""
submit one episode (the README's walkthrough reads it afterwards):
  docker run --rm --network {NETWORK} \\
    -v {WORK}/estate:/estate -v {corpus}:/corpus \\
    -e GSJ_PINS_PATH=/estate/pins.gsj.json \\
    {POLAR_IMAGE} \\
    gsj-rollout submit --config /estate/rollout.yaml \\
      --from-bank /corpus/taskbank.parquet --row 0

then read it (the receiver archived it under work/traces/):
  ./read.py                      what landed, accepted and quarantined
  ./read.py show                 the latest episode, as a transcript
  ./read.py quarantine           why anything was rejected, explained
and before spending episodes on a new endpoint:  ./preflight.py""")


# ------------------------------------------------------------------ commands

def cmd_validate(args) -> None:
    check_library()
    demo = load_demo_config(Path(args.config))
    corpus = (HERE / demo["corpus"]).resolve() if not Path(demo["corpus"]).is_absolute() \
        else Path(demo["corpus"])
    phase_validate(corpus)
    say("validate — PASS; the estate is one `./bootstrap.py up` away")


def cmd_up(args) -> None:
    check_docker()
    check_library()
    demo = load_demo_config(Path(args.config))
    corpus = (HERE / demo["corpus"]).resolve() if not Path(demo["corpus"]).is_absolute() \
        else Path(demo["corpus"])
    phase_validate(corpus)
    check_corpus_yaml(corpus)
    ids = case_ids(corpus)

    secret = ensure_secret()
    write_env_file(secret)

    forgejo_up()
    token = ensure_owner_token()
    pipeline("scaffold", corpus, token, secret)

    write_mcp_config(ids)
    mcp_up_wait()
    pipeline("ingest", corpus, token, secret)
    pipeline("taskbank", corpus, token, secret)
    pipeline("verify", corpus, token, secret)

    digest_file = ESTATE / DIGEST_FILE_NAME
    served_digest = digest_file.read_text().strip() if digest_file.is_file() else ""
    derived_eot = derive_pins(corpus, demo["inference"]["model"],
                              str(demo.get("thinking", "off")),
                              str(demo["inference"]["base_url"]))
    engine_container_url = write_rollout_yaml(demo, derived_eot)
    render_topology()
    ensure_sandbox_image()
    polar_up(recreate=served_digest != estate_digest())

    engine_state = check_engine(engine_container_url, demo["inference"]["model"])
    say(f"up — complete in {time.monotonic() - _T0:.1f}s total")
    print_status(demo, engine_state)


def cmd_status(args) -> None:
    demo = None
    engine_state = None
    cfg = Path(args.config)
    if cfg.is_file():
        try:
            demo = load_demo_config(cfg)
        except SystemExit:
            demo = None
    if not ENV_FILE.is_file():
        write_env_file(os.environ.get("GSJ_MCP_TOKEN_SECRET", "unset"))
    print_status(demo, engine_state)


def cmd_down(args) -> None:
    check_docker()
    if not ENV_FILE.is_file():
        # compose interpolation needs the vars even for `down` — synthesize
        write_env_file("unset")
    run(compose_cmd("down", "--remove-orphans"))
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
    sub.add_parser("up", help="the whole estate, idempotently"
                   ).set_defaults(func=cmd_up)
    sub.add_parser("status", help="what is running, where, how to stop"
                   ).set_defaults(func=cmd_status)
    down = sub.add_parser("down", help="stop the estate")
    down.add_argument("--wipe", action="store_true",
                      help="also delete work/ — secrets, data, traces, everything")
    down.set_defaults(func=cmd_down)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
