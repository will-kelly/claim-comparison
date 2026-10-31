"""Command-line entry point: claimcheck review | watch | approve | proposed | eval."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import evaluate, library, runner


def _client(offline: bool):
    if offline:
        return None
    try:
        import anthropic
    except ImportError:
        sys.exit("The anthropic package is not installed. Run `pip install -e .` or use --offline.")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("No ANTHROPIC_API_KEY set; trying the default credential profile. "
              "Use --offline for phrase matching only.", file=sys.stderr)
    return anthropic.Anthropic()


def _run_with_api_errors(fn):
    try:
        import anthropic
    except ImportError:
        return fn()
    try:
        return fn()
    except anthropic.AuthenticationError:
        sys.exit("Authentication failed. Set ANTHROPIC_API_KEY or run with --offline.")
    except anthropic.RateLimitError:
        sys.exit("Rate limited by the API. Wait and retry.")
    except anthropic.APIStatusError as exc:
        sys.exit(f"API error {exc.status_code}: {exc.message}")
    except anthropic.APIConnectionError:
        sys.exit("Could not reach the API. Check the network or run with --offline.")


def cmd_review(args, paths):
    assets = [Path(a).resolve() for a in args.files] or runner.list_assets(paths)
    client = _client(args.offline)
    reviews, out = _run_with_api_errors(lambda: runner.run_review(paths, assets, client))
    for r in reviews:
        print(f"{r.asset}: {len(r.findings)} findings")
    print(f"Report: {out}")
    runner.save_state(paths, runner.snapshot(paths))
    return 1 if args.fail_on_findings and any(r.findings for r in reviews) else 0


def cmd_watch(args, paths):
    client = _client(args.offline)
    print(f"Watching {paths.assets} and {paths.approved}. Ctrl-C to stop.")
    try:
        _run_with_api_errors(lambda: runner.watch(paths, client, args.interval))
    except KeyboardInterrupt:
        pass
    return 0


def cmd_proposed(args, paths):
    items = library.load_proposed(paths.proposed)
    if not items:
        print("No proposed claims.")
    for p in items:
        evidence = p.evidence or "(no evidence yet)"
        print(f"{p.id}  {p.statement}\n    from {p.source_asset}: \"{p.source_quote}\"\n    evidence: {evidence}")
    return 0


def cmd_approve(args, paths):
    try:
        claim = library.approve(paths.proposed, paths.approved, args.id, args.evidence, args.category)
    except library.LibraryError as exc:
        sys.exit(str(exc))
    print(f"Approved {args.id} as {claim.id}: {claim.statement}")
    print("Add limits and prohibited phrasings in claims/approved.toml if it needs them.")
    return 0


def cmd_eval(args, paths):
    expected = evaluate.load_expected(Path(args.key))
    client = _client(args.offline)
    reviews, _ = _run_with_api_errors(
        lambda: runner.run_review(paths, runner.list_assets(paths), client, write=False))
    result = evaluate.score(reviews, expected)
    print(evaluate.render(result))
    return 0 if not result.missed and result.invented == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="claimcheck", description=__doc__)
    parser.add_argument("--root", default=".", help="project folder holding claims/ and assets/")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("review", help="review assets against the approved claims")
    p.add_argument("files", nargs="*", help="assets to review (default: everything in assets/)")
    p.add_argument("--offline", action="store_true", help="prohibited-phrase matching only, no API call")
    p.add_argument("--fail-on-findings", action="store_true", help="exit 1 when anything is flagged")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("watch", help="re-review assets whenever they or the library change")
    p.add_argument("--interval", type=float, default=5.0, help="seconds between checks")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("proposed", help="list claims waiting for approval")
    p.set_defaults(fn=cmd_proposed)

    p = sub.add_parser("approve", help="move a proposed claim into the approved library")
    p.add_argument("id", help="proposed claim id, e.g. P1")
    p.add_argument("--evidence", help="what backs the claim (required if not already recorded)")
    p.add_argument("--category", choices=library.CATEGORIES)
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("eval", help="score the reviewer against the planted-problem answer key")
    p.add_argument("--key", default="tests/fixtures/expected.toml")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(fn=cmd_eval)

    args = parser.parse_args(argv)
    paths = runner.Paths(Path(args.root).resolve())
    return args.fn(args, paths)


if __name__ == "__main__":
    sys.exit(main())
