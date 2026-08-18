#!/usr/bin/env python3
"""gsj-rollout-demo read — the archived trajectories, readable.

    ./read.py ls                 # what is in the archive (and the quarantine)
    ./read.py show [ID]          # a session transcript a person can read
    ./read.py export [ID]        # a structured projection a program consumes
    ./read.py quarantine [ID]    # rejected traces: every finding, explained

Everything here is DERIVED from the receiver's archive under work/traces/.
This tool adds nothing the receiver did not write, stores nothing, and never
writes a file — the archive is the truth; these are views of it.

ID is a session id, any unique piece of one, or `latest` (the default).
`show` renders thinking-on reasoning by decoding the archived token ids;
that needs the `tokenizers` package and the served model's tokenizer —
without them the transcript says what it could not render, per turn.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DIR = HERE / "work" / "traces"

# Qwen3's think-block marker ids — a labelled heuristic for detecting
# non-empty reasoning without a tokenizer, valid only for Qwen-family models
# (the reference stack). Everything decoded for *display* comes from a real
# tokenizer; these only decide whether to say "thinking present, not shown".
QWEN_THINK, QWEN_ENDTHINK = 151667, 151668


def die(what: str, fix: str) -> None:
    print(f"read.py: FAIL — {what}", file=sys.stderr)
    print(f"  what to do: {fix}", file=sys.stderr, flush=True)
    sys.exit(1)


# ------------------------------------------------------------- the archive

def scan(directory: Path, quarantined: bool) -> list:
    """Every archived body in `directory`: (path, session_id, mode, mtime)."""
    entries = []
    if not directory.is_dir():
        return entries
    for path in directory.glob("*.json"):
        stem = path.name[:-len(".json")]
        if "." in stem:                       # <session_id>.<pins-mode>.json
            sid, mode = stem.rsplit(".", 1)
        else:                                 # pre-stamp or client-collected
            sid, mode = stem, "unstamped"
        entries.append({"path": path, "sid": sid, "mode": mode,
                        "mtime": path.stat().st_mtime,
                        "quarantined": quarantined})
    return sorted(entries, key=lambda e: e["mtime"])


def all_entries(directory: Path) -> list:
    return sorted(scan(directory, False) + scan(directory / "quarantine", True),
                  key=lambda e: e["mtime"])


def resolve(directory: Path, ident: str) -> dict:
    entries = all_entries(directory)
    if not entries:
        die(f"no archived episodes under {directory} (or its quarantine/).",
            "submit one first — the README's `Submit an episode` section is "
            "the walkthrough; or point --dir at the archive "
            "(the receiver writes work/traces/ on the estate host)")
    if ident == "latest":
        return entries[-1]
    hits = [e for e in entries if ident in e["sid"]]
    if not hits:
        die(f"no archived episode matches {ident!r}.",
            f"`./read.py ls` lists the {len(entries)} episode(s) present; "
            "any unique piece of a session id works")
    if len(hits) > 1 and not all(h["sid"] == hits[0]["sid"] for h in hits):
        names = ", ".join(sorted({h["sid"] for h in hits})[:4])
        die(f"{ident!r} is ambiguous — it matches {len(hits)} episodes ({names}…).",
            "give a longer piece of the session id (`./read.py ls` shows them)")
    return hits[-1]


def load(entry: dict) -> tuple:
    """-> (gate_findings, session_result). Quarantined bodies arrive wrapped —
    and the WRAPPER, not the directory, is the truth about disposition (a
    --dir pointed straight at quarantine/ must not relabel rejects)."""
    try:
        body = json.loads(entry["path"].read_text())
    except (OSError, ValueError) as exc:
        die(f"{entry['path']} is not readable JSON: {exc}",
            "the receiver writes archives atomically, so a corrupt file was "
            "corrupted after landing — restore it or delete it")
    if isinstance(body, dict) and set(body) == {"findings", "session_result"}:
        entry["quarantined"] = True
        return body["findings"], body["session_result"]
    return [], body


def trace_of(sr: dict):
    traces = (sr.get("trajectory") or {}).get("traces") or []
    return traces[0] if traces else None


def content_text(content) -> str:
    """OpenAI content: None, a string, or a list of typed parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def call_fn(tc) -> dict:
    """A tool_call's function object — checks.py tolerates a call without
    one, so a quarantined body can carry it; never crash on it."""
    fn = tc.get("function") if isinstance(tc, dict) else None
    return fn if isinstance(fn, dict) else {}


