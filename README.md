# Claims consistency reviewer

Checks an article, a LinkedIn post, and website copy against an approved
claims library. It flags three kinds of problem:

- **Contradiction:** the content says something an approved claim rules out.
- **Unsupported promise:** the content claims something no approved claim
  backs, or stretches a claim past its evidence.
- **Positioning drift:** the content aims the product at a different audience
  or category than the approved positioning.

Each finding gives the quoted passage, its line, the rule it breaks, and a
proposed correction.

> The output is a review recommendation, not a guarantee that content is safe
> to publish. An editor decides what changes.

## What's in the first build

| Path | What it is |
| --- | --- |
| `claims/approved.toml` | Five approved claims for a fictional product, Lumen. Replace them with yours. |
| `claims/proposed.toml` | New claims the reviewer found. They wait here for approval. |
| `assets/` | Three related assets with eight problems planted in them. |
| `tests/fixtures/expected.toml` | Answer key for the planted problems. |
| `reviews/latest.md` | Most recent report. |

## How it works

Every asset goes through two passes:

1. **Phrase matching.** Each claim lists prohibited phrasings ("fact-checks",
   "in half", "auto-publish"). These are matched literally, so they're never
   missed. This pass needs no API key.
2. **Model review.** Claude reads the asset against the whole library and
   reports contradictions, unsupported promises, and drift that use any
   wording, with a correction for each. Output is constrained to a JSON
   schema.

Then a check runs on the model's output: every quote must appear in the asset.
A quote that doesn't is discarded and listed under "discarded by verification"
in the report. The reviewer can't cite a passage that isn't there.

Where both passes catch the same passage, the report keeps the model's finding
because its correction is more specific.

## Autonomy and approval

| Runs on its own | Needs you |
| --- | --- |
| Reviews, when an asset or the approved library changes (`claimcheck watch` locally, or the GitHub Action on push) | Approving a new claim (`claimcheck approve`) |
| Writing reports to `reviews/` | Editing content |
| Adding candidate claims to `claims/proposed.toml` | Adding limits and prohibited phrasings to a claim |

The reviewer never writes to `claims/approved.toml`. A proposed claim can't be
approved without evidence.

## Setup

```bash
pip install -e ".[dev]"
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Use

Review everything in `assets/`:

```bash
claimcheck review
```

Review with phrase matching only, no API call:

```bash
claimcheck review --offline
```

Re-review whenever a file changes:

```bash
claimcheck watch
```

See and approve proposed claims:

```bash
claimcheck proposed
```

```bash
claimcheck approve P1 --evidence "SOC 2 Type II report, 2026-08" --category governance
```

Score the reviewer against the planted problems:

```bash
claimcheck eval
```

`eval` exits non-zero if any planted problem is missed or the model invents a
quote. Findings outside the answer key are listed for you to check by hand.

## Results so far

Phrase matching alone (`claimcheck eval --offline`) catches 6 of the 8 planted
problems. The two it misses need the model pass:

- "Lumen will cut your review time by 40%." The number is right, but the pilot
  qualifier is gone and the result is promised to every reader.
- "Lumen is SOC 2 Type II certified." No approved claim covers it, so it should
  be flagged and proposed as a new claim.

The model pass has been tested with a stubbed client, not yet against the live
API. Run `claimcheck eval` with an API key to get the real score.

## Using it on your own content

1. Replace the claims in `claims/approved.toml`. Keep `limits` and
   `prohibited` specific: they do most of the work.
2. Put your assets in `assets/` (`.md`, `.txt`, or `.html`).
3. Update `tests/fixtures/expected.toml` with problems you know are there, so
   `claimcheck eval` tells you whether the reviewer finds them.
4. To run it in GitHub Actions, add `ANTHROPIC_API_KEY` as a repository
   secret. Without the secret, the action runs phrase matching only.

## Model

Uses `claude-opus-5-5` with adaptive thinking, structured output, and
server-side refusal fallback. The claims library is cached across the assets
in a run.
