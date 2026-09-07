# Custom Instructions & Sub-agent Routing

These rules apply to all work in this repository (both `customer-lifecycle-ai` and any sibling projects). Project-specific notes live in subdirectory AGENTS.md files, e.g. `customer-lifecycle-ai/AGENTS.md` — follow the nearest one first.

## Pre-Processing & Token Scrubbing
Before sending raw build logs, terminal outputs, or large markdown docs directly to GLM-5.3, summarize them using local Qwen 7B via standard HTTP POST to Ollama:
- Endpoint: `http://localhost:11434/v1/chat/completions`
- Model: `qwen2.5-coder:7b`

## AST Dependency Inspections
When inspecting dependencies or project structure, do NOT read raw repository folders.
Query the local `graphify-out/graph.json` (use the nearest one: repo root or e.g. `customer-lifecycle-ai/graphify-out/graph.json`) to retrieve target file paths and imports, then pass only those specific files to GLM-5.3.
Prefer reading `customer-lifecycle-ai/graphify-out/index.json` (precomputed hub/totals digest) before opening the full graph; regenerate with `python customer-lifecycle-ai/scripts/build_graph_index.py`. Slash commands `/scrub` and `/deps` automate both workflows.

## Token Efficiency Rules

- Shell output discipline: pipe long command output to a file; show at most ~50 relevant lines via `grep`/`sed` excerpts. Never dump full logs, full test-suite output, or >200-line file reads into context when an excerpt answers the question.
- Multi-file searches and exploratory reading must be delegated to a read-only Explore subagent that returns only its conclusion, not file contents.
- Reading `graph.json` requires a script; print only aggregates (counts, rankings), never raw node/edge dumps.

## Model Routing

| Task type | Route to |
|---|---|
| Log triage, doc summarization, changelogs/draft text, large-output distillation | Local Qwen 2.5 Coder 7B via Ollama (`/scrub`) |
| Dependency & structure questions | `graphify-out/index.json`, then `graph.json` via script (`/deps`) |
| Code changes, architecture reasoning, cross-file analysis, anything mutating | GLM-5.3 (this agent) |

