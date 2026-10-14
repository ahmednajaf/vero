"""Offline harness checks, NOT evidence that the model writes a good report."""
import json
from copy import deepcopy

import pytest

from app.knowledge.prompt_trial import FIXTURE, instructions, prepare


def fixture():
    manifest = {"version": "mechanical-fixture", "observation_year": 2025,
                "documents": [{"key": "one", "company_id": "fixture-a", "company": "Test only A",
                               "sha256": "a" * 64, "pages": [2]},
                              {"key": "two", "company_id": "fixture-b", "company": "Test only B",
                               "sha256": "b" * 64, "pages": [1]}],
                "review_only": {"expected": "HIDDEN_GOLD_ANSWER"}}
    docs = {s["key"]: {"sha256": s["sha256"], "report_id": s["key"], "title": "Test fixture",
                       "source_url": "https://example.com/report.pdf", "claims": ["OLD_EDITORIAL_FINDING"],
                       "private_path": "/private/never/send",
                       "pages": [{"pdf_page": 1, "label": "i", "text": "Original page one."},
                                 {"pdf_page": 2, "label": "1", "text": "Original page two."}]}
            for s in manifest["documents"]}
    return manifest, docs


def test_expected_answers_and_prior_editorial_claims_never_enter_model_input():
    manifest, docs = fixture()
    before = deepcopy((manifest, docs))
    result = prepare(manifest, docs, package="sector")
    text = json.dumps(result)
    assert "HIDDEN_GOLD_ANSWER" not in text
    assert "OLD_EDITORIAL_FINDING" not in text
    assert "/private/never/send" not in text
    assert (manifest, docs) == before
    data = json.loads(result["messages"][1]["content"])
    assert [e["id"] for e in data["evidence"]] == ["one:2", "two:1"]
    assert data["evidence"][0]["pdf_page"] == 2
    assert data["evidence"][0]["page_label"] == "1"
    assert data["coverage"]["completed_search_records"] == []


def test_preparation_is_reproducible_and_text_changes_change_fingerprint():
    manifest, docs = fixture()
    original = prepare(manifest, docs, package="sector")
    assert original == prepare(manifest, docs, package="sector")
    docs["one"]["pages"][1]["text"] += " Footnote."
    changed = prepare(manifest, docs, package="sector")
    assert changed["metadata"]["input_sha256"] != original["metadata"]["input_sha256"]
    assert changed["metadata"]["page_sha256"]["one:2"] != original["metadata"]["page_sha256"]["one:2"]


def test_package_changes_only_the_brief_not_the_evidence():
    manifest, docs = fixture()
    sector = prepare(manifest, docs, package="sector")
    company = prepare(manifest, docs, package="company", primary_company_id="fixture-a")
    a = json.loads(sector["messages"][1]["content"])
    b = json.loads(company["messages"][1]["content"])
    assert a["evidence"] == b["evidence"]
    assert sector["metadata"]["prompt_sha256"] == company["metadata"]["prompt_sha256"]
    assert sector["metadata"]["input_sha256"] != company["metadata"]["input_sha256"]


@pytest.mark.parametrize("package,primary,error", [
    ("company", None, "primary_company_required"),
    ("company", "outside", "primary_company_required"),
    ("sector", "fixture-a", "sector_has_no_primary_company"),
    ("unknown", None, "unknown_package"),
])
def test_explicit_package_context(package, primary, error):
    manifest, docs = fixture()
    with pytest.raises(ValueError, match=error):
        prepare(manifest, docs, package=package, primary_company_id=primary)


@pytest.mark.parametrize("change,error", [
    ("hash", "document_hash_changed"),
    ("page", "required_evidence_page_missing"),
    ("empty", "required_evidence_page_missing"),
    ("duplicate", "duplicate_evidence_id"),
])
def test_source_mismatch_is_visible_instead_of_silently_changing_trial(change, error):
    manifest, docs = fixture()
    if change == "hash":
        docs["one"]["sha256"] = "c" * 64
    elif change == "page":
        manifest["documents"][0]["pages"] = [3]
    elif change == "empty":
        docs["one"]["pages"][1]["text"] = " "
    else:
        manifest["documents"][0]["pages"] = [2, 2]
    with pytest.raises(ValueError, match=error):
        prepare(manifest, docs, package="sector")


def test_trial_does_not_claim_it_ran_inference():
    manifest, docs = fixture()
    result = prepare(manifest, docs, package="sector")
    assert result["metadata"]["api_calls"] == 0
    assert result["metadata"]["model"] is None
    assert result["metadata"]["model_evaluation_status"] == "not_run"
    assert instructions().startswith("VERO ANALYTICAL REPORT BRIEF")


def test_real_manifest_has_five_companies_multiple_reports_and_resolvable_review_pages():
    manifest = json.loads(FIXTURE.read_text())
    assert len({d["company_id"] for d in manifest["documents"]}) == 5
    assert len(manifest["documents"]) == 6
    available = {f"{d['key']}:{p}" for d in manifest["documents"] for p in d["pages"]}
    cases = manifest["review_only"]["cases"]
    assert len({c["id"] for c in cases}) == len(cases) == 12
    assert all(set(c["sources"]) <= available for c in cases)