def turns_of(trace: dict) -> list:
    """Group response_messages: one assistant turn + its tool results."""
    turns = []
    for msg in trace.get("response_messages") or []:
        if msg.get("role") == "assistant":
            turns.append({"msg": msg, "results": []})
        elif msg.get("role") == "tool" and turns:
            turns[-1]["results"].append(msg)
    return turns


def mask_runs(mask: list) -> list:
    """Contiguous loss_mask==1 spans — one per assistant turn (measured:
    runs == assistant messages on every reference body)."""
    runs, start = [], None
    for i, bit in enumerate(mask):
        if bit == 1 and start is None:
            start = i
        elif bit != 1 and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def qwen_think_spans(ids: list) -> list:
    """(start, end) id-index spans strictly between the Qwen think markers.
    The thinking-off template emits an EMPTY block (one newline token), so
    only spans longer than 1 token mean reasoning actually happened."""
    spans, start = [], None
    for i, tid in enumerate(ids):
        if tid == QWEN_THINK:
            start = i
        elif tid == QWEN_ENDTHINK and start is not None:
            if i - start - 1 > 1:
                spans.append((start + 1, i))
            start = None
    return spans


# ------------------------------------------------------------ the tokenizer

def load_tokenizer(spec, model):
    """-> (tokenizer|None, why_not). Never fails the command — the transcript
    states, per turn, what it could not render."""
    try:
        from tokenizers import Tokenizer
    except ImportError:
        return None, ("the 'tokenizers' package is not installed — "
                      "pip install tokenizers   (then re-run)")
    candidates = []
    if spec:
        p = Path(spec)
        if p.is_file():
            candidates.append(("file", str(p)))
        elif (p / "tokenizer.json").is_file():
            candidates.append(("file", str(p / "tokenizer.json")))
        else:
            candidates.append(("hub", spec))
    if model:
        cache = Path.home() / ".cache" / "huggingface" / "hub"
        cached = f"models--{model.replace('/', '--')}"
        for tj in sorted(cache.glob(f"{cached}/snapshots/*/tokenizer.json")):
            candidates.append(("file", str(tj)))
        candidates.append(("hub", model))
    for kind, ref in candidates:
        try:
            return (Tokenizer.from_file(ref) if kind == "file"
                    else Tokenizer.from_pretrained(ref)), None
    # a hub fetch can fail offline; the next candidate may still work
        except Exception:
            continue
    return None, (f"no tokenizer found for {model!r} (looked in the local "
                  "HF cache, then the hub) — pass --tokenizer "
                  "<tokenizer.json|dir|hf-id> for the model your endpoint serves")


def decoded_turns(trace: dict, tokenizer) -> list:
    """Per assistant turn: the raw text the model emitted (from the archived
    token ids), or None when it cannot be decoded."""
    n_turns = sum(1 for m in trace.get("response_messages") or []
                  if m.get("role") == "assistant")
    out = [None] * n_turns
    if tokenizer is None:
        return out
    ids = trace.get("response_ids") or []
    runs = mask_runs(trace.get("loss_mask") or [])
    if len(runs) != n_turns:      # never guess an alignment
        return out
    for k, (s, e) in enumerate(runs):
        try:
            out[k] = tokenizer.decode(ids[s:e], skip_special_tokens=False)
        except Exception:
            pass
    return out


THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def split_think(decoded: str):
    """(reasoning_text|None, rest) from a decoded raw turn."""
    if decoded is None:
        return None, None
    m = THINK_RE.search(decoded)
    if not m:
        return None, decoded
    body = m.group(1).strip()
    return (body or None), decoded[m.end():]


# --------------------------------------------------------------- rendering

