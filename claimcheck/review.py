"""Review one asset against the approved claims library.

Two passes run on every asset:

1. A lexical pass that matches each claim's prohibited phrasings. It needs no
   API key and never misses a listed phrase.
2. A model pass (Claude) that reads the asset against the whole library and
   reports contradictions, unsupported promises, and positioning drift, with a
   proposed correction for each.

Every quote the model returns is checked against the asset text. A quote that
does not appear in the asset is dropped and listed as rejected, so the report
never cites a passage that isn't there.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from .library import Claim, library_for_prompt

MODEL = "claude-opus-5-5"
VIOLATION_TYPES = ("contradiction", "unsupported", "drift")
SEVERITIES = ("high", "medium", "low")


class ReviewError(Exception):
    pass


@dataclass
class Finding:
    asset: str
    quote: str
    line: int
    claim_id: str  # an approved claim id, or "none"
    violation_type: str
    rule: str
    explanation: str
    proposed_correction: str
    severity: str
    source: str  # "lexical" or "model"


@dataclass
class AssetReview:
    asset: str
    findings: list[Finding] = field(default_factory=list)
    candidate_claims: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # model output that failed checks
    model_ran: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# --- quote verification -----------------------------------------------------

_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", " ": " "})


def _normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase, unify quotes and dashes, collapse whitespace.

    Returns the normalised string and, for each of its characters, the index
    of the original character it came from.
    """
    out, index = [], []
    prev_space = False
    for i, ch in enumerate(text.translate(_TRANSLATE)):
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch.lower())
        index.append(i)
    return "".join(out), index


def locate(text: str, quote: str) -> int | None:
    """Return the 1-based line where `quote` starts in `text`, or None."""
    norm_text, index = _normalise_with_map(text)
    norm_quote, _ = _normalise_with_map(quote.strip())
    norm_quote = norm_quote.strip(" .")
    if len(norm_quote) < 8:
        return None
    pos = norm_text.find(norm_quote)
    if pos < 0:
        return None
    return text.count("\n", 0, index[pos]) + 1


# --- lexical pass -----------------------------------------------------------

def _sentence_around(text: str, start: int, end: int) -> tuple[str, int]:
    boundary = re.compile(r"[.!?](\s|$)|\n\s*\n")
    s = 0
    for m in boundary.finditer(text, 0, start):
        s = m.end()
    m = boundary.search(text, end)
    e = m.start() + 1 if m else len(text)
    while s < len(text) and text[s].isspace():
        s += 1
    sentence = re.sub(r"\s+", " ", text[s:e]).strip()
    return sentence, s


def lexical_scan(asset: str, text: str, claims: list[Claim]) -> list[Finding]:
    findings: dict[tuple[str, int], Finding] = {}
    for claim in claims:
        for phrase in claim.prohibited:
            pattern = r"\s+".join(re.escape(w) for w in phrase.split())
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                sentence, s = _sentence_around(text, m.start(), m.end())
                key = (claim.id, s)
                if key in findings:
                    findings[key].rule += f"; '{phrase}'"
                    continue
                vtype = "drift" if claim.category == "positioning" else "contradiction"
                limits = " ".join(claim.limits)
                findings[key] = Finding(
                    asset=asset,
                    quote=sentence,
                    line=text.count("\n", 0, s) + 1,
                    claim_id=claim.id,
                    violation_type=vtype,
                    rule=f"{claim.id} prohibited phrasing: '{phrase}'",
                    explanation=f"Uses wording that {claim.id} rules out. {limits}".strip(),
                    proposed_correction=f"Rewrite in line with {claim.id}: \"{claim.statement}\"",
                    severity="high",
                    source="lexical",
                )
    return sorted(findings.values(), key=lambda f: f.line)


# --- model pass -------------------------------------------------------------

