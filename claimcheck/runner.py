"""Run reviews, write reports, and watch for file changes."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import library, report
from .review import AssetReview, review_asset

ASSET_SUFFIXES = {".md", ".txt", ".html"}


@dataclass
class Paths:
    root: Path

    @property
    def approved(self) -> Path:
        return self.root / "claims" / "approved.toml"

    @property
    def proposed(self) -> Path:
        return self.root / "claims" / "proposed.toml"

    @property
    def assets(self) -> Path:
        return self.root / "assets"

    @property
    def reviews(self) -> Path:
        return self.root / "reviews"

    @property
    def state(self) -> Path:
        return self.root / ".claimcheck" / "state.json"


def list_assets(paths: Paths) -> list[Path]:
    return sorted(p for p in paths.assets.iterdir() if p.is_file() and p.suffix in ASSET_SUFFIXES)


def run_review(paths: Paths, assets: list[Path], client=None, write: bool = True):
    """Review the given assets and write a report. Returns (reviews, report_path)."""
    claims = library.load_claims(paths.approved)
    reviews: list[AssetReview] = []
    for asset in assets:
        reviews.append(review_asset(asset.name, asset.read_text(encoding="utf-8"), claims, client))

    candidates = [c for r in reviews for c in r.candidate_claims]
    added = library.propose(paths.proposed, candidates, claims) if write else []

    when = datetime.now()
    out = None
    if write:
        paths.reviews.mkdir(parents=True, exist_ok=True)
        stem = f"review-{when:%Y%m%d-%H%M%S}"
        out = paths.reviews / f"{stem}.md"
        out.write_text(report.render_markdown(reviews, added, when), encoding="utf-8")
        (paths.reviews / f"{stem}.json").write_text(report.render_json(reviews, added, when), encoding="utf-8")
        (paths.reviews / "latest.md").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    return reviews, out


# --- change detection --------------------------------------------------------

def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(paths: Paths) -> dict[str, str]:
    snap = {"claims/approved.toml": _digest(paths.approved)}
    for asset in list_assets(paths):
        snap[f"assets/{asset.name}"] = _digest(asset)
    return snap


def changed_assets(paths: Paths, previous: dict[str, str], current: dict[str, str]) -> list[Path]:
    """Assets to re-review: all of them if the library changed, else the changed ones."""
    if previous.get("claims/approved.toml") != current["claims/approved.toml"]:
        return list_assets(paths)
    return [paths.root / k for k, v in current.items()
            if k.startswith("assets/") and previous.get(k) != v]


def load_state(paths: Paths) -> dict[str, str]:
    try:
        return json.loads(paths.state.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(paths: Paths, snap: dict[str, str]) -> None:
    paths.state.parent.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(json.dumps(snap, indent=2), encoding="utf-8")


def watch(paths: Paths, client=None, interval: float = 5.0, on_report=print) -> None:
    """Poll for changes and review what changed. Runs until interrupted.

    Only reviews run automatically. Proposed claims are written to the
    proposed file and wait there for `claimcheck approve`.
    """
    while True:
        current = snapshot(paths)
        todo = changed_assets(paths, load_state(paths), current)
        if todo:
            reviews, out = run_review(paths, todo, client)
            count = sum(len(r.findings) for r in reviews)
            on_report(f"Reviewed {', '.join(a.name for a in todo)}: {count} findings -> {out}")
            save_state(paths, current)
        time.sleep(interval)