def clip(text: str, limit: int, full: bool) -> str:
    if full or len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0] or text[:limit]
    return f"{cut}\n… (+{len(text) - len(cut):,} chars — --full shows everything)"


def indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def parse_hits(content: str):
    """MCP search results arrive as CONCATENATED json objects
    {page, file, score, text} — parse them all, or None if not that shape."""
    decoder, idx, hits = json.JSONDecoder(), 0, []
    while idx < len(content):
        while idx < len(content) and content[idx] in " \n\r\t":
            idx += 1
        if idx >= len(content):
            break
        try:
            obj, idx = decoder.raw_decode(content, idx)
        except ValueError:
            return None
        if not (isinstance(obj, dict) and "page" in obj and "text" in obj):
            return None
        hits.append(obj)
    return hits or None


def render_result(name: str, content: str, timestep, full: bool) -> list:
    """One tool result, as lines. MCP search hits get the page-aware view —
    the cutoff is the estate's whole point, so pages are always shown."""
    lines = []
    hits = parse_hits(content) if name.startswith("mcp_gsj_search") else None
    if hits:
        pages = [h.get("page") for h in hits]
        marks = ", ".join(str(p) for p in pages)
        ok = (timestep is None or all(isinstance(p, int) and p <= timestep
                                      for p in pages))
        verdict = (f"all <= timestep {timestep} (the cutoff holds)" if ok
                   else f"PAGE BEYOND TIMESTEP {timestep} — cutoff violated")
        lines.append(f"   <- {len(hits)} hits, pages [{marks}] — {verdict}")
        for h in hits:
            head = " ".join(h.get("text", "").split())
            head = head if full else (head[:150] + ("…" if len(head) > 150 else ""))
            lines.append(f"      page {h.get('page')}  score {h.get('score', 0):.2f}"
                         f"  {h.get('file', '')}\n         {head}")
        return lines
    label = f"   <- ({len(content):,} chars)"
    body = clip(content, 500, full)
    lines.append(label)
    lines.append(indent(body, "      "))
    return lines


def turn_blocks(trace: dict, decoded: list, timestep, full: bool,
                no_tok_reason) -> list:
    """Render every assistant turn; collapse literal repetition honestly.

    Each block: (signature, lines). Signature covers the model's action AND
    the tool's answer — only byte-identical turns collapse."""
    blocks = []
    turns = turns_of(trace)
    stamp_thinking = qwen_think_spans(trace.get("response_ids") or [])
    for k, turn in enumerate(turns):
        msg, lines = turn["msg"], []
        think, _rest = split_think(decoded[k] if k < len(decoded) else None)
        text = content_text(msg.get("content"))
        calls = [(call_fn(tc).get("name", "(unnamed tool call)"),
                  call_fn(tc).get("arguments", ""))
                 for tc in msg.get("tool_calls") or []]
        results = [content_text(r.get("content")) for r in turn["results"]]

        if think:
            lines.append("   thinking:")
            lines.append(indent(clip(think, 700, full), "   | "))
        elif decoded[k] is None and stamp_thinking and no_tok_reason:
            lines.append(f"   [thinking happened this session but cannot be "
                         f"shown: {no_tok_reason}]")
        for name, args in calls:
            try:
                args_line = json.dumps(json.loads(args))
            except ValueError:
                args_line = args
            if not full and len(args_line) > 300:
                args_line = args_line[:300] + f"… (+{len(args_line) - 300:,} chars)"
            lines.append(f"   -> {name} {args_line}")
        for (name, _), content in zip(calls, results):
            lines.extend(render_result(name, content, timestep, full))
        for content in results[len(calls):]:
            lines.extend(render_result("", content, timestep, full))
        if text.strip():
            lines.append(indent(text.strip(), "   "))
        if not lines:
            lines.append("   (an empty assistant turn)")
        signature = (think, text, tuple(calls), tuple(results))
        blocks.append((signature, lines))
    return blocks


