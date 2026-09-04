# Token-Optimization Workflow for AI Coding Agents (ZCode / GLM + Local Ollama + Graphify)

**Goal:** cut the token volume (and cost) of AI-assisted development sessions by 80–95% by (1) never feeding raw logs/docs/files into the cloud model's context, (2) answering dependency questions from a precomputed graph index instead of file exploration, and (3) routing every task type to the cheapest model that can do it.

**Reference implementation:** `customer-lifecycle-ai` repo (ABSA PoC). Everything below is copy-paste adaptable.

---

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                        CLOUD AGENT (GLM-5.3)                       │
│   Receives ONLY: distilled summaries + small indexes + decisions   │
└───────────────▲────────────────────────────▲───────────────────────┘
                │ ~1KB digest                │ ~800-token summary
                │                            │
   ┌────────────┴───────────┐    ┌───────────┴─────────────┐
   │ graphify-out/index.json│    │  LOCAL Qwen 2.5 Coder   │
   │ (precomputed, 5KB)     │    │  7B via Ollama :11434   │
   │ built from graph.json  │    │  (scrubs logs/docs raw  │
   │ (6MB AST graph)        │    │  content before it ever │
   └────────────────────────┘    │  reaches the cloud)     │
                                 └─────────────────────────┘
```

**Three rules drive everything:**

| Rule | Mechanism |
|---|---|
| Raw content never enters the cloud context | Local Qwen scrubbing (`/scrub`) |
| Dependency questions answered from an index, not file exploration | Graphify index (`/deps`) |
| Cheap tasks go to the local model; cloud only reasons/edits | Model routing table in AGENTS.md |

---

## 2. Prerequisites

```bash
# 1. Ollama with a local coder model
ollama pull qwen2.5-coder:7b        # ~4.7GB; 3b works as fallback
ollama serve                        # default endpoint http://localhost:11434

# 2. Graphify (AST dependency graph of the repo) — any tool producing a
#    networkx node-link JSON with nodes {id, label, source_file, ...}
pip install graphify                 # or your AST graph generator
graphify build -o graphify-out/graph.json

# 3. Python 3.10+ (for the helper scripts)
```

---

## 3. Component 1 — AGENTS.md (the instruction file the agent auto-loads)

Place at the **repo root** (and optionally per-subdirectory for overrides). This is what makes the workflow *automatic* — the agent loads it every session without being told.

```markdown
# Custom Instructions & Sub-agent Routing

## Pre-Processing & Token Scrubbing
Before sending raw build logs, terminal outputs, or large markdown docs
directly to the cloud model, summarize them using local Qwen via Ollama:
- Endpoint: http://localhost:11434/v1/chat/completions
- Model: qwen2.5-coder:7b

## AST Dependency Inspections
When inspecting dependencies or project structure, do NOT read raw
repository folders.
Query `graphify-out/index.json` (precomputed digest — read it first),
then `graphify-out/graph.json` only for drill-down via a script.
Regenerate the index with `python scripts/build_graph_index.py`.
The `/deps` slash command automates this.

## Token Efficiency Rules
- Pipe long shell output to a file and show at most ~50 relevant lines;
  never dump full logs or test output into context.
- Multi-file searches go to a read-only Explore subagent that returns
  only conclusions, not file contents.
- Print only aggregates when inspecting graph.json (counts/rankings),
  never raw node/edge dumps.

## Model Routing
| Task type | Route to |
|---|---|
| Log triage, doc summarization, distillation of large outputs | Local Qwen 2.5 Coder 7B via Ollama (`scripts/local_scrub.py`) |
| Dependency & structure questions | `graphify-out/index.json` / scripted graph queries |
| Code changes, architecture reasoning, anything mutating | Cloud model (this agent) |
```

> **Key detail:** put the file at the *detected project root* (git root). If the instructions live in a subfolder, sessions opened at the root never load them.

---

## 4. Component 2 — Graph index builder (`scripts/build_graph_index.py`)

Turns the multi-MB graph into a ~5KB digest the agent can read in one shot. One-time setup; regenerate after big refactors (or wire into a git post-commit hook).

```python
#!/usr/bin/env python3
"""Generate a compact dependency index from a graphify node-link graph."""
import json, os, sys
from collections import Counter, defaultdict

def build(graph_path: str) -> dict:
    with open(graph_path, encoding="utf-8") as f:
        g = json.load(f)
    nodes, edges = g["nodes"], g.get("edges", g.get("links", []))
    file_of = {n["id"]: n.get("source_file", "?") for n in nodes}
    sym_count = Counter(file_of.values())

    inbound = defaultdict(set); outbound = defaultdict(set)
    for e in edges:
        ft, fs = file_of.get(e["target"]), file_of.get(e["source"])
        if ft: inbound[ft].add(e["source"])
        if fs: outbound[fs].add(e["target"])

    hubs = [{"file": f, "inbound_links": len(inbound[f]),
             "defined_symbols": sym_count[f],
             "outbound_links": len(outbound.get(f, ()))}
            for f in sorted(inbound, key=lambda x: -len(inbound[x]))[:30]]

    return {
        "generated_from": os.path.basename(graph_path),
        "stale_if_graph_changed": os.path.getmtime(graph_path),
        "totals": {"nodes": len(nodes), "edges": len(edges), "files": len(sym_count)},
        "file_types": dict(Counter(os.path.splitext(f)[1] for f in sym_count).most_common(10)),
        "top_hubs_by_inbound_links": hubs,
    }

if __name__ == "__main__":
    graph = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    index = build(graph)
    out = os.path.join(os.path.dirname(graph), "index.json")
    json.dump(index, open(out, "w", encoding="utf-8"), indent=2)
    print(f"wrote {out} ({os.path.getsize(out)/1024:.1f} KB)")
