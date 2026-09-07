# Custom Instructions & Sub-agent Routing

## Pre-Processing & Token Scrubbing
Before sending raw build logs, terminal outputs, or large markdown docs directly to GLM-5.3, summarize them using local Qwen 7B via standard HTTP POST to Ollama:
- Endpoint: `http://localhost:11434/v1/chat/completions`
- Model: `qwen2.5-coder:7b`

## AST Dependency Inspections
When inspecting dependencies or project structure, do NOT read raw repository folders.
Query `graphify-out/index.json` (precomputed digest — read it first), then `graphify-out/graph.json` only for drill-down via a script. Regenerate the index with `python scripts/build_graph_index.py`. The `/deps` slash command automates this.

## Token Efficiency Rules
- Pipe long shell output to a file and show at most ~50 relevant lines; never dump full logs or test output into context.
- Multi-file searches go to a read-only Explore subagent that returns only conclusions, not file contents.
- Print only aggregates when inspecting graph.json (counts/rankings), never raw node/edge dumps.

## Model Routing
| Task type | Route to |
|---|---|
| Log triage, doc summarization, distillation of large outputs | Local Qwen 2.5 Coder 7B via Ollama (`scripts/local_scrub.py`) |
| Dependency & structure questions | `graphify-out/index.json` / scripted graph queries |
| Code changes, architecture reasoning, anything mutating | GLM-5.3 (this agent) |