def print_session(blocks: list) -> None:
    """Collapse runs of >=3 byte-identical turns — the CP-34 reference episode
    is 70 identical read calls, and honesty does not require printing it 70x."""
    i, n = 0, len(blocks)
    while i < n:
        j = i
        while j + 1 < n and blocks[j + 1][0] == blocks[i][0]:
            j += 1
        count = j - i + 1
        if count >= 3:
            print(f"[turns {i + 1}-{j + 1}] — the next turn repeated {count}x, "
                  f"call and result byte-identical each time:")
        else:
            j = i
            print(f"[turn {i + 1}]")
        for line in blocks[i][1]:
            print(line)
        i = j + 1


def find_deliverable(trace: dict):
    """The last `write` call — the brief asks for out/<task_id>.md. Returns
    (path, content, turn_no) or None."""
    best = None
    for k, turn in enumerate(turns_of(trace)):
        for tc in turn["msg"].get("tool_calls") or []:
            if call_fn(tc).get("name") != "write":
                continue
            try:
                args = json.loads(call_fn(tc).get("arguments", ""))
            except ValueError:
                continue
            if isinstance(args, dict) and "path" in args:
                best = (args.get("path"), args.get("content", ""), k + 1)
    return best


# ----------------------------------------------------------------- headers

def header_lines(entry, findings, sr, trace) -> list:
    md = sr.get("metadata") or {}
    tmd = (sr.get("trajectory") or {}).get("metadata") or {}
    lines = []
    disp = "QUARANTINED" if findings else "accepted"
    lines.append(f"== episode {sr.get('session_id', entry['sid'])} "
                 f"({disp}; archived {entry['mode']}) ==")
    if findings:
        lines.append(f"rejected    {len(findings)} finding(s): "
                     + "; ".join(findings))
        lines.append("            `./read.py quarantine "
                     f"{entry['sid'][:16]}` explains each one")
    case, ts = md.get("case_id"), md.get("timestep")
    if case is not None:
        lines.append(f"task        {case} @ timestep {ts}   "
                     f"({md.get('prompt_source')}, split {md.get('split')})")
    lines.append(f"status      {sr.get('status')}"
                 + (f" — error: {sr.get('error')}" if sr.get("error") else ""))
    if tmd:
        lines.append(f"model       {tmd.get('model_used')} via {tmd.get('api_type')}")
    if trace:
        ws = (trace.get("metadata") or {}).get("gsj_workspace") or {}
        pages = ws.get("pages") or {}
        if ws:
            lines.append(f"checkout    branch {ws.get('branch')}, commit "
                         f"{str(ws.get('commit'))[:10]} — pages "
                         f"{pages.get('min')}..{pages.get('max')} "
                         f"({pages.get('count')} visible at this cutoff)")
        n_turns = sum(1 for m in trace.get("response_messages") or []
                      if m.get("role") == "assistant")
        n_calls = sum(len(m.get("tool_calls") or [])
                      for m in trace.get("response_messages") or []
                      if m.get("role") == "assistant")
        mask = trace.get("loss_mask") or []
        ones = sum(mask)
        lines.append(f"turns       {n_turns} assistant turns, {n_calls} tool calls")
        lines.append(f"tokens      prompt {len(trace.get('prompt_ids') or []):,}; "
                     f"response {len(trace.get('response_ids') or []):,} "
                     f"({ones:,} trainable"
                     + (f" = {ones / len(mask):.0%})" if mask else ")"))
        fin = trace.get("finish_reason")
        if fin == "length":
            lines.append("finish      LENGTH — the episode hit the generation cap "
                         "mid-turn. It qualified BY DESIGN and is honestly")
            lines.append("            labelled (ADR-0025); whether to train on it "
                         "is the trainer's call.")
        else:
            lines.append(f"finish      {fin}")
        sysmsg = next((m for m in trace.get("prompt_messages") or []
                       if m.get("role") == "system"), None)
        if sysmsg:
            text = content_text(sysmsg.get("content"))
            digest = hashlib.sha256(text.encode()).hexdigest()
            lines.append(f"system      {len(text):,} chars, sha256 {digest[:16]}… "
                         "(the G2-pinned prompt — not repeated here)")
    gv = tmd.get("gsj_validation") or {}
    rs = tmd.get("reconstruction_stats") or {}
    if rs:
        lines.append(f"rebuilt     {rs.get('completions_merged')}/"
                     f"{rs.get('completions_total')} completions merged, "
                     f"{rs.get('chains_reconstructed_full')} full chain(s); "
                     f"builder findings: {len(gv.get('findings') or [])}")
    timing = sr.get("timing") or {}
    if timing.get("run_ms"):
        lines.append(f"timing      run {timing['run_ms'] / 1000:.1f}s "
                     f"(init {timing.get('init_ms', 0) / 1000:.1f}s, "
                     f"post {timing.get('postrun_ms', 0) / 1000:.1f}s)")
    return lines


