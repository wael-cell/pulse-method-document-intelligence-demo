"""
Typed schemas (Pydantic v2) for the document intelligence pipeline.

These models are the single source of truth for the API contract and the
dashboard-ready output record. They are deliberately strict: unknown fields are
rejected, confidences are bounded to [0, 1], and enums are used for any value
that downstream systems (a dashboard, a CRM sync, a spreadsheet export) need to
branch on.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------------------
class JobStatus(str, Enum):
    """Lifecycle of a single document-processing job."""

    QUEUED = "queued"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class IssueSeverity(str, Enum):
    """Severity for validation issues and risk flags."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueType(str, Enum):
    """Stable codes for deterministic validation findings."""

    UNKNOWN_MATERIAL_CODE = "unknown_material_code"
    UNIT_MISMATCH = "unit_mismatch"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    NON_POSITIVE_QUANTITY = "non_positive_quantity"
    QUANTITY_OUT_OF_RANGE = "quantity_out_of_range"
    UNPARSEABLE_DIMENSION = "unparseable_dimension"
    LOW_CONFIDENCE = "low_confidence"
    DEADLINE_IN_PAST = "deadline_in_past"
    DEADLINE_BEFORE_ISSUE = "deadline_before_issue_date"
    DUPLICATE_LINE_ITEM = "duplicate_line_item"
    COMPLIANCE_NOT_ADDRESSED = "compliance_not_addressed"


class ComplianceStatus(str, Enum):
    SATISFIED = "satisfied"
    PENDING = "pending"
    NOT_ADDRESSED = "not_addressed"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------------------
# Extracted content models
# --------------------------------------------------------------------------------------
class ExtractedMaterial(BaseModel):
    """A single line item lifted from a material schedule / takeoff table."""

    model_config = ConfigDict(extra="forbid")

    line_item: int = Field(..., ge=1, description="1-based row index within the schedule.")
    raw_text: str = Field(..., description="Original (messy) source line for traceability.")
    material_code: str | None = Field(
        default=None, description="Normalized catalog code, if one was recognized."
    )
    description: str = Field(..., description="Human-readable material description.")
    quantity: float | None = Field(default=None, description="Parsed quantity.")
    unit: str | None = Field(default=None, description="Unit of measure, e.g. EA, LF, CY, SF.")
    dimensions: str | None = Field(
        default=None, description="Raw dimension string, e.g. '8 in x 8 in x 16 in'."
    )
    spec_reference: str | None = Field(
        default=None, description="Referenced spec/standard, e.g. 'ASTM C90'."
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extractor confidence [0,1].")


class Deadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., description="What the deadline refers to.")
    due_date: date | None = Field(default=None, description="Parsed ISO date, if recognized.")
    raw_text: str = Field(..., description="Original source phrase.")
    confidence: float = Field(..., ge=0.0, le=1.0)


class ComplianceNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(..., description="Code/standard reference, e.g. 'IBC 2021 §1705'.")
    requirement: str = Field(..., description="Plain-language requirement.")
    status: ComplianceStatus = Field(default=ComplianceStatus.UNKNOWN)
    confidence: float = Field(..., ge=0.0, le=1.0)


class RiskFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., description="Risk category, e.g. 'schedule', 'data_quality'.")
    description: str = Field(..., description="What the risk is.")
    severity: IssueSeverity = Field(default=IssueSeverity.WARNING)
    source: str = Field(default="extraction", description="'extraction' or 'validation'.")


class ExtractedDocument(BaseModel):
    """Structured representation of a single technical/project document."""

    model_config = ConfigDict(extra="forbid")

    project_id: str | None = Field(default=None, description="Project / job number.")
    project_name: str | None = Field(default=None)
    client_reference: str | None = Field(default=None, description="Client PO / contract ref.")
    document_type: str | None = Field(
        default=None, description="e.g. 'Material Schedule', 'Scope of Work'."
    )
    revision: str | None = Field(default=None, description="Document revision, e.g. 'Rev C'.")
    issue_date: date | None = Field(default=None)
    location: str | None = Field(default=None, description="Project location, if stated.")
    materials: list[ExtractedMaterial] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    compliance_notes: list[ComplianceNote] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Extraction + validation metadata
# --------------------------------------------------------------------------------------
class ExtractionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extractor: str = Field(..., description="Identifier of the extraction component.")
    mode: str = Field(
        default="simulated",
        description="'simulated' for the demo; 'llm' when wired to a real provider.",
    )
    document_char_count: int = Field(..., ge=0)
    materials_found: int = Field(..., ge=0)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    duration_ms: int = Field(..., ge=0)


class ValidationIssue(BaseModel):
    """A single deterministic finding produced by the validation layer."""

    model_config = ConfigDict(extra="forbid")

    field_path: str = Field(..., description="Dotted path to the offending value.")
    issue_type: IssueType
    severity: IssueSeverity
    message: str
    observed: str | None = Field(default=None, description="The value as extracted.")
    expected: str | None = Field(default=None, description="What a valid value looks like.")
    suggested_action: str | None = Field(default=None)


class ValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_issues: int = Field(..., ge=0)
    errors: int = Field(..., ge=0)
    warnings: int = Field(..., ge=0)
    infos: int = Field(..., ge=0)
    passed: bool = Field(
        ..., description="True when there are no ERROR-severity issues."
    )


# --------------------------------------------------------------------------------------
# Final pipeline output (dashboard-ready record)
# --------------------------------------------------------------------------------------
class ProcessingResult(BaseModel):
    """The clean, dashboard/CSV/CRM-ready record emitted by the pipeline."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": (
                "Final structured output for one ingested document. Safe to sync "
                "to a dashboard, flatten to CSV, or push into a CRM."
            )
        },
    )

    schema_version: str = Field(default="1.0.0")
    job_id: str
    source_filename: str
    status: JobStatus
    document: ExtractedDocument
    extraction_metadata: ExtractionMetadata
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    validation_summary: ValidationSummary
    requires_human_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("generated_at")
    @classmethod
    def _ensure_tz(cls, value: datetime) -> datetime:
        """Guarantee timezone-aware timestamps for clean serialization."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


# --------------------------------------------------------------------------------------
# API request/response envelopes
# --------------------------------------------------------------------------------------
class UploadResponse(BaseModel):
    job_id: str
    status: JobStatus
    source_filename: str
    received_bytes: int
    message: str = "Document accepted and queued. Call /documents/{job_id}/process next."


class StageEvent(BaseModel):
    status: JobStatus
    at: datetime
    detail: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    source_filename: str
    created_at: datetime
    updated_at: datetime
    stage_history: list[StageEvent] = Field(default_factory=list)
    requires_human_review: bool = False
    error: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str
    environment: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
