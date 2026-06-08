"""
Simulated structured-extraction layer.

In production this module would call an LLM (with a strict JSON schema / function
calling) plus an OCR step. For the demo it is a *deterministic local simulation*:
it parses the messy OCR-style text with heuristics and returns the same typed
``ExtractedDocument`` an LLM step would, complete with per-field confidences.

This keeps the demo fully offline and reproducible (no credentials, no network),
while preserving the real shape of the pipeline. Swapping ``mode="simulated"`` for
a real provider call is the only change required to go live.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date

from .config import Settings, get_settings
from .exceptions import ExtractionError
from .logging_config import get_logger, log_context
from .schemas import (
    ComplianceNote,
    ComplianceStatus,
    Deadline,
    ExtractedDocument,
    ExtractedMaterial,
    ExtractionMetadata,
    RiskFlag,
)
from .schemas import IssueSeverity

logger = get_logger(__name__)

_NAME_LINE = re.compile(r"^[A-Z0-9][A-Z0-9 \-&/]{5,}$")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_SPEC = re.compile(r"\b([A-Z]{2,4}\s?[A-Z]?\d{2,4}[A-Za-z0-9§\-]*)")
_COLUMN_SPLIT = re.compile(r"\s{2,}")
_LOW_CONF_HINTS = ("proprietary", "vendor", "tbd", "illegible", "unknown")


def _parse_number(token: str | None) -> float | None:
    if token is None:
        return None
    cleaned = token.strip().replace(",", "")
    if cleaned in {"", "-", "n/a", "N/A", "na", "NA"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_optional(token: str | None) -> str | None:
    if token is None:
        return None
    t = token.strip()
    if t in {"", "-", "n/a", "N/A", "na", "NA"}:
        return None
    return t


def _search(pattern: str, text: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _detect_section(line_upper: str) -> str | None:
    if "MATERIAL SCHEDULE" in line_upper:
        return "materials"
    if "KEY DATES" in line_upper:
        return "dates"
    if "COMPLIANCE" in line_upper or "QA NOTES" in line_upper:
        return "compliance"
    if line_upper.startswith("RISK") or ("RISK" in line_upper and "OPEN" in line_upper):
        return "risk"
    return None


def _is_divider(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) <= {"-", "=", "_", "*"}


def _material_confidence(raw: str, code: str | None, qty: float | None, unit: str | None) -> float:
    conf = 0.95
    if qty is None:
        conf -= 0.30
    if unit is None:
        conf -= 0.20
    if not code:
        conf -= 0.25
    lowered = raw.lower()
    if any(hint in lowered for hint in _LOW_CONF_HINTS):
        conf = min(conf, 0.60)
    return round(max(0.30, min(conf, 0.99)), 2)


def _parse_header(text: str) -> dict[str, str | date | None]:
    project_id = _search(r"Project\s*No\.?:\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    client_reference = _search(r"Client\s*PO:\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    document_type = _search(r"Document:\s*(.+?)(?:\s{2,}|\s+Rev\b|$)", text, re.IGNORECASE)
    revision = _search(r"\bRev\.?\s*([A-Za-z0-9]+)\b", text)
    location = _search(r"Location:\s*([A-Za-z .,]+)", text, re.IGNORECASE)

    issued_raw = _search(r"Issued:\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    issue_date: date | None = None
    if issued_raw:
        try:
            issue_date = date.fromisoformat(issued_raw)
        except ValueError:
            issue_date = None

    project_name: str | None = None
    for line in text.splitlines()[:10]:
        candidate = line.strip()
        if not candidate or _is_divider(candidate):
            continue
        upper = candidate.upper()
        if any(k in upper for k in ("OCR", "SCANNED", "DOCUMENT", "PROJECT NO")):
            continue
        if _detect_section(upper):
            break
        if _NAME_LINE.match(candidate):
            project_name = candidate
            break

    return {
        "project_id": project_id,
        "project_name": project_name,
        "client_reference": client_reference,
        "document_type": document_type,
        "revision": f"Rev {revision}" if revision else None,
        "issue_date": issue_date,
        "location": location.rstrip(" .") if location else None,
    }


def _parse_materials(lines: list[str]) -> list[ExtractedMaterial]:
    materials: list[ExtractedMaterial] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue
        # Skip the column header row.
        if line.lstrip().lower().startswith("item") and "code" in line.lower():
            continue
        cols = _COLUMN_SPLIT.split(line.strip())
        if len(cols) < 5:
            continue
        # Require the first column to look like a line-item index.
        if not cols[0].isdigit():
            continue

        line_item = int(cols[0])
        code = _clean_optional(cols[1])
        description = cols[2].strip()
        qty = _parse_number(cols[3]) if len(cols) > 3 else None
        unit = _clean_optional(cols[4]) if len(cols) > 4 else None
        dimensions = _clean_optional(cols[5]) if len(cols) > 5 else None
        spec_token = cols[6] if len(cols) > 6 else None
        spec_reference = None
        if spec_token:
            spec_match = _SPEC.search(spec_token)
            spec_reference = spec_match.group(1).strip() if spec_match else None

        materials.append(
            ExtractedMaterial(
                line_item=line_item,
                raw_text=line.strip(),
                material_code=code,
                description=description,
                quantity=qty,
                unit=unit.upper() if unit else None,
                dimensions=dimensions,
                spec_reference=spec_reference,
                confidence=_material_confidence(line, code, qty, unit),
            )
        )
    return materials


def _parse_deadlines(lines: list[str]) -> list[Deadline]:
    deadlines: list[Deadline] = []
    for raw_line in lines:
        line = raw_line.strip().lstrip("-").strip()
        if not line:
            continue
        date_match = _DATE.search(line)
        label = re.split(r":\s*", line)[0].strip() if ":" in line else line
        due: date | None = None
        confidence = 0.5
        if date_match:
            try:
                due = date.fromisoformat(date_match.group(1))
                confidence = 0.93
            except ValueError:
                due = None
        deadlines.append(
            Deadline(label=label, due_date=due, raw_text=line, confidence=confidence)
        )
    return deadlines


def _compliance_status(text: str) -> ComplianceStatus:
    lowered = text.lower()
    if "not yet addressed" in lowered or "not addressed" in lowered:
        return ComplianceStatus.NOT_ADDRESSED
    if "pending" in lowered or "prior to" in lowered or "to be approved" in lowered:
        return ComplianceStatus.PENDING
    if "approved" in lowered or "satisfied" in lowered or "complete" in lowered:
        return ComplianceStatus.SATISFIED
    return ComplianceStatus.UNKNOWN


def _parse_compliance(lines: list[str]) -> list[ComplianceNote]:
    notes: list[ComplianceNote] = []
    for raw_line in lines:
        line = raw_line.strip().lstrip("-").strip()
        if not line:
            continue
        spec_match = _SPEC.search(line)
        reference = spec_match.group(1).strip() if spec_match else "general"
        notes.append(
            ComplianceNote(
                reference=reference,
                requirement=line,
                status=_compliance_status(line),
                confidence=0.85 if spec_match else 0.7,
            )
        )
    return notes


def _risk_category(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ("lead time", "week", "schedule", "completion", "delay")):
        return "schedule"
    if any(k in lowered for k in ("negative", "appears", "verify", "mismatch", "missing")):
        return "data_quality"
    if any(k in lowered for k in ("proprietary", "sole source", "vendor")):
        return "procurement"
    return "general"


def _parse_risks(lines: list[str]) -> list[RiskFlag]:
    flags: list[RiskFlag] = []
    for raw_line in lines:
        line = raw_line.strip().lstrip("-").strip()
        if not line:
            continue
        flags.append(
            RiskFlag(
                category=_risk_category(line),
                description=line,
                severity=IssueSeverity.WARNING,
                source="extraction",
            )
        )
    return flags


async def extract_document(
    text: str,
    *,
    settings: Settings | None = None,
) -> tuple[ExtractedDocument, ExtractionMetadata]:
    """
    Run the (simulated) structured extraction over raw document text.

    Returns the extracted document plus extraction metadata. Raises
    ``ExtractionError`` if the input contains no usable text.
    """
    settings = settings or get_settings()
    started = time.perf_counter()

    if not text or not text.strip():
        raise ExtractionError("Document contains no extractable text.")

    # Simulate async OCR/LLM latency without blocking the event loop.
    if settings.max_simulated_latency_ms > 0:
        await asyncio.sleep(settings.max_simulated_latency_ms / 1000.0)

    header = _parse_header(text)

    section_lines: dict[str, list[str]] = {
        "materials": [],
        "dates": [],
        "compliance": [],
        "risk": [],
    }
    current: str | None = None
    for line in text.splitlines():
        if _is_divider(line):
            continue
        section = _detect_section(line.strip().upper())
        if section:
            current = section
            continue
        if current:
            section_lines[current].append(line)

    materials = _parse_materials(section_lines["materials"])
    deadlines = _parse_deadlines(section_lines["dates"])
    compliance = _parse_compliance(section_lines["compliance"])
    risks = _parse_risks(section_lines["risk"])

    document = ExtractedDocument(
        project_id=header["project_id"],
        project_name=header["project_name"],
        client_reference=header["client_reference"],
        document_type=header["document_type"],
        revision=header["revision"],
        issue_date=header["issue_date"],
        location=header["location"],
        materials=materials,
        deadlines=deadlines,
        compliance_notes=compliance,
        risk_flags=risks,
    )

    if materials:
        overall = round(sum(m.confidence for m in materials) / len(materials), 2)
    else:
        # No line items recognized: low confidence so the job routes to review.
        overall = 0.40

    duration_ms = int((time.perf_counter() - started) * 1000)
    metadata = ExtractionMetadata(
        extractor="simulated-extractor-v1",
        mode="simulated",
        document_char_count=len(text),
        materials_found=len(materials),
        overall_confidence=overall,
        duration_ms=duration_ms,
    )

    logger.info(
        "extraction.completed",
        extra=log_context(
            materials_found=len(materials),
            overall_confidence=overall,
            duration_ms=duration_ms,
        ),
    )
    return document, metadata