# ---------------------------------------------------------------- commands

def cmd_ls(args) -> None:
    directory = Path(args.dir)
    entries = all_entries(directory)
    if not entries:
        die(f"nothing archived under {directory} (or its quarantine/).",
            "submit an episode first (README, `Submit an episode`), or point "
            "--dir at a traces directory")
    rows = [(e, *load(e)) for e in entries]
    rejected = sum(1 for _, findings, _ in rows if findings)
    print(f"{len(rows) - rejected} accepted, {rejected} quarantined "
          f"under {directory}:\n")
    for e, findings, sr in rows:
        md = sr.get("metadata") or {}
        trace = trace_of(sr)
        where = "QUARANTINE" if findings else "accepted  "
        task = (f"{md.get('case_id')}@t{md.get('timestep')}"
                if md.get("case_id") else "-")
        fin = trace.get("finish_reason") if trace else sr.get("status")
        turns = (sum(1 for m in trace.get("response_messages") or []
                     if m.get("role") == "assistant") if trace else 0)
        print(f"  {where}  {e['sid']}  {e['mode']:>12}  {task:<18} "
              f"turns {turns:>3}  {fin}")
    print("\n`./read.py show <any unique piece of an id>` renders one; "
          "`latest` is the default.")


def cmd_show(args) -> None:
    entry = resolve(Path(args.dir), args.id)
    findings, sr = load(entry)
    trace = trace_of(sr)
    for line in header_lines(entry, findings, sr, trace):
        print(line)
    if trace is None:
        print("\n(no trace arrived in this body — the session died before "
              "reconstruction; `./read.py quarantine` explains the findings, "
              "and work/sessions/ on the estate host has the harness logs)")
        return
    md = sr.get("metadata") or {}
    timestep = md.get("timestep")

    user = next((m for m in trace.get("prompt_messages") or []
                 if m.get("role") == "user"), None)
    print("\n-- the task prompt " + "-" * 50)
    print(content_text(user.get("content")).strip() if user else "(none)")

    tokenizer, why_not = (None, None)
    if qwen_think_spans(trace.get("response_ids") or []):
        tokenizer, why_not = load_tokenizer(
            args.tokenizer,
            ((sr.get("trajectory") or {}).get("metadata") or {}).get("model_used"))
    decoded = decoded_turns(trace, tokenizer)
    if tokenizer is not None and not any(d is not None for d in decoded):
        why_not = ("the loss_mask's turn boundaries do not match the message "
                   "list (mask runs != assistant turns) — the archive's own "
                   "evidence is inconsistent, so nothing was decoded")

    print("\n-- the session " + "-" * 54)
    blocks = turn_blocks(trace, decoded, timestep, args.full, why_not)
    print_session(blocks)

    print("\n-- the deliverable " + "-" * 50)
    deliverable = find_deliverable(trace)
    if deliverable:
        path, content, turn_no = deliverable
        print(f"({path}, written at turn {turn_no})\n")
        print(content.rstrip())
    else:
        print("NO deliverable was written — no `write` call happened in this "
              "session.\n(The skill asks for out/<task_id>.md; a session can "
              "qualify without one — qualification checks provenance, not "
              "task success.)")
    if trace.get("finish_reason") == "length":
        print("\n[truncated: this session ended at the generation cap "
              "(finish_reason=length) — the tail above is where it stopped, "
              "mid-stream, honestly labelled (ADR-0025)]")


