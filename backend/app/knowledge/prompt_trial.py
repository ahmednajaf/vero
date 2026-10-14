"""Offline preparation of the new analytical prompt. No API or database access.

The application shares the instructions() resource loader. The preparation CLI
remains offline; expected findings are never put in model input.
Run from backend: python -m app.knowledge.prompt_trial --package sector
"""
from __future__ import annotations

import argparse
import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

VERSION = "peer-report-v1"
ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "data/prompt-evaluation/energy-analysis-v1.json"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def instructions() -> str:
    return files("app.knowledge").joinpath("prompts/peer_report_v1.txt").read_text()


def prepare(manifest: dict[str, Any], documents: dict[str, dict[str, Any]], *,
            package: str, primary_company_id: str | None = None) -> dict[str, Any]:
    """Allowlist raw evidence only. Never forward the manifest's review answers."""
    if package not in {"company", "sector"}:
        raise ValueError("unknown_package")
    companies: dict[str, dict[str, str]] = {}
    evidence, sources = [], []
    for spec in manifest["documents"]:
        doc = documents[spec["key"]]
        if doc["sha256"] != spec["sha256"]:
            raise ValueError("document_hash_changed")
        company_id = spec["company_id"]
        companies[company_id] = {"id": company_id, "name": spec["company"]}
        pages = {p["pdf_page"]: p for p in doc["pages"]}
        sources.append({"id": spec["key"], "company_id": company_id,
                        "report_id": doc["report_id"], "title": doc["title"],
                        "url": doc["source_url"], "sha256": doc["sha256"]})
        for number in spec["pages"]:
            page = pages.get(number)
            if page is None or not page["text"].strip():
                raise ValueError("required_evidence_page_missing")
            evidence.append({"id": f"{spec['key']}:{number}", "company_id": company_id,
                             "document_id": spec["key"], "pdf_page": number,
                             "page_label": page.get("label"), "text": page["text"]})
    if not companies or not evidence:
        raise ValueError("empty_evidence")
    if len({p["id"] for p in evidence}) != len(evidence):
        raise ValueError("duplicate_evidence_id")
    if package == "company" and primary_company_id not in companies:
        raise ValueError("primary_company_required")
    if package == "sector" and primary_company_id is not None:
        raise ValueError("sector_has_no_primary_company")
    payload = {"mode": "ANALYSE", "package": package,
               "primary_company_id": primary_company_id,
               "observation_year": manifest["observation_year"],
               "companies": list(companies.values()), "documents": sources,
               "evidence": evidence,
               "coverage": {"kind": "selected_pages", "completed_search_records": []}}
    prompt = instructions()
    return {"messages": [{"role": "developer", "content": prompt},
                         {"role": "user", "content": canonical(payload)}],
            "metadata": {"prompt_version": VERSION, "fixture_version": manifest["version"],
                         "prompt_sha256": digest(prompt), "input_sha256": digest(canonical(payload)),
                         "page_sha256": {p["id"]: digest(p["text"]) for p in evidence},
                         "companies": len(companies), "documents": len(sources),
                         "pages": len(evidence), "input_characters": len(canonical(payload)),
                         "model": None, "api_calls": 0, "model_evaluation_status": "not_run"}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=["company", "sector"], required=True)
    parser.add_argument("--primary-company-id")
    parser.add_argument("--corpus", type=Path, default=ROOT / "tmp/energy-2025")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(FIXTURE.read_text())
    docs = {d["key"]: json.loads((args.corpus / f"{d['key']}.json").read_text())
            for d in manifest["documents"]}
    # Verify retained bytes, not merely a claimed hash in a cached parse file.
    for spec in manifest["documents"]:
        pdf = Path(docs[spec["key"]]["path"])
        with pdf.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != spec["sha256"]:
            raise ValueError("retained_pdf_hash_changed")
    prepared = prepare(manifest, docs, package=args.package,
                       primary_company_id=args.primary_company_id)
    output = args.output or ROOT / f"tmp/prompt-trials/{VERSION}-{args.package}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve a prepared baseline; edits require another explicitly named output.
    with output.open("x") as stream:
        json.dump(prepared, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"output": str(output), **prepared["metadata"]}, indent=2))


if __name__ == "__main__":
    main()
