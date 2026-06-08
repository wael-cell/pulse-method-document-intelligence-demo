"""
End-to-end tests for the document intelligence pipeline.

These exercise the real FastAPI app through Starlette's TestClient, plus a couple
of direct assertions on the deterministic validation layer. They are designed to
prove the two paths a buyer cares about both work:
    1. a document flows upload -> process -> result, and
    2. deliberately-broken data is caught and routed to human review.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.extraction import extract_document
from app.logging_config import configure_logging
from app.main import app
from app.validation import validate_document

# Configure logging at INFO so every structured log call is actually built during
# the tests. This makes the suite exercise the same logging path the live server
# uses, catching reserved-LogRecord-key mistakes that a silent logger would hide.
configure_logging("INFO")

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_reference_catalog_exposed() -> None:
    resp = client.get("/reference/materials")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 5
    assert "CMU-8" in body["codes"]


def test_demo_document_flows_to_needs_review() -> None:
    # 1. Ingest the bundled sample (contains deliberate data problems).
    upload = client.post("/documents/demo")
    assert upload.status_code == 202
    job_id = upload.json()["job_id"]
    assert upload.json()["status"] == "queued"

    # 2. Process it.
    processed = client.post(f"/documents/{job_id}/process")
    assert processed.status_code == 200
    assert processed.json()["status"] == "needs_review"
    assert processed.json()["requires_human_review"] is True

    # 3. Retrieve the dashboard-ready result.
    result = client.get(f"/documents/{job_id}/result")
    assert result.status_code == 200
    body = result.json()

    # Header was extracted.
    assert body["document"]["project_id"] == "NG-2241"
    assert body["document"]["client_reference"] == "PO-88321-A"

    # The validator found the planted problems.
    issue_types = {i["issue_type"] for i in body["validation_issues"]}
    assert "unknown_material_code" in issue_types   # XZ-9981
    assert "non_positive_quantity" in issue_types   # negative insulation qty
    assert "unit_mismatch" in issue_types           # EMT measured in BX
    assert "deadline_before_issue_date" in issue_types

    # Summary is internally consistent.
    summary = body["validation_summary"]
    assert summary["errors"] >= 1
    assert summary["passed"] is False
    assert summary["total_issues"] == len(body["validation_issues"])


def test_unknown_job_returns_404() -> None:
    resp = client.get("/jobs/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == "job_not_found"


def test_result_before_processing_returns_409() -> None:
    upload = client.post("/documents/demo")
    job_id = upload.json()["job_id"]
    resp = client.get(f"/documents/{job_id}/result")
    assert resp.status_code == 409
    assert resp.json()["code"] == "result_not_ready"


def test_empty_upload_rejected() -> None:
    resp = client.post(
        "/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 415
    assert resp.json()["code"] == "unsupported_document"


def test_clean_document_completes_without_review() -> None:
    """A tidy document with valid codes/units should validate cleanly."""
    clean_text = (
        "GREENFIELD WAREHOUSE\n"
        "Project No.: GW-1001 | Client PO: PO-55012\n"
        "Document: Material Schedule Rev A\n"
        "Issued: 2026-05-01 Location: Austin, TX\n"
        "--------------------------------------------------\n"
        "MATERIAL SCHEDULE (takeoff)\n"
        "Item  Code      Description            Qty   Unit  Dimensions  Spec\n"
        "1     CMU-8     8in cmu standard       1200  EA    8x8x16      ASTM C90\n"
        "2     PVC-4     pvc pipe 4in sch40     800   LF    4 in        ASTM D1785\n"
        "--------------------------------------------------\n"
        "KEY DATES\n"
        "- Submittals due: 2026-06-15\n"
    )

    async def _run():
        document, meta = await extract_document(clean_text)
        outcome = await validate_document(document, meta)
        return document, outcome

    document, outcome = asyncio.run(_run())
    assert len(document.materials) == 2
    assert outcome.summary.errors == 0
    assert outcome.requires_human_review is False