SYSTEM_PROMPT = """\
You review marketing and editorial content against an approved claims library.
Your output is a review recommendation for a human editor, who makes the final
call.

Report three kinds of problem:

- contradiction: the content says something an approved claim, its evidence,
  or its limits rule out (wrong number, unshipped feature, behaviour the
  product does not have).
- unsupported: the content makes a factual or promissory claim that no
  approved claim backs, or stretches an approved claim past its evidence (for
  example, dropping a required qualifier or promising a pilot result to every
  reader). Use claim_id "none" when no approved claim covers it at all.
- drift: the content positions the product for an audience, use, or category
  that differs from the approved positioning.

Rules for each finding:

- quote is copied exactly from the content, character for character, and is
  the shortest full sentence or clause that shows the problem. Never
  paraphrase. Findings whose quote cannot be found in the content are
  discarded.
- rule names the claim and the specific statement, evidence, or limit
  violated, for example "C2 limit: always state that the result comes from a
  pilot".
- proposed_correction is replacement text for the quoted passage that an
  editor could paste in. It must stay within the approved claims. If nothing
  approved can replace it, propose cutting it and say so.
- severity is high for anything a reader could rely on and be misled by,
  medium for overstatement, low for wording that is merely loose.

Report only real problems. Content that matches an approved claim, opinion,
and general framing that makes no claim about the product are fine and should
not be reported. If the content has no problems, return an empty findings
list.

For every unsupported claim with claim_id "none", also add an entry to
candidate_claims: a neutral statement of the claim the content is making, the
exact source quote, and why it would need approval. Do not add candidates for
anything an approved claim already covers.

Approved claims library:

{library}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "claim_id": {"type": "string"},
                    "violation_type": {"type": "string", "enum": list(VIOLATION_TYPES)},
                    "rule": {"type": "string"},
                    "explanation": {"type": "string"},
                    "proposed_correction": {"type": "string"},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                },
                "required": ["quote", "claim_id", "violation_type", "rule",
                             "explanation", "proposed_correction", "severity"],
                "additionalProperties": False,
            },
        },
        "candidate_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "source_quote": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["statement", "source_quote", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings", "candidate_claims"],
    "additionalProperties": False,
}


def _call_model(client, asset: str, text: str, claims: list[Claim]) -> dict:
    system = SYSTEM_PROMPT.format(library=library_for_prompt(claims))
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        # The library is the same for every asset in a run, so cache it.
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"Review this asset.\n\nAsset: {asset}\n\n<content>\n{text}\n</content>",
        }],
    )
    if response.stop_reason == "refusal":
        raise ReviewError(f"{asset}: the model declined to review this asset")
    if response.stop_reason == "max_tokens":
        raise ReviewError(f"{asset}: the review was cut off at max_tokens")
    body = next((b.text for b in response.content if b.type == "text"), None)
    if body is None:
        raise ReviewError(f"{asset}: the model returned no review")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"{asset}: could not parse the review ({exc})") from exc


def _overlaps(a: Finding, b: Finding) -> bool:
    x, y = a.quote.lower(), b.quote.lower()
    return a.claim_id == b.claim_id and (x in y or y in x)


def review_asset(asset: str, text: str, claims: list[Claim], client=None) -> AssetReview:
    """Review one asset. With client=None only the lexical pass runs."""
    result = AssetReview(asset=asset)
    lexical = lexical_scan(asset, text, claims)

    model_findings: list[Finding] = []
    if client is not None:
        data = _call_model(client, asset, text, claims)
        result.model_ran = True
        known = {c.id for c in claims} | {"none"}
        for raw in data.get("findings", []):
            line = locate(text, raw["quote"])
            if line is None:
                result.rejected.append({**raw, "reason": "quote not found in asset"})
                continue
            if raw["claim_id"] not in known:
                result.rejected.append({**raw, "reason": f"unknown claim id {raw['claim_id']}"})
                continue
            model_findings.append(Finding(asset=asset, line=line, source="model", **raw))
        for cand in data.get("candidate_claims", []):
            if locate(text, cand["source_quote"]) is None:
                result.rejected.append({**cand, "reason": "candidate source quote not found in asset"})
                continue
            result.candidate_claims.append({**cand, "source_asset": asset})

    # Prefer the model's finding where both passes caught the same passage:
    # it carries a specific correction. Keep lexical hits the model missed.
    merged = list(model_findings)
    for lf in lexical:
        if not any(_overlaps(lf, mf) for mf in model_findings):
            merged.append(lf)
    result.findings = sorted(merged, key=lambda f: (f.line, f.claim_id))
    return result
