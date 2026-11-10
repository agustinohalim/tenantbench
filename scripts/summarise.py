"""Summarise runs/<split>_runs.jsonl: leak rate per class x validator with Wilson 95% intervals,
false-rejection rate on valid queries, and exact McNemar (Holm) for V5 vs V2, V3, V4, V6.

Usage: python -I scripts/summarise.py --split dev|test
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATORS = ["V1", "V2", "V3", "V4", "V5", "V6", "V7"]
CONTRASTS = ["V2", "V3"]  # H2b; V4, V6, V7 are descriptive (prereg revision 10 Nov)


def wilson(k: int, n: int, z: float = 1.959963984540054):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on discordant counts b, c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def holm(ps: dict[str, float]) -> dict[str, float]:
    items = sorted(ps.items(), key=lambda x: x[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    a = ap.parse_args()
    rows = [json.loads(l) for l in (ROOT / "runs" / f"{a.split}_runs.jsonl").open(encoding="utf-8")]
    corpus = [r for r in rows if r["kind"] == "corpus"]
    valid = [r for r in rows if r["kind"] == "valid"]

    leak = collections.defaultdict(lambda: [0, 0, 0])  # leaks, n, run errors
    for r in corpus:
        for key in ((r["cls"], r["validator"]), ("ALL", r["validator"])):
            leak[key][1] += 1
            leak[key][0] += bool(r.get("leak"))
            leak[key][2] += r.get("leak") is None
    classes = sorted({r["cls"] for r in corpus}, key=lambda c: int(c[1:])) + ["ALL"]
    print("## Leak rate (accepted and leaking / corpus items)\n")
    print("| class | n | " + " | ".join(VALIDATORS) + " |")
    print("|---|---|" + "---|" * len(VALIDATORS))
    for c in classes:
        n = leak[(c, "V1")][1]
        cells = []
        for v in VALIDATORS:
            k, nn, _ = leak[(c, v)]
            lo, hi = wilson(k, nn)
            cells.append(f"{k} ({100 * k / nn:.1f}%; {100 * lo:.1f}–{100 * hi:.1f})" if nn else "—")
        print(f"| {c} | {n} | " + " | ".join(cells) + " |")

    print("\n## False rejection on valid queries\n")
    print("| validator | n | rejected or wrong rewrite | rate (Wilson 95%) | run errors |")
    print("|---|---|---|---|---|")
    for v in VALIDATORS:
        rs = [r for r in valid if r["validator"] == v]
        k = sum(1 for r in rs if r.get("false_reject"))
        e = sum(1 for r in rs if r.get("false_reject") is None)
        lo, hi = wilson(k, len(rs))
        print(f"| {v} | {len(rs)} | {k} | {100 * k / max(1, len(rs)):.1f}% ({100 * lo:.1f}–{100 * hi:.1f}) | {e} |")

    print("\n## Exact McNemar on corpus items, V5 vs others (Holm over 2)\n")
    by = collections.defaultdict(dict)
    for r in corpus:
        by[r["id"]][r["validator"]] = bool(r.get("leak"))
    ps, counts = {}, {}
    for o in CONTRASTS:
        b = sum(1 for d in by.values() if d.get("V5") and not d.get(o))
        c = sum(1 for d in by.values() if d.get(o) and not d.get("V5"))
        ps[o], counts[o] = mcnemar_exact(b, c), (b, c)
    adj = holm(ps)
    print("| contrast | V5 leaks only | other leaks only | p | p (Holm) |")
    print("|---|---|---|---|---|")
    for o in CONTRASTS:
        b, c = counts[o]
        print(f"| V5 vs {o} | {b} | {c} | {ps[o]:.3g} | {adj[o]:.3g} |")


if __name__ == "__main__":
    main()