def cmd_export(args) -> None:
    entry = resolve(Path(args.dir), args.id)
    findings, sr = load(entry)
    trace = trace_of(sr)
    md = sr.get("metadata") or {}
    tmd = (sr.get("trajectory") or {}).get("metadata") or {}
    out = {
        "format": "gsj-demo-episode-export/1",
        "archive": {
            "path": str(entry["path"]),
            "disposition": "quarantined" if findings or entry["quarantined"]
                           else "accepted",
            "pins_mode": entry["mode"],
        },
        "session": {k: sr.get(k) for k in
                    ("session_id", "task_id", "status", "node_id", "error")},
        "task": md or None,
        "model": {"requested": tmd.get("model_requested"),
                  "used": tmd.get("model_used"),
                  "api_type": tmd.get("api_type")} if tmd else None,
        "gate_findings": findings,
        "gsj_validation": tmd.get("gsj_validation"),
        "reconstruction_stats": tmd.get("reconstruction_stats"),
        "completion_filter": tmd.get("completion_filter"),
        "timing": sr.get("timing"),
    }
    if trace is None:
        out["trace"] = None
        print(json.dumps(out, indent=2))
        return
    mask = trace.get("loss_mask") or []
    runs = mask_runs(mask)
    ids = trace.get("response_ids") or []
    think = qwen_think_spans(ids)
    model_used = str(tmd.get("model_used") or "")
    turns = []
    hit_pages = []
    for k, turn in enumerate(turns_of(trace)):
        calls = []
        for tc in turn["msg"].get("tool_calls") or []:
            calls.append({"name": call_fn(tc).get("name"),
                          "arguments": call_fn(tc).get("arguments", "")})
        results = []
        for i, r in enumerate(turn["results"]):
            content = content_text(r.get("content"))
            results.append({"chars": len(content), "head": content[:200]})
            paired = calls[i] if i < len(calls) else None
            hits = (parse_hits(content)
                    if paired and str(paired["name"]).startswith("mcp_gsj_search")
                    else None)
            if hits:
                hit_pages.extend(h.get("page") for h in hits)
        turns.append({
            "n": k + 1,
            "content": content_text(turn["msg"].get("content")) or None,
            "tool_calls": calls,
            "results": results,
            "token_span": list(runs[k]) if k < len(runs) else None,
        })
    ws = (trace.get("metadata") or {}).get("gsj_workspace") or {}
    out.update({
        "workspace": ws or None,
        "finish_reason": trace.get("finish_reason"),
        "reward": trace.get("reward"),
        "counts": {
            "prompt_tokens": len(trace.get("prompt_ids") or []),
            "response_tokens": len(ids),
            "trainable_tokens": sum(mask),
            "trainable_share": round(sum(mask) / len(mask), 4) if mask else None,
            "assistant_turns": len(turns),
            "tool_calls": sum(len(t["tool_calls"]) for t in turns),
            "think_tokens": (sum(e - s for s, e in think)
                             if model_used.startswith("Qwen") else None),
            "think_tokens_basis": ("qwen marker ids in response_ids"
                                   if model_used.startswith("Qwen")
                                   else "not computed: non-Qwen tokenizer"),
        },
        "page_census": {
            "timestep": md.get("timestep"),
            "workspace_pages": ws.get("pages"),
            "search_pages_returned": sorted({p for p in hit_pages
                                             if isinstance(p, int)}) or None,
            "pages_beyond_timestep": sorted(
                {p for p in hit_pages if isinstance(p, int)
                 and isinstance(md.get("timestep"), int)
                 and p > md["timestep"]}) or [],
        },
        "turns": turns,
        "arrays": (
            {k: trace.get(k) for k in
             ("prompt_ids", "response_ids", "loss_mask", "response_logprobs")}
            if args.arrays else
            {"included": False,
             "where": f"{entry['path']} -> trajectory.traces[0]."
                      "{prompt_ids,response_ids,loss_mask,response_logprobs}",
             "why": "the arrays are ~95% of the body's bytes and the archive "
                    "already holds them verbatim; --arrays embeds them"}),
    })
    print(json.dumps(out, indent=2))