```

**Measured impact on the reference repo:** 6.7MB graph → 4.8KB index. Dependency questions that used to cost a script-iteration loop now cost one file read.

---

## 5. Component 3 — Local scrubber (`scripts/local_scrub.py`)

Posts file content to Ollama and prints **only the distilled summary**. Raw content never appears in the cloud session.

```python
#!/usr/bin/env python3
"""Scrub a large text file through local Qwen via Ollama.
Usage: python local_scrub.py <file>   ('-' for stdin). Prints summary only."""
import json, sys, urllib.request

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODELS = ["qwen2.5-coder:7b", "qwen2.5-coder:3b"]  # fallback if 7B OOMs
MAX_CHARS = 200_000

PROMPT = ("Distill the following content into a compact summary preserving "
          "everything an engineer needs: key decisions, errors/warnings verbatim "
          "if short, action items, and numbers that matter. Drop boilerplate. "
          "Plain markdown, no preamble.\n\nCONTENT:\n{content}")

def main():
    args = [a for a in sys.argv[1:] if a != "-"]
    data = sys.stdin.read() if "-" in sys.argv else open(args[0], encoding="utf-8", errors="replace").read()
    content = data[:MAX_CHARS] + (f"\n\n[TRUNCATED: first {MAX_CHARS} of {len(data)} chars]" if len(data) > MAX_CHARS else "")

    out, last_err = None, None
    for model in MODELS:
        req = urllib.request.Request(OLLAMA_URL, data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": PROMPT.format(content=content)}],
            "temperature": 0.2, "max_tokens": 800,
        }).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.load(r); break
        except Exception as e:
            last_err = e
    if out is None:
        sys.exit(f"Ollama call failed ({last_err})")
    print(out["choices"][0]["message"]["content"])

if __name__ == "__main__":
    main()
```

Notes: the model-fallback list matters — on busy machines the 7B sometimes OOMs on its KV cache; the 3B keeps the workflow alive.

---

## 6. Component 4 — Slash commands (`<repo>/.zcode/commands/`)

Two markdown files make the workflows one-keystroke and deterministic.

**`.zcode/commands/scrub.md`**
```markdown
---
description: Scrub a large file or command output with local Qwen before it enters the main agent's context
argument-hint: <file-or-text-to-scrub>
---
Scrub the target using the LOCAL model only — do not read the raw content into your own context:
Target: $ARGUMENTS
1. Do NOT Read/cat the file. Run: python scripts/local_scrub.py "$ARGUMENTS"
2. Pass the distilled summary to me verbatim. Raw content must never be printed in full.
3. If Ollama is unreachable, say so and stop — do not fall back to reading the raw file.
```

**`.zcode/commands/deps.md`**
```markdown
---
description: Answer a dependency/structure question from the precomputed graph index
argument-hint: <question about dependencies, hubs, structure>
---
Question: $ARGUMENTS
1. Read graphify-out/index.json (small; safe to load fully).
2. Answer from the index first. Only if insufficient, run a small Python
   script against graphify-out/graph.json — never grep/ls source folders
   for dependency discovery, never print more than ~50 lines of graph data.
3. If still insufficient, name the 1–3 specific files worth opening directly.
```

---

## 7. Component 5 — Make the index self-maintaining (optional but recommended)

```bash
# .git/hooks/post-commit
python scripts/build_graph_index.py && git add graphify-out/index.json
```
The index records the graph's mtime (`stale_if_graph_changed`) so the agent can detect staleness.

---

## 8. What this looks like in practice

| Before (typical session) | After |
|---|---|
| Agent runs `cat build.log` → 3,000 tokens of noise in context | `/scrub build.log` → ~300-token distilled summary; raw file never read |
| "What depends on X?" → agent greps 30 files across multiple turns | `/deps what depends on X` → one index read, one answer |
| Dependency analysis = re-parsing a 6.7MB JSON every time | Parse once at commit time; sessions read 4.8KB |
| Every summarization job billed to the cloud model | Summarization runs locally at $0 |
| Agent explores folders to learn structure | AGENTS.md forbids it; index is the map |

**Rules of thumb for the routing table:** if a task is *transformative* (logs→summary, doc→digest) it belongs to the local model; if it's *judgment* (code changes, architecture, review) it belongs to the cloud agent; if it's *lookup* (what-depends-on-what, where-is-X) it belongs to a precomputed index, not a model at all.

---

## 9. Rollout checklist

- [ ] Ollama installed + `qwen2.5-coder:7b` pulled (3b as fallback)
- [ ] Graphify graph generated → `graphify-out/graph.json`
- [ ] `scripts/build_graph_index.py` run → `index.json` (verify < 10KB)
- [ ] `scripts/local_scrub.py` smoke-tested against Ollama
- [ ] `AGENTS.md` at git root with the three rule blocks + routing table
- [ ] `/scrub` and `/deps` command files created
- [ ] Post-commit hook regenerating the index (optional)
- [ ] New agent session started (instruction files load at session start)

---

## 10. Lessons learned from the reference implementation

1. **AGENTS.md placement is the #1 failure mode** — it must be at the detected project root, or sessions silently run without it.
2. **Fallback models matter** — 7B local models OOM intermittently; auto-falling back to 3B keeps `/scrub` reliable.
3. **Never let the agent read raw files "just to check"** — the instruction must be absolute ("do not fall back to reading the raw file"), otherwise token discipline erodes.
4. **Filter docs out of graph rankings** — markdown requirement docs show up as high-degree "hubs" in AST graphs; they're documentation references, not code dependencies.
5. **Cap output at the source** — the "~50 lines max" rule for shell output does more for token savings than any other single rule, because verbose tool output is the biggest leak in practice.
