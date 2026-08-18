#!/usr/bin/env python3
"""gsj-rollout-demo preflight — probe YOUR endpoint against what the demo
assumes, BEFORE an episode is spent learning it the hard way.

    ./preflight.py               # probes config.yaml's endpoint from this host

The demo's smoke ran against the reference stack (vLLM, Qwen/Qwen3-0.6B,
pinned sampling). A stranger's endpoint differs in ways that break different
things: no tool-call parser, unpinned sampling defaults, another tokenizer,
a smaller context window. Most of that cannot be FIXED here — it is your
serving stack's provenance — but it can be made legible: each probe below
names what it found, what the demo assumes, and what the mismatch costs.

Probes run HOST-side against config.yaml's base_url exactly as written.
(Container-side reachability — the path episodes actually use — is checked
by `./bootstrap.py up`'s engine line.)

Exit 0: nothing fatal found. Exit 1: at least one FAIL.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

OK, WARN, FAIL, SKIP = "[ ok ]", "[warn]", "[FAIL]", "[ -- ]"
_failed = False


def row(mark: str, name: str, detail: str) -> None:
    global _failed
    if mark == FAIL:
        _failed = True
    pad = "\n" + " " * 25
    print(f"{mark} {name:<17} {pad.join(detail.splitlines())}", flush=True)


def http(url: str, payload=None, timeout=10.0):
    """-> (status, parsed json | text | None). Never raises."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"} if payload is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body, status = exc.read().decode(errors="replace"), exc.code
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.yaml"),
                    help="the stranger's config (default: ./config.yaml)")
    ap.add_argument("--pins", default=str(HERE / "work" / "estate" / "pins.gsj.json"),
                    help="this estate's derived pins (default: work/estate/…)")
    args = ap.parse_args()

    try:
        import yaml
    except ImportError:
        print("preflight: PyYAML is missing — pip install "
              "'gsj-harness-rollout-server>=0.1.2' (it rides the library "
              "install)", file=sys.stderr)
        return 1
    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"preflight: {cfg_path} does not exist.\n  what to do: copy "
              "config.yaml.example to config.yaml and fill in the three "
              "values", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    inf = cfg.get("inference") or {}
    base = str(inf.get("base_url", "")).rstrip("/")
    model = inf.get("model")
    if not base or not model:
        print(f"preflight: {cfg_path} lacks inference.base_url / "
              "inference.model.\n  what to do: see config.yaml.example",
              file=sys.stderr)
        return 1
    window = int(cfg.get("context_window", 32768))
    eot = int(cfg.get("end_of_turn_token_id", 151645))

    print(f"probing {base} for {model!r} (host-side, as written in "
          f"{cfg_path.name})\n")

    # 1 — reachable
    status, models = http(f"{base}/v1/models", timeout=8)
    if status is None or status >= 400:
        why = (f"did not answer ({models})" if status is None
               else f"answered HTTP {status} — an error, not a model list"
                    + (" (a base_url that already ends in /v1 probes "
                       "/v1/v1/models — drop the suffix)" if status == 404
                       else ""))
        row(FAIL, "reachable",
            f"GET {base}/v1/models {why}.\n"
            "consequence: nothing below could run; episodes die as "
            "ADM1/ADM4 'no completions'.\n"
            "what to do: start your endpoint, or fix base_url in config.yaml "
            "(no /v1 suffix).")
        print()
        print("preflight: FAIL — the endpoint's model list is unreadable; "
              "every other probe needs it.")
        return 1
    row(OK, "reachable", f"GET /v1/models answered (HTTP {status})")

    # 2 — the served-model name, byte-for-byte (tolerate the shapes seen in
    # the wild: {"data": [...]}, a bare list, junk entries)
    data = models.get("data") if isinstance(models, dict) else models
    cards = [m for m in data if isinstance(m, dict)] \
        if isinstance(data, list) else []
    served = [m.get("id") for m in cards]
    card = next((m for m in cards if m.get("id") == model), None)
    if model in served:
        row(OK, "model", f"{model!r} is served")
    else:
        row(FAIL, "model",
            f"{model!r} is NOT in the served list {served}.\n"
            "consequence: Polar requests this exact name; the engine refuses "
            "it and every episode dies with 'no completions' (quarantined "
            "ADM1/ADM4).\n"
            "what to do: serve the model under exactly this name, or set "
            "inference.model to a name in the list above.")

    # 3 — context window, when the endpoint states it (vLLM does)
    stated = card.get("max_model_len") if isinstance(card, dict) else None
    if card is None:
        row(SKIP, "context window",
            "cannot be read — the configured model has no card in /v1/models "
            "(see the model row above); fix that first.")
    elif isinstance(stated, int):
        if stated >= window:
            row(OK, "context window", f"max_model_len {stated:,} >= the "
                f"harness's planning window {window:,}")
        else:
            row(FAIL, "context window",
                f"max_model_len {stated:,} < the harness's planning window "
                f"{window:,}.\n"
                "consequence: the harness plans turns against the larger "
                "number; requests start dying mid-episode when the real "
                "window fills.\n"
                f"what to do: serve with a >= {window:,} window, or set "
                f"context_window: {stated} in config.yaml (smaller episodes, "
                "honestly planned).")
    else:
        row(WARN, "context window",
            f"this endpoint does not state its window (no max_model_len — "
            "not vLLM?). The demo assumes >= "
            f"{window:,}.\n"
            "consequence if smaller: mid-episode 400s once the real window "
            "fills — set context_window in config.yaml to the true value.")

    # 4 — tool-call parser: the agent's tools arrive as OpenAI definitions
    payload = {
        "model": model, "max_tokens": 512,
        "messages": [{"role": "user",
                      "content": "What is 217 + 105? You MUST use the add "
                                 "tool to compute it."}],
        "tools": [{"type": "function", "function": {
            "name": "add", "description": "Add two integers.",
            "parameters": {"type": "object",
                           "required": ["a", "b"],
                           "properties": {"a": {"type": "number"},
                                          "b": {"type": "number"}}}}}],
        "tool_choice": "auto"}
    status, resp = http(f"{base}/v1/chat/completions", payload, timeout=90)
    if status is None or (isinstance(status, int) and status >= 500):
        row(FAIL, "tool parser",
            f"the completion request failed outright ({status}: "
            f"{str(resp)[:200]}).\n"
            "consequence: episodes cannot run at all.\n"
            "what to do: your server's log has the real error; fix and re-run.")
    elif isinstance(status, int) and status >= 400:
        row(FAIL, "tool parser",
            f"the endpoint REJECTED the tools parameter (HTTP {status}: "
            f"{str(resp)[:200]}).\n"
            "consequence: pi sends 11 tool definitions on every turn; every "
            "episode dies at the first request.\n"
            "what to do: enable your server's tool-calling support (vLLM: "
            "--enable-auto-tool-choice --tool-call-parser hermes).")
    else:
        choices = resp.get("choices") if isinstance(resp, dict) else None
        first = choices[0] if isinstance(choices, list) and choices else None
        msg = first.get("message") if isinstance(first, dict) else None
        msg = msg if isinstance(msg, dict) else {}
        calls = [c for c in msg.get("tool_calls") or [] if isinstance(c, dict)]
        first_fn = calls[0].get("function") if calls else None
        first_fn = first_fn if isinstance(first_fn, dict) else {}
        if calls and first_fn.get("name") == "add":
            row(OK, "tool parser", "the endpoint returned a structured "
                "tool_call for a tool-begging prompt")
        elif calls:
            row(OK, "tool parser", f"structured tool_calls came back "
                f"(called {first_fn.get('name')!r})")
        else:
            row(WARN, "tool parser",
                "the endpoint answered with TEXT, no structured tool_call.\n"
                "could be model choice on this toy prompt — but if your "
                "server has no tool-call parser, the agent's calls stay "
                "text: episodes loop making zero tool calls and produce "
                "degenerate trajectories.\n"
                "what to do: confirm your server parses tool calls (vLLM: "
                "--enable-auto-tool-choice --tool-call-parser hermes).")

    # 5 — the served tokenizer, against THIS estate's pinned tail (vLLM's
    #     /tokenize makes this a real check; elsewhere it is honestly a gap)
    pins_path = Path(args.pins)
    if not pins_path.is_file():
        row(SKIP, "tokenizer tail",
            f"no derived pins at {pins_path} — run ./bootstrap.py up first "
            "(pins are derived there), then re-run this preflight.")
    else:
        pins = json.loads(pins_path.read_text()).get("pins", {})
        tail_text = (pins.get("g6_expected_tail") or [None])[0]
        tail_id_set = pins.get("g6_expected_tail_ids") or []
        tail_ids = tail_id_set[0] if tail_id_set else None
        status, tok = http(f"{base}/tokenize",
                           {"model": model, "prompt": tail_text,
                            "add_special_tokens": False}, timeout=10)
        if not isinstance(status, int) or status >= 400 or not isinstance(tok, dict):
            row(WARN, "tokenizer tail",
                f"POST /tokenize is not available here ({status}) — the "
                "served tokenizer cannot be verified over the API.\n"
                "consequence if it differs from the pinned one (Qwen3): the "
                "FIRST episode is quarantined at G6:prompt_suffix_ne_tail_ids "
                "— that quarantine, not this preflight, is where you would "
                "learn it. `./read.py quarantine` will name it.")
        elif tok.get("tokens") in tail_id_set:
            row(OK, "tokenizer tail",
                f"/tokenize renders the pinned G6 tail exactly ({tail_ids})")
        else:
            row(FAIL, "tokenizer tail",
                f"the served tokenizer renders the pinned tail as\n"
                f"{tok.get('tokens')}\nbut this estate's pins expect\n"
                f"{tail_ids}.\n"
                "consequence: EVERY episode will be quarantined at "
                "G6:prompt_suffix_ne_tail_ids — the tokenizer/chat-template "
                "is not the one the pins were derived from.\n"
                "what to do: serve the reference tokenizer (Qwen3), or "
                "re-derive the tokenizer-bound pins for yours — the "
                "library's pins walk (docs/checks-spec.md); this is the "
                "demo's known seam.")
        # the end-of-turn id splits turns during reconstruction
        status, tok = http(f"{base}/tokenize",
                           {"model": model, "prompt": "<|im_end|>",
                            "add_special_tokens": False}, timeout=10)
        if isinstance(status, int) and status < 400 and isinstance(tok, dict):
            if tok.get("tokens") == [eot]:
                row(OK, "end-of-turn id",
                    f"'<|im_end|>' -> [{eot}] — matches the builder's pin")
            else:
                row(FAIL, "end-of-turn id",
                    f"'<|im_end|>' tokenizes to {tok.get('tokens')}, but the "
                    f"builder splits turns at [{eot}].\n"
                    "consequence: reconstruction mis-splits every multi-turn "
                    "episode (G7 territory), or the tail check fires first.\n"
                    "what to do: set end_of_turn_token_id in config.yaml to "
                    "your tokenizer's actual end-of-turn id and re-run "
                    "./bootstrap.py up.")

    # 6 — sampling defaults: honestly not probeable
    row(WARN, "sampling defaults",
        "NOT PROBEABLE over the API. pi sends NO sampling parameters, so "
        "your server's generation defaults ARE the sampling policy.\n"
        "consequence if unpinned: rollouts silently sample at whatever the "
        "server defaults to (vLLM without --generation-config: T=1.0 — the "
        "CP-09 lesson), and that distribution is what you train on.\n"
        "what to do: pin them server-side (vLLM: --generation-config "
        "<dir-with-generation_config.json>; the reference stack pins the "
        "snapshot's own file) and treat the argv as part of your estate's "
        "provenance.")

    print()
    if _failed:
        print("preflight: FAIL — at least one mismatch above will cost you "
              "episodes. Fix the [FAIL] rows before submitting.")
        return 1
    print("preflight: no fatal mismatch found. [warn] rows are the limits "
          "of what an API can see — read them once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
