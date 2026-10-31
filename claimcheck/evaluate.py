"""Score a review run against the answer key of planted problems."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .review import AssetReview


@dataclass
class EvalResult:
    caught: list[dict] = field(default_factory=list)
    missed: list[dict] = field(default_factory=list)
    extra: list = field(default_factory=list)  # findings not in the key; an editor should look
    invented: int = 0  # model quotes that were not in the asset (already discarded)

    @property
    def recall(self) -> float:
        total = len(self.caught) + len(self.missed)
        return len(self.caught) / total if total else 1.0


def load_expected(path: Path) -> list[dict]:
    return tomllib.loads(path.read_text(encoding="utf-8"))["expected"]


def score(reviews: list[AssetReview], expected: list[dict]) -> EvalResult:
    result = EvalResult()
    matched_findings = set()
    for exp in expected:
        needle = exp["quote_contains"].lower()
        hit = None
        for r in reviews:
            if r.asset != exp["asset"]:
                continue
            for f in r.findings:
                if needle in f.quote.lower() or f.quote.lower().strip(" .") in needle:
                    hit = f
                    matched_findings.add(id(f))
        (result.caught if hit else result.missed).append({**exp, "finding": hit})
    for r in reviews:
        result.invented += sum(1 for x in r.rejected if "not found" in x["reason"])
        result.extra += [f for f in r.findings if id(f) not in matched_findings]
    return result


def render(result: EvalResult) -> str:
    total = len(result.caught) + len(result.missed)
    lines = [f"Caught {len(result.caught)} of {total} planted problems (recall {result.recall:.0%})."]
    for m in result.missed:
        lines.append(f"  MISSED {m['asset']}: \"{m['quote_contains']}\" ({m['claim']}, {m['type']})")
    for c in result.caught:
        f = c["finding"]
        tag = "" if f.claim_id == c["claim"] else f"  [tied to {f.claim_id}, key says {c['claim']}]"
        lines.append(f"  caught {c['asset']}: \"{c['quote_contains']}\" via {f.source}{tag}")
    lines.append(f"Findings outside the key (check by hand): {len(result.extra)}")
    for f in result.extra:
        lines.append(f"  {f.asset}:{f.line} {f.claim_id} {f.violation_type}: \"{f.quote}\"")
    lines.append(f"Model quotes not found in the asset (discarded): {result.invented}")
    return "\n".join(lines)
