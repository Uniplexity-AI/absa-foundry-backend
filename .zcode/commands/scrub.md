---
description: Scrub a large file or command output with local Qwen before it enters the main agent's context
argument-hint: <file-or-text-to-scrub>
---

Scrub the following content or file using the LOCAL model only — do not read the raw content into your own context:

Target (file path or inline text): $ARGUMENTS

Procedure:
1. If the target is a file path, do NOT Read/`cat` it. Run `python customer-lifecycle-ai/scripts/local_scrub.py "$ARGUMENTS"` from the repo root, which POSTs the file content to Ollama (`http://localhost:11434/v1/chat/completions`, model `qwen2.5-coder:7b`) and prints only the distilled summary.
2. Write result to stdout and pass that distilled summary to me verbatim. Raw content must never be printed in full.
3. If Ollama is unreachable (`curl -s --max-time 5 http://localhost:11434/v1/models` fails), say so and stop — do not fall back to reading the raw file.
