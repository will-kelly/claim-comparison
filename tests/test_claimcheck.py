import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from claimcheck import evaluate, library, runner
from claimcheck.review import locate, review_asset

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project(tmp_path):
    for d in ("claims", "assets"):
        shutil.copytree(ROOT / d, tmp_path / d)
    return runner.Paths(tmp_path)


class FakeClient:
    """Stands in for anthropic.Anthropic(); returns canned reviews per asset."""

    def __init__(self, by_asset, stop_reason="end_turn"):
        self.by_asset = by_asset
        self.stop_reason = stop_reason
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["messages"][0]["content"]
        asset = prompt.split("Asset: ", 1)[1].split("\n", 1)[0]
        body = self.by_asset.get(asset, {"findings": [], "candidate_claims": []})
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(body))],
        )


def finding(quote, claim_id, vtype, correction="Rewrite."):
    return {"quote": quote, "claim_id": claim_id, "violation_type": vtype,
            "rule": f"{claim_id} rule", "explanation": "Because.",
            "proposed_correction": correction, "severity": "high"}


MODEL_OUTPUT = {
    "article.md": {
        "findings": [
            finding("Lumen will cut your review time by 40%.", "C2", "unsupported",
                    "In our 2026 pilot with four teams, median review time fell by 40%."),
            finding("Lumen is designed for any content team, from solo creators to global enterprises.",
                    "C5", "drift"),
        ],
        "candidate_claims": [],
    },
    "linkedin-post.md": {
        "findings": [
            finding("Lumen fact-checks every draft so you can publish with confidence.", "C1", "contradiction"),
            finding("Teams using Lumen cut review cycles in half.", "C2", "contradiction"),
            finding("It works where you already write: Google Docs, Notion, and Microsoft Word.", "C3",
                    "contradiction"),
            # Invented: this sentence is not in the post. It must be discarded.
            finding("Lumen replaces your editors entirely.", "C4", "contradiction"),
        ],
        "candidate_claims": [],
    },
    "website-copy.md": {
        "findings": [
            finding("Once an editor signs off, Lumen auto-publishes approved drafts to your CMS.", "C4",
                    "contradiction"),
            finding("Lumen is SOC 2 Type II certified and keeps your drafts encrypted at rest.", "none",
                    "unsupported", "Cut this line until certification is an approved claim."),
            finding("From a team of three to an enterprise-wide content organisation, Lumen grows with you.",
                    "C5", "drift"),
        ],
        "candidate_claims": [
            {"statement": "Lumen is SOC 2 Type II certified.",
             "source_quote": "Lumen is SOC 2 Type II certified",
             "rationale": "Security certification is not in the library."},
        ],
    },
}


def test_library_loads_five_claims():
    claims = library.load_claims(ROOT / "claims" / "approved.toml")
    assert [c.id for c in claims] == ["C1", "C2", "C3", "C4", "C5"]


def test_locate_tolerates_whitespace_and_curly_quotes():
    text = "Line one.\nLumen is designed for any content team, from solo creators to global\nenterprises."
    assert locate(text, "from solo creators to global enterprises") == 2
    assert locate("It’s fast.", "It's fast") == 1
    assert locate(text, "Lumen publishes for you") is None


def test_offline_review_finds_prohibited_phrases(project):
    claims = library.load_claims(project.approved)
    text = (project.assets / "article.md").read_text()
    r = review_asset("article.md", text, claims)
    assert not r.model_ran
    assert len(r.findings) == 1  # solo creators + global enterprises merge into one sentence
    f = r.findings[0]
    assert f.claim_id == "C5" and f.violation_type == "drift"
    assert "global enterprises" in f.rule
    assert locate(text, f.quote) == f.line


