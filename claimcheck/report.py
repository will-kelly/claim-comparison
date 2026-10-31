"""Render review results as Markdown and JSON."""

from __future__ import annotations

import json
from datetime import datetime

from .review import AssetReview

DISCLAIMER = (
    "This is a review recommendation, not a guarantee that the content is safe "
    "to publish. An editor decides what changes."
)

TYPE_LABEL = {"contradiction": "Contradiction", "unsupported": "Unsupported promise",
              "drift": "Positioning drift"}


def _md_escape_quote(text: str) -> str:
    return text.replace("\n", " ")


def render_markdown(reviews: list[AssetReview], proposed_added: list, when: datetime) -> str:
    total = sum(len(r.findings) for r in reviews)
    lines = [
        "# Claims consistency review",
        "",
        f"Run: {when:%Y-%m-%d %H:%M}  ",
        f"Assets: {len(reviews)}  ",
        f"Findings: {total}",
        "",
        f"> {DISCLAIMER}",
        "",
    ]
    if any(not r.model_ran for r in reviews):
        lines += [
            "> Offline run: only prohibited-phrase matching ran. Unsupported claims "
            "and drift that use other wording are not detected without the model pass.",
            "",
        ]

    for r in reviews:
        lines += [f"## {r.asset}", ""]
        if not r.findings:
            lines += ["No findings.", ""]
        for n, f in enumerate(r.findings, 1):
            lines += [
                f"### {n}. {TYPE_LABEL[f.violation_type]} · {f.claim_id} · {f.severity}",
                "",
                f"> {_md_escape_quote(f.quote)}",
                "",
                f"- **Line:** {f.line}",
                f"- **Rule:** {f.rule}",
                f"- **Why:** {f.explanation}",
                f"- **Proposed correction:** {f.proposed_correction}",
                f"- **Found by:** {f.source}",
                "",
            ]
        if r.rejected:
            lines += [
                "<details><summary>Model output discarded by verification "
                f"({len(r.rejected)})</summary>",
                "",
            ]
            for item in r.rejected:
                quote = item.get("quote") or item.get("source_quote", "")
                lines.append(f"- {item['reason']}: \"{_md_escape_quote(quote)}\"")
            lines += ["", "</details>", ""]

    lines += ["## Claims awaiting approval", ""]
    if proposed_added:
        lines.append("These were added to `claims/proposed.toml`. They are not approved "
                     "until you run `claimcheck approve <id>`.")
        lines.append("")
        for p in proposed_added:
            lines.append(f"- **{p.id}** ({p.source_asset}): {p.statement}")
    else:
        lines.append("No new claims proposed in this run.")
    lines.append("")
    return "\n".join(lines)


def render_json(reviews: list[AssetReview], proposed_added: list, when: datetime) -> str:
    return json.dumps(
        {
            "run": when.isoformat(timespec="seconds"),
            "disclaimer": DISCLAIMER,
            "reviews": [r.to_dict() for r in reviews],
            "proposed_added": [p.__dict__ for p in proposed_added],
        },
        indent=2,
        ensure_ascii=False,
    )
