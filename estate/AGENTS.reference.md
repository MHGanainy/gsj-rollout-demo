# AGENTS.md — case workspace instructions

You are working inside a checkout of a case file. Follow these rules exactly.

## Ground rules

- **Tools over assertions.** Every claim must come from a tool observation
  (file read, grep, or MCP search) made in this session — never from prior
  knowledge or guesswork.
- **Never invent facts.** If the case file does not contain it, say that it
  is not in the file.
- **Facts vs. inference.** Keep cited facts strictly separate from
  inferences. Mark every inference as such and name the cited facts it
  rests on.

## Pages and citations

- Cite pages as `page:N` (for example `page:7`).
- Mapping: `page:N` ↔ `md/page_{N:04d}.md` — page 7 is the file
  `md/page_0007.md`.
- The pages present in this checkout are the entire case as it stands now.
  Never speculate about pages that are not in the checkout.

## Search

- For content questions, prefer `mcp_gsj_search_case` first; fall back to
  grep over `md/` only when search does not answer.
- Search results carry page numbers — cite them as `page:N` like any other
  observation.

## Deliverables

- Write your deliverable to `out/<task_id>.md` unless the prompt says
  otherwise. Do not create or modify any other tracked file.
