#!/usr/bin/env python3
"""Generate a compact dependency index from a graphify node-link graph.

Reads graphify-out/graph.json (or a path passed as argv[1]) and writes
graphify-out/index.json beside it with the stats agents need for
dependency/structure questions, so the 6MB graph is only opened for drill-down.
"""
import json
import os
import sys
from collections import Counter, defaultdict


def build(graph_path: str) -> dict:
    with open(graph_path, encoding="utf-8") as f:
        g = json.load(f)

    nodes = g["nodes"]
    edges = g.get("edges", g.get("links", []))
    file_of = {n["id"]: n.get("source_file", "?") for n in nodes}
    sym_count = Counter(file_of.values())

    inbound: dict[str, set] = defaultdict(set)
    outbound: dict[str, set] = defaultdict(set)
    for e in edges:
        ft = file_of.get(e["target"])
        fs = file_of.get(e["source"])
        if ft:
            inbound[ft].add(e["source"])
        if fs:
            outbound[fs].add(e["target"])

    hubs = [
        {
            "file": f,
            "inbound_links": len(inbound[f]),
            "defined_symbols": sym_count[f],
            "outbound_links": len(outbound.get(f, ())),
        }
        for f in sorted(inbound, key=lambda x: -len(inbound[x]))[:30]
    ]

    ext = Counter(os.path.splitext(f)[1] or f for f in sym_count)
    return {
        "generated_from": os.path.basename(graph_path),
        "stale_if_graph_changed": os.path.getmtime(graph_path),
        "totals": {
            "nodes": len(nodes),
            "edges": len(edges),
            "files": len(sym_count),
        },
        "file_types": dict(ext.most_common(10)),
        "top_hubs_by_inbound_links": hubs,
    }


def main() -> None:
    graph = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "graphify-out", "graph.json"
    )
    index = build(graph)
    out = os.path.join(os.path.dirname(graph), "index.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    size_kb = os.path.getsize(out) / 1024
    print(f"wrote {out} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