FINDING_MEANINGS = [
    ("ADM1:status_not_completed",
     "Polar's terminal status for the session was not COMPLETED (the suffix "
     "names what it was). The episode failed before validation even mattered.",
     "read session.error and trajectory.error in the body; the harness log "
     "under work/sessions/ on the estate host has the last words. The engine "
     "and the sandbox image are the usual suspects."),
    ("ADM2:builder_findings_present",
     "the in-server builder recorded findings while reconstructing the token "
     "arrays — the trace's own evidence is suspect.",
     "read trajectory.metadata.gsj_validation.findings in the body."),
    ("ADM3:trajectory_missing",
     "the callback carried no trajectory object at all.",
     "read session.error; this is Polar-side — check gsj-demo-polar-rollout "
     "and gsj-demo-polar-gateway logs."),
    ("ADM4:no_traces",
     "the trajectory arrived with an empty traces list — nothing was "
     "reconstructed, usually because the episode errored before the model "
     "ever completed a turn.",
     "read trajectory.error (e.g. 'no completions' means the engine never "
     "answered); check that your endpoint serves the configured model "
     "(./preflight.py) and the gateway log."),
    ("ADM5:malformed_trace",
     "a trace lacked required fields — the body does not have the shape the "
     "receiver validates.",
     "this points at a Polar/builder bug or a hand-edited body; keep the "
     "file and report it."),
    ("LP",
     "a logprob/mask-integrity check failed — the arrays that make the trace "
     "trainable are absent, mis-sized, or carry impossible values (the LP "
     "family: absent logprobs, length mismatches, sentinel/positive/"
     "non-finite values, a broken mask).",
     "read the named array in the body; this is engine- or builder-side "
     "damage, not something a resubmit fixes — if it repeats, your engine "
     "is not returning per-token logprobs the way the reference stack does."),
    ("TR1",
     "the trace's finish_reason is not one the policy allows (the suffix "
     "names it).",
     "a rare engine-side stop (e.g. content_filter); read the last turn "
     "with `./read.py show` to see where it stopped."),
    ("TR2",
     "reasoning tokens arrived loss-masked — thinking content the trainer "
     "would silently skip.",
     "a mode/builder inconsistency; check config `thinking:` against the "
     "archive stamp."),
    ("TR3",
     "the task's split is neither train nor eval.",
     "fix the taskbank row (the corpus pipeline builds split from the tree; "
     "a hand-built task carried the bad value)."),
    ("H41",
     "the full tool roster was offered and the model made ZERO tool calls — "
     "under this policy that is rejected as an untooled episode.",
     "usually a missing tool-call parser on the endpoint (./preflight.py's "
     "tool-parser row) or a model too weak to call tools."),
    ("G1:",
     "skill-card provenance failed: the episode's stated skill card hash is "
     "not in THIS estate's approved set (or the evidence is missing).",
     "if you edited corpus skills/ after `up`, re-run ./bootstrap.py up — "
     "pins re-derive from the corpus; a task submitted from another corpus's "
     "bank will always be rejected here."),
    ("G2:",
     "the system prompt's hash is not THIS estate's pin: the harness did not "
     "run with the prompt these pins were derived for.",
     "if you edited the corpus AGENTS.md after `up`, re-run ./bootstrap.py "
     "up; a different sandbox image also lands here."),
    ("G3:",
     "the tool roster differs from the pinned one — the agent did not have "
     "the pinned tool surface.",
     "check that sandbox_image in corpus.yaml is the published harness "
     "image; a different pi build lands here."),
    ("G5:",
     "the temporal-cutoff evidence failed — checkout pages vs timestep, "
     "branch naming, page contiguity, or a search hit beyond the timestep. "
     "This is THE property the estate exists to enforce.",
     "read gsj_workspace in the body (branch/pages) and the mcp results; if "
     "a search returned a page > timestep, that is an MCP-side scoping "
     "failure worth reporting with the body attached."),
    ("G6:",
     "the rendered token tail before generation is not the pinned tail. The "
     "classic cause: a thinking-mode mismatch — the submit leg and this "
     "estate's pins disagree about the mode. The other cause: your model's "
     "tokenizer/chat template is not the one the pins were derived from.",
     "compare config.yaml `thinking:` with the archive stamp on the "
     "filename; if you changed modes, re-run ./bootstrap.py up so pins AND "
     "the receiver follow. A non-Qwen model needs a tokenizer re-pin — the "
     "demo's known seam (./preflight.py names the mismatch before an "
     "episode is spent)."),
    ("G7:",
     "reconstruction evidence failed — chain count, truncation, merge "
     "totals, or the engine settings hash is not approved (sampling/engine "
     "drift).",
     "read reconstruction_stats in the body; if it is the settings hash, "
     "your engine's sampling defaults differ from the pinned ones — pin "
     "them server-side (vLLM: --generation-config) and re-run."),
]


