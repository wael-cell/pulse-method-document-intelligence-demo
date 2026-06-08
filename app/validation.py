"""
Deterministic validation layer.

This is the part of the pipeline that makes the output *trustworthy*. The
extraction step (LLM/OCR) is probabilistic; this step is not. Every rule here is
explicit, ordered, and reproducible, so the same document always yields the same
findings. That separation — probabilistic extraction, deterministic validation —
is what lets a business safely automate the boring 90% while routing the risky
10% to a human.

Rules implemented:
  * required header fields present
  * material codes resolve against the reference catalog
  * units are allowed for the resolved material
  * quantities are present, positive, and within sane bounds
  * dimensions parse to something numeric
  * extractor confidence meets the per-field threshold
  * deadlines are internally consistent (not before the issue date / not stale)
  * compliance items are not left unaddressed
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .config import Settings, get_settings
from .logging_config import get_logger, log_context
from .reference_data import resolve_code
from .schemas import (
    ExtractedDocument,
    ExtractionMetadata,
    IssueSeverity,
    IssueType,
    ValidationIssue,
    ValidationSummary,
)
from .schemas import ComplianceStatus

logger = get_logger(__name__)

_HAS_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class ValidationOutcome:
    """Result of validating one extracted document."""

    issues: list[ValidationIssue]
    summary: ValidationSummary
    requires_human_review: bool
    review_reasons: list[str]


def _summarize(issues: list[ValidationIssue]) -> ValidationSummary:
    errors = sum(1 for i in issues if i.severity is IssueSeverity.ERROR)
    warnings = sum(1 for i in issues if i.severity is IssueSeverity.WARNING)
    infos = sum(1 for i in issues if i.severity is IssueSeverity.INFO)
    return ValidationSummary(
        total_issues=len(issues),
        errors=errors,
        warnings=warnings,
        infos=infos,
        passed=errors == 0,
    )


def _check_header(doc: ExtractedDocument, issues: list[ValidationIssue]) -> None:
    if not doc.project_id:
        issues.append(
            ValidationIssue(
                field_path="document.project_id",
                issue_type=IssueType.MISSING_REQUIRED_FIELD,
                severity=IssueSeverity.ERROR,
                message="Project ID could not be extracted; record cannot be keyed.",
                observed=None,
                expected="A project/job number, e.g. 'NG-2241'.",
                suggested_action="Confirm the project number from the document header.",
            )
        )
    if not doc.document_type:
        issues.append(
            ValidationIssue(
                field_path="document.document_type",
                issue_type=IssueType.MISSING_REQUIRED_FIELD,
                severity=IssueSeverity.WARNING,
                message="Document type was not identified.",
                expected="e.g. 'Material Schedule', 'Scope of Work'.",
                suggested_action="Tag the document type for correct downstream routing.",
            )
        )


def _check_materials(
    doc: ExtractedDocument,
    settings: Settings,
    issues: list[ValidationIssue],
) -> None:
    seen_line_items: set[int] = set()

    for index, material in enumerate(doc.materials):
        base = f"document.materials[{index}]"

        if material.line_item in seen_line_items:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.line_item",
                    issue_type=IssueType.DUPLICATE_LINE_ITEM,
                    severity=IssueSeverity.WARNING,
                    message=f"Duplicate line item number {material.line_item}.",
                    observed=str(material.line_item),
                    suggested_action="Renumber or merge the duplicated rows.",
                )
            )
        seen_line_items.add(material.line_item)

        record = resolve_code(material.material_code)

        # --- material code ---------------------------------------------------------
        if record is None:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.material_code",
                    issue_type=IssueType.UNKNOWN_MATERIAL_CODE,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Material code '{material.material_code}' was not found in "
                        f"the reference catalog."
                    ),
                    observed=material.material_code,
                    expected="A code present in the reference material catalog.",
                    suggested_action="Map this code to a catalog entry or add it to the catalog.",
                )
            )

        # --- unit ------------------------------------------------------------------
        if material.unit is None:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.unit",
                    issue_type=IssueType.MISSING_REQUIRED_FIELD,
                    severity=IssueSeverity.WARNING,
                    message="Unit of measure is missing.",
                    expected="A unit such as EA, LF, CY, SF.",
                    suggested_action="Add the unit of measure for this line item.",
                )
            )
        elif record is not None and material.unit.upper() not in record.allowed_units:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.unit",
                    issue_type=IssueType.UNIT_MISMATCH,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Unit '{material.unit}' is not valid for {record.code} "
                        f"({record.canonical_name})."
                    ),
                    observed=material.unit,
                    expected=f"One of: {', '.join(sorted(record.allowed_units))} "
                    f"(default {record.default_unit}).",
                    suggested_action=f"Convert the quantity to {record.default_unit}.",
                )
            )

        # --- quantity --------------------------------------------------------------
        if material.quantity is None:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.quantity",
                    issue_type=IssueType.MISSING_REQUIRED_FIELD,
                    severity=IssueSeverity.WARNING,
                    message="Quantity is missing.",
                    expected="A positive number.",
                    suggested_action="Add the quantity for this line item.",
                )
            )
        elif material.quantity <= 0:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.quantity",
                    issue_type=IssueType.NON_POSITIVE_QUANTITY,
                    severity=IssueSeverity.ERROR,
                    message=f"Quantity must be positive; got {material.quantity:g}.",
                    observed=f"{material.quantity:g}",
                    expected="A value greater than 0.",
                    suggested_action="Correct the sign/value (likely a data-entry error).",
                )
            )
        elif record is not None and not (
            record.min_quantity <= material.quantity <= record.max_quantity
        ):
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.quantity",
                    issue_type=IssueType.QUANTITY_OUT_OF_RANGE,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Quantity {material.quantity:g} is outside the expected range "
                        f"[{record.min_quantity:g}, {record.max_quantity:g}] for {record.code}."
                    ),
                    observed=f"{material.quantity:g}",
                    expected=f"[{record.min_quantity:g}, {record.max_quantity:g}]",
                    suggested_action="Confirm the quantity; it may be a unit/scale error.",
                )
            )

        # --- dimensions (light check) ---------------------------------------------
        if material.dimensions and not _HAS_DIGIT.search(material.dimensions):
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.dimensions",
                    issue_type=IssueType.UNPARSEABLE_DIMENSION,
                    severity=IssueSeverity.INFO,
                    message=f"Dimensions '{material.dimensions}' contain no numeric value.",
                    observed=material.dimensions,
                    suggested_action="Confirm the dimension string if dimensions are required.",
                )
            )

        # --- confidence ------------------------------------------------------------
        if material.confidence < settings.min_field_confidence:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.confidence",
                    issue_type=IssueType.LOW_CONFIDENCE,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Extractor confidence {material.confidence:.2f} is below the "
                        f"threshold {settings.min_field_confidence:.2f}."
                    ),
                    observed=f"{material.confidence:.2f}",
                    expected=f">= {settings.min_field_confidence:.2f}",
                    suggested_action="Have a reviewer confirm this line item.",
                )
            )


def _check_deadlines(
    doc: ExtractedDocument,
    today: date,
    issues: list[ValidationIssue],
) -> None:
    for index, deadline in enumerate(doc.deadlines):
        base = f"document.deadlines[{index}]"
        if deadline.due_date is None:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.due_date",
                    issue_type=IssueType.MISSING_REQUIRED_FIELD,
                    severity=IssueSeverity.INFO,
                    message=f"No date parsed for deadline '{deadline.label}'.",
                    observed=deadline.raw_text,
                    suggested_action="Confirm the date for this milestone.",
                )
            )
            continue

        if doc.issue_date and deadline.due_date < doc.issue_date:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.due_date",
                    issue_type=IssueType.DEADLINE_BEFORE_ISSUE,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Deadline '{deadline.label}' ({deadline.due_date.isoformat()}) is "
                        f"before the document issue date ({doc.issue_date.isoformat()})."
                    ),
                    observed=deadline.due_date.isoformat(),
                    expected=f">= {doc.issue_date.isoformat()}",
                    suggested_action="Verify the milestone date with the project manager.",
                )
            )
        elif deadline.due_date < today:
            issues.append(
                ValidationIssue(
                    field_path=f"{base}.due_date",
                    issue_type=IssueType.DEADLINE_IN_PAST,
                    severity=IssueSeverity.INFO,
                    message=(
                        f"Deadline '{deadline.label}' ({deadline.due_date.isoformat()}) is "
                        f"already in the past."
                    ),
                    observed=deadline.due_date.isoformat(),
                    suggested_action="Confirm whether this milestone is complete or slipped.",
                )
            )


def _check_compliance(doc: ExtractedDocument, issues: list[ValidationIssue]) -> None:
    for index, note in enumerate(doc.compliance_notes):
        if note.status is ComplianceStatus.NOT_ADDRESSED:
            issues.append(
                ValidationIssue(
                    field_path=f"document.compliance_notes[{index}].status",
                    issue_type=IssueType.COMPLIANCE_NOT_ADDRESSED,
                    severity=IssueSeverity.WARNING,
                    message=f"Compliance item '{note.reference}' is not yet addressed.",
                    observed=note.status.value,
                    expected="satisfied / pending with an owner",
                    suggested_action="Assign an owner and track to closure before sign-off.",
                )
            )


async def validate_document(
    document: ExtractedDocument,
    metadata: ExtractionMetadata,
    *,
    settings: Settings | None = None,
    today: date | None = None,
) -> ValidationOutcome:
    """Run all deterministic validation rules and decide on human review."""
    settings = settings or get_settings()
    today = today or date.today()

    issues: list[ValidationIssue] = []
    _check_header(document, issues)
    _check_materials(document, settings, issues)
    _check_deadlines(document, today, issues)
    _check_compliance(document, issues)

    summary = _summarize(issues)

    review_reasons: list[str] = []
    if summary.errors > 0:
        review_reasons.append(
            f"{summary.errors} validation error(s) require correction before sync."
        )
    if metadata.overall_confidence < settings.review_block_threshold:
        review_reasons.append(
            f"Overall extraction confidence {metadata.overall_confidence:.2f} is below "
            f"the review threshold {settings.review_block_threshold:.2f}."
        )
    if metadata.materials_found == 0:
        review_reasons.append("No line items were recognized in the document.")

    requires_human_review = bool(review_reasons)

    logger.info(
        "validation.completed",
        extra=log_context(
            total_issues=summary.total_issues,
            errors=summary.errors,
            warnings=summary.warnings,
            requires_human_review=requires_human_review,
        ),
    )
    return ValidationOutcome(
        issues=issues,
        summary=summary,
        requires_human_review=requires_human_review,
        review_reasons=review_reasons,
    )
