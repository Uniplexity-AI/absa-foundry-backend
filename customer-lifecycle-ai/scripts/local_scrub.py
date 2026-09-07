#!/usr/bin/env python3
"""Scrub a large text file through local Qwen via Ollama, printing only a distilled summary.

Usage: python local_scrub.py <path-to-file> [-]   # '-' reads stdin
Never prints the raw content — only Qwen's summary.
"""
import json
import sys
import urllib.request

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODELS = ["qwen2.5-coder:7b", "qwen2.5-coder:3b"]  # falls back if the larger model OOMs
MAX_CHARS = 200_000  # ~50k tokens, fits qwen 7B context comfortably

PROMPT = (
    "Distill the following content into a compact summary that preserves everything "
    "an engineer needs: key decisions, errors/warnings verbatim if short, action items, "
    "and numbers that matter. Drop boilerplate, repetition, and verbose formatting. "
    "Output plain markdown, no preamble.\n\nCONTENT:\n{content}"
)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "-"]
    if len(args) < 1:
        sys.exit("usage: local_scrub.py <file-path> | '-' for stdin")
    data = sys.stdin.read() if "-" in sys.argv else open(args[0], encoding="utf-8", errors="replace").read()
    truncated = len(data) > MAX_CHARS
    content = data[:MAX_CHARS]
    if truncated:
        content += f"\n\n[TRUNCATED: showed first {MAX_CHARS} of {len(data)} characters]"

    out = None
    last_err = None
    for model in MODELS:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": PROMPT.format(content=content)}],
                "temperature": 0.2,
                "max_tokens": 800,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.load(r)
            break
        except Exception as exc:
            last_err = exc
    if out is None:
        sys.exit(f"Ollama call failed ({last_err}). Is 'ollama serve' running with {MODELS[0]} available?")
    print(out["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