def test_model_review_catches_all_planted_problems_and_drops_invented_quote(project):
    client = FakeClient(MODEL_OUTPUT)
    reviews, _ = runner.run_review(project, runner.list_assets(project), client, write=False)
    result = evaluate.score(reviews, evaluate.load_expected(ROOT / "tests" / "fixtures" / "expected.toml"))
    assert result.missed == []
    assert result.invented == 1
    linkedin = next(r for r in reviews if r.asset == "linkedin-post.md")
    assert all("replaces your editors" not in f.quote for f in linkedin.findings)
    # Every reported quote really is in its asset.
    for r in reviews:
        text = (project.assets / r.asset).read_text()
        for f in r.findings:
            assert locate(text, f.quote) == f.line


def test_model_and_lexical_findings_are_deduplicated(project):
    client = FakeClient(MODEL_OUTPUT)
    reviews, _ = runner.run_review(project, [project.assets / "linkedin-post.md"], client, write=False)
    sources = [(f.claim_id, f.source) for f in reviews[0].findings]
    assert sources.count(("C1", "model")) == 1
    assert ("C1", "lexical") not in sources


def test_request_uses_structured_output_and_caches_library(project):
    client = FakeClient(MODEL_OUTPUT)
    runner.run_review(project, [project.assets / "article.md"], client, write=False)
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "[C3]" in call["system"][0]["text"]


def test_refusal_is_an_error_not_an_empty_review(project):
    from claimcheck.review import ReviewError
    client = FakeClient(MODEL_OUTPUT, stop_reason="refusal")
    with pytest.raises(ReviewError):
        runner.run_review(project, [project.assets / "article.md"], client, write=False)


def test_new_claims_are_proposed_never_approved(project):
    before = project.approved.read_text()
    client = FakeClient(MODEL_OUTPUT)
    _, out = runner.run_review(project, runner.list_assets(project), client)
    assert project.approved.read_text() == before
    proposed = library.load_proposed(project.proposed)
    assert [p.statement for p in proposed] == ["Lumen is SOC 2 Type II certified."]
    assert "P1" in out.read_text()
    # A second run does not propose the same claim again.
    runner.run_review(project, runner.list_assets(project), client)
    assert len(library.load_proposed(project.proposed)) == 1


def test_approve_requires_evidence_then_moves_claim(project):
    library.propose(project.proposed, [{"statement": "Lumen is SOC 2 Type II certified.",
                                        "source_asset": "website-copy.md",
                                        "source_quote": "SOC 2", "rationale": "r"}],
                    library.load_claims(project.approved))
    with pytest.raises(library.LibraryError, match="no evidence"):
        library.approve(project.proposed, project.approved, "P1")
    claim = library.approve(project.proposed, project.approved, "P1",
                            evidence="Audit report, 2026-08", category="governance")
    assert claim.id == "C6"
    assert [c.id for c in library.load_claims(project.approved)][-1] == "C6"
    assert library.load_proposed(project.proposed) == []


def test_report_has_disclaimer_quotes_rules_and_corrections(project):
    client = FakeClient(MODEL_OUTPUT)
    _, out = runner.run_review(project, [project.assets / "article.md"], client)
    md = out.read_text()
    assert "not a guarantee that the content is safe to publish" in md
    assert "> Lumen will cut your review time by 40%." in md
    assert "**Rule:** C2 rule" in md
    assert "In our 2026 pilot with four teams" in md


def test_change_detection(project):
    first = runner.snapshot(project)
    assert len(runner.changed_assets(project, {}, first)) == 3
    runner.save_state(project, first)
    assert runner.changed_assets(project, runner.load_state(project), first) == []

    post = project.assets / "linkedin-post.md"
    post.write_text(post.read_text() + "\nOne more line.\n")
    changed = runner.changed_assets(project, first, runner.snapshot(project))
    assert [p.name for p in changed] == ["linkedin-post.md"]

    project.approved.write_text(project.approved.read_text() + "\n# edited\n")
    assert len(runner.changed_assets(project, first, runner.snapshot(project))) == 3
