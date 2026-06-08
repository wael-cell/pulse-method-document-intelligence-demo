"""
Custom exception hierarchy for the pipeline.

Every error the service can raise inherits from ``PipelineError`` and carries an
``http_status`` and a stable ``code`` so the API can translate domain failures
into clean, typed JSON responses instead of leaking stack traces.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for all domain errors raised by the pipeline."""

    http_status: int = 500
    code: str = "pipeline_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class UnsupportedDocumentError(PipelineError):
    """Raised when an uploaded document is empty, too large, or the wrong type."""

    http_status = 415
    code = "unsupported_document"


class JobNotFoundError(PipelineError):
    """Raised when a referenced job id does not exist in the store."""

    http_status = 404
    code = "job_not_found"


class InvalidJobStateError(PipelineError):
    """Raised when an operation is not valid for a job's current status."""

    http_status = 409
    code = "invalid_job_state"


class ExtractionError(PipelineError):
    """Raised when the (simulated) extraction step cannot produce a record."""

    http_status = 422
    code = "extraction_failed"


class ResultNotReadyError(PipelineError):
    """Raised when a result is requested before processing has completed."""

    http_status = 409
    code = "result_not_ready"
