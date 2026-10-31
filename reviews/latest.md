# Claims consistency review

Run: 2026-10-31 18:16  
Assets: 3  
Findings: 6

> This is a review recommendation, not a guarantee that the content is safe to publish. An editor decides what changes.

> Offline run: only prohibited-phrase matching ran. Unsupported claims and drift that use other wording are not detected without the model pass.

## article.md

### 1. Positioning drift · C5 · high

> Lumen is designed for any content team, from solo creators to global enterprises.

- **Line:** 24
- **Rule:** C5 prohibited phrasing: 'solo creators'; 'global enterprises'
- **Why:** Uses wording that C5 rules out. Do not position Lumen for solo creators, consumer brands, or enterprise-wide content organisations.
- **Proposed correction:** Rewrite in line with C5: "Lumen is built for B2B technology content teams of 3 to 20 people."
- **Found by:** lexical

## linkedin-post.md

### 1. Contradiction · C1 · high

> Lumen fact-checks every draft so you can publish with confidence.

- **Line:** 3
- **Rule:** C1 prohibited phrasing: 'fact-checks'
- **Why:** Uses wording that C1 rules out. Lumen flags missing sources; it does not verify whether a statement is true. Flags are suggestions for an editor to review.
- **Proposed correction:** Rewrite in line with C1: "Lumen flags statements in a draft that lack a cited source."
- **Found by:** lexical

### 2. Contradiction · C2 · high

> Teams using Lumen cut review cycles in half.

- **Line:** 5
- **Rule:** C2 prohibited phrasing: 'in half'
- **Why:** Uses wording that C2 rules out. Always state that the result comes from a pilot. Do not generalise the result to all teams or present it as typical.
- **Proposed correction:** Rewrite in line with C2: "In a 2026 pilot with four content teams, median review time fell from 3.0 days to 1.8 days, a 40% reduction."
- **Found by:** lexical

### 3. Contradiction · C3 · high

> It works where you already write: Google Docs, Notion, and Microsoft Word.

- **Line:** 7
- **Rule:** C3 prohibited phrasing: 'microsoft word'
- **Why:** Uses wording that C3 rules out. Microsoft Word and Confluence are on the roadmap, not shipped.
- **Proposed correction:** Rewrite in line with C3: "Lumen integrates with Google Docs and Notion."
- **Found by:** lexical

## website-copy.md

### 1. Contradiction · C4 · high

> Once an editor signs off, Lumen auto-publishes approved drafts to your CMS.

- **Line:** 10
- **Rule:** C4 prohibited phrasing: 'auto-publish'
- **Why:** Uses wording that C4 rules out. Never describe Lumen as publishing, auto-publishing, or pushing content live.
- **Proposed correction:** Rewrite in line with C4: "A human editor approves every change. Lumen suggests edits; it never publishes."
- **Found by:** lexical

### 2. Positioning drift · C5 · high

> From a team of three to an enterprise-wide content organisation, Lumen grows with you.

- **Line:** 18
- **Rule:** C5 prohibited phrasing: 'enterprise-wide'
- **Why:** Uses wording that C5 rules out. Do not position Lumen for solo creators, consumer brands, or enterprise-wide content organisations.
- **Proposed correction:** Rewrite in line with C5: "Lumen is built for B2B technology content teams of 3 to 20 people."
- **Found by:** lexical

## Claims awaiting approval

No new claims proposed in this run.
