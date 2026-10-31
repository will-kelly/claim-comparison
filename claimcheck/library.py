"""Approved and proposed claims: loading, proposing, and approving.

The approved library is read-only to the reviewer. New claims found in
content are written to the proposed file, and move into the approved library
only through `approve()`, which a person runs.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CATEGORIES = ("capability", "metric", "integration", "governance", "positioning")


class LibraryError(Exception):
    pass


@dataclass
class Claim:
    id: str
    category: str
    statement: str
    evidence: str = ""
    limits: list[str] = field(default_factory=list)
    prohibited: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        missing = [k for k in ("id", "category", "statement") if not d.get(k)]
        if missing:
            raise LibraryError(f"claim {d.get('id', '?')} is missing {', '.join(missing)}")
        if d["category"] not in CATEGORIES:
            raise LibraryError(f"claim {d['id']} has unknown category {d['category']!r}")
        return cls(
            id=d["id"],
            category=d["category"],
            statement=d["statement"],
            evidence=d.get("evidence", ""),
            limits=list(d.get("limits", [])),
            prohibited=list(d.get("prohibited", [])),
        )


@dataclass
class ProposedClaim:
    id: str
    statement: str
    source_asset: str
    source_quote: str
    rationale: str
    category: str = "capability"
    evidence: str = ""


def load_claims(path: Path) -> list[Claim]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    claims = [Claim.from_dict(c) for c in data.get("claims", [])]
    ids = [c.id for c in claims]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise LibraryError(f"duplicate claim ids: {', '.join(sorted(dupes))}")
    return claims


def load_proposed(path: Path) -> list[ProposedClaim]:
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [ProposedClaim(**p) for p in data.get("proposed", [])]


# --- writing -----------------------------------------------------------------

PROPOSED_HEADER = """\
# Proposed claims awaiting approval.
#
# The reviewer appends claims here when content asserts something the
# approved library does not cover. Nothing here counts as approved.
# Review each one, fill in its evidence, then run:
#
#   claimcheck approve P1
#
# or delete the entry to reject it.
"""


def _s(value: str) -> str:
    # A JSON string literal is a valid TOML basic string.
    return json.dumps(value, ensure_ascii=False)


def _list(values: list[str]) -> str:
    return "[" + ", ".join(_s(v) for v in values) + "]"


def _write_proposed(path: Path, items: list[ProposedClaim]) -> None:
    blocks = [PROPOSED_HEADER]
    for p in items:
        blocks.append(
            "\n[[proposed]]\n"
            f"id = {_s(p.id)}\n"
            f"category = {_s(p.category)}\n"
            f"statement = {_s(p.statement)}\n"
            f"evidence = {_s(p.evidence)}\n"
            f"source_asset = {_s(p.source_asset)}\n"
            f"source_quote = {_s(p.source_quote)}\n"
            f"rationale = {_s(p.rationale)}\n"
        )
    path.write_text("".join(blocks), encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _next_id(prefix: str, existing: list[str]) -> str:
    nums = [int(m.group(1)) for i in existing if (m := re.fullmatch(rf"{prefix}(\d+)", i))]
    return f"{prefix}{max(nums, default=0) + 1}"


def propose(path: Path, candidates: list[dict], approved: list[Claim]) -> list[ProposedClaim]:
    """Append new candidate claims to the proposed file, skipping duplicates.

    Each candidate is a dict with statement, source_asset, source_quote and
    rationale. Returns the entries that were actually added.
    """
    current = load_proposed(path)
    seen = {_norm(p.statement) for p in current} | {_norm(c.statement) for c in approved}
    added = []
    for cand in candidates:
        key = _norm(cand["statement"])
        if not key or key in seen:
            continue
        seen.add(key)
        item = ProposedClaim(
            id=_next_id("P", [p.id for p in current + added]),
            statement=cand["statement"],
            source_asset=cand["source_asset"],
            source_quote=cand["source_quote"],
            rationale=cand["rationale"],
        )
        added.append(item)
    if added:
        _write_proposed(path, current + added)
    return added


def approve(
    proposed_path: Path,
    approved_path: Path,
    proposed_id: str,
    evidence: str | None = None,
    category: str | None = None,
) -> Claim:
    """Move one proposed claim into the approved library.

    Refuses when the claim has no evidence: an approved claim is one you can
    back up, so the evidence has to be recorded first.
    """
    items = load_proposed(proposed_path)
    match = next((p for p in items if p.id == proposed_id), None)
    if match is None:
        raise LibraryError(f"no proposed claim with id {proposed_id}")
    evidence = (evidence or match.evidence).strip()
    if not evidence:
        raise LibraryError(
            f"{proposed_id} has no evidence. Add it in {proposed_path.name} "
            "or pass --evidence before approving."
        )
    category = category or match.category
    approved = load_claims(approved_path)
    claim = Claim(
        id=_next_id("C", [c.id for c in approved]),
        category=category,
        statement=match.statement,
        evidence=evidence,
    )
    Claim.from_dict(claim.__dict__)  # validates category
    block = (
        "\n[[claims]]\n"
        f"id = {_s(claim.id)}\n"
        f"category = {_s(claim.category)}\n"
        f"statement = {_s(claim.statement)}\n"
        f"evidence = {_s(claim.evidence)}\n"
        "limits = []\n"
        "prohibited = []\n"
    )
    text = approved_path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    approved_path.write_text(text + block, encoding="utf-8")
    _write_proposed(proposed_path, [p for p in items if p.id != proposed_id])
    return claim


def library_for_prompt(claims: list[Claim]) -> str:
    lines = []
    for c in claims:
        lines.append(f"[{c.id}] ({c.category}) {c.statement}")
        if c.evidence:
            lines.append(f"  Evidence: {c.evidence}")
        for lim in c.limits:
            lines.append(f"  Limit: {lim}")
        if c.prohibited:
            lines.append("  Prohibited phrasings: " + "; ".join(c.prohibited))
    return "\n".join(lines)
