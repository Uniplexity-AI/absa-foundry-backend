---
description: Answer a dependency/structure question from the precomputed graphify index instead of raw folders or the full graph
argument-hint: <question about dependencies, hubs, structure>
---

Question: $ARGUMENTS

Procedure:
1. Read `customer-lifecycle-ai/graphify-out/index.json` (small, safe to load fully). It contains totals, file-type breakdown, and the top 30 hub files ranked by inbound links.
2. Answer from the index first. Only if the index cannot answer it, write and run a small Python script that queries `customer-lifecycle-ai/graphify-out/graph.json` — never `grep`/`ls` through source folders for dependency discovery, and never print more than ~50 lines of graph data.
3. If neither is enough, name the specific 1–3 files (from their paths in the index) worth opening directly, and read only those.