def explain(finding: str) -> tuple:
    for prefix, meaning, todo in FINDING_MEANINGS:
        if finding.startswith(prefix):
            return meaning, todo
    return ("an unrecognised finding code — the library's checks.py is "
            "newer than this reader.",
            "read the code's docstring in gsj_rollout/checks.py; then teach "
            "read.py the new code.")


def cmd_quarantine(args) -> None:
    qdir = Path(args.dir) / "quarantine"
    entries = scan(qdir, True)
    if args.id is None:
        if not entries:
            print(f"the quarantine is empty ({qdir}) — every archived episode "
                  "passed validation.")
            return
        print(f"{len(entries)} quarantined episode(s) under {qdir}:\n")
        for e in entries:
            findings, sr = load(e)
            print(f"  {e['sid']}  ({e['mode']})")
            for f in findings:
                print(f"      {f}")
        print("\n`./read.py quarantine <any unique piece of an id>` explains "
              "each finding and what to do about it.")
        return
    entry = resolve(Path(args.dir), args.id)
    findings, sr = load(entry)
    if not findings:
        die(f"{entry['sid']} is not quarantined — it was accepted.",
            f"`./read.py show {args.id}` renders it; `quarantine` with no "
            "argument lists what WAS rejected")
    print(f"episode {sr.get('session_id')} — REJECTED with "
          f"{len(findings)} finding(s)  (archived {entry['mode']})")
    print(f"status {sr.get('status')}"
          + (f"; error: {sr.get('error')}" if sr.get("error") else ""))
    for f in findings:
        meaning, todo = explain(f)
        print(f"\n  {f}")
        print(indent(f"meaning: {meaning}", "      "))
        print(indent(f"what to do: {todo}", "      "))
    print(f"\nthe full body is {entry['path']}; `./read.py show {args.id}` "
          "renders whatever arrived (rejection kept the evidence, not "
          "discarded it — forensics beat counters).")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="the receiver's archive (default: work/traces)")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("ls", help="list the archive and the quarantine"
                   ).set_defaults(func=cmd_ls)
    show = sub.add_parser("show", help="a session transcript a person can read")
    show.add_argument("id", nargs="?", default="latest")
    show.add_argument("--full", action="store_true",
                      help="no truncation of tool results/arguments")
    show.add_argument("--tokenizer", default=None,
                      help="tokenizer.json / dir / HF id for decoding "
                           "thinking-on reasoning (default: HF cache, then hub)")
    show.set_defaults(func=cmd_show)
    exp = sub.add_parser("export", help="a structured projection (JSON, stdout)")
    exp.add_argument("id", nargs="?", default="latest")
    exp.add_argument("--arrays", action="store_true",
                     help="embed the token/mask/logprob arrays verbatim "
                          "(default: referenced — the archive already holds them)")
    exp.set_defaults(func=cmd_export)
    quar = sub.add_parser("quarantine",
                          help="rejected traces: every finding, explained")
    quar.add_argument("id", nargs="?", default=None)
    quar.set_defaults(func=cmd_quarantine)
    args = ap.parse_args()
    if args.command is None:
        args.id = None
        cmd_ls(args)
        return
    args.func(args)


if __name__ == "__main__":
    main()
