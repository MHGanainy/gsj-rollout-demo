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
               "end_of_turn_token_id"}
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


def mcp_up_wait() -> None:
    say("mcp — docker compose up (first start clones and embeds; later starts "
        "reuse the index via fingerprint)")
    if run(compose_cmd("up", "-d", "mcp")).returncode != 0:
        die("`docker compose up mcp` failed.",
            f"the compose error above is authoritative; if the pull failed, load {MCP_IMAGE} "
            "out-of-band and re-run")
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

def derive_pins(corpus: Path, model: str) -> None:
    from importlib.util import find_spec
    packaged = Path(find_spec("gsj_rollout").origin).parent / "pins" / "pins.gsj.json"
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
    out = ESTATE / "pins.gsj.json"
    out.write_text(json.dumps(doc, indent=2) + "\n")
    say(f"pins — derived for THIS estate at {out}: {len(cards)} skill card(s) approved "
        f"(G1), system prompt re-derived for your AGENTS.md (G2)")
    if corpus_agents == ref_agents:
        say("pins — your AGENTS.md is the reference text, so G2 equals the packaged pin")
    if model != "Qwen/Qwen3-0.6B":
        say(f"pins — NOTE: your model is {model!r}, not the reference Qwen/Qwen3-0.6B. "
            "The tokenizer-bound pins (G6's thinking tail; the estate-side G4 walk) and "
            "builder.end_of_turn_token_id are still the reference estate's — the first "
            "episode may be rejected naming those digests. That rejection is the design "
            "working; re-deriving them needs the library's pins walk "
            "(docs/checks-spec.md) and is this demo's known seam.")


# ------------------------------------------------------------ rollout config

def write_rollout_yaml(demo: dict) -> str:
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
    if "context_window" in demo:
        harness["context_window"] = int(demo["context_window"])
    if "max_tokens" in demo:
        harness["max_tokens"] = int(demo["max_tokens"])
    if harness:
        cfg["harness"] = harness
    if "end_of_turn_token_id" in demo:
        cfg["builder"] = {"end_of_turn_token_id": int(demo["end_of_turn_token_id"])}
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
    if run(["docker", "image", "inspect", SANDBOX_IMAGE],
           capture_output=True).returncode == 0:
        say(f"sandbox — {SANDBOX_IMAGE} already present")
        return
    say(f"sandbox — pulling {SANDBOX_IMAGE} (episodes run in it; pulling now so the "
        "first episode is not the moment you learn your registry path is broken)")
    if run(["docker", "pull", SANDBOX_IMAGE]).returncode != 0:
        die(f"could not pull {SANDBOX_IMAGE}.",
            "if this host cannot reach ghcr.io, load the image out-of-band "
            "(docker save/load or skopeo) and re-run — local images are used as-is")


def polar_up() -> None:
    say("polar — docker compose up (rollout server, gateway, receiver)")
    if run(compose_cmd("up", "-d", "polar-rollout", "polar-gateway",
                       "receiver")).returncode != 0:
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
submit one episode (CP-35 walks through this properly):
  docker run --rm --network {NETWORK} \\
    -v {WORK}/estate:/estate -v {corpus}:/corpus \\
    -e GSJ_PINS_PATH=/estate/pins.gsj.json \\
    {POLAR_IMAGE} \\
    gsj-rollout submit --config /estate/rollout.yaml \\
      --from-bank /corpus/taskbank.parquet --row 0 --out /estate/traces/collected""")


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

    derive_pins(corpus, demo["inference"]["model"])
    engine_container_url = write_rollout_yaml(demo)
    render_topology()
    ensure_sandbox_image()
    polar_up()

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
