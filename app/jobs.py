"""
Job store + pipeline orchestrator.

Holds the lifecycle of every document-processing job and runs the
extract -> validate -> assemble pipeline. The store is an in-memory, async-safe
dictionary for the demo; the public method surface (create / get / list /
run_pipeline) is intentionally the same shape you would back with Postgres + a
real task queue (Celery / RQ / Arq) in production.

Failure handling models a dead-letter queue: any exception during processing
moves the job to ``FAILED`` with a captured error message instead of crashing
the request, so nothing is silently lost.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import Settings, get_settings
from .exceptions import JobNotFoundError, PipelineError, ResultNotReadyError
from .extraction import extract_document
from .logging_config import get_logger, log_context
from .schemas import (
    JobStatus,
    JobStatusResponse,
    ProcessingResult,
    StageEvent,
)
from .validation import validate_document

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobRecord:
    """Internal mutable state for a single job (not exposed directly)."""

    job_id: str
    source_filename: str
    raw_text: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    stage_history: list[StageEvent] = field(default_factory=list)
    result: ProcessingResult | None = None
    error: str | None = None
    requires_human_review: bool = False

    def to_status_response(self) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=self.job_id,
            status=self.status,
            source_filename=self.source_filename,
            created_at=self.created_at,
            updated_at=self.updated_at,
            stage_history=self.stage_history,
            requires_human_review=self.requires_human_review,
            error=self.error,
        )


class JobStore:
    """Async-safe in-memory store of jobs keyed by job id."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, *, source_filename: str, raw_text: str) -> JobRecord:
        job_id = uuid.uuid4().hex
        record = JobRecord(
            job_id=job_id,
            source_filename=source_filename,
            raw_text=raw_text,
        )
        record.stage_history.append(
            StageEvent(status=JobStatus.QUEUED, at=record.created_at, detail="Job queued.")
        )
        async with self._lock:
            self._jobs[job_id] = record
        logger.info(
            "job.created",
            extra=log_context(job_id=job_id, source_filename=source_filename),
        )
        return record

    async def get(self, job_id: str) -> JobRecord:
        async with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            raise JobNotFoundError(f"No job found with id '{job_id}'.", details={"job_id": job_id})
        return record

    async def list_ids(self) -> list[str]:
        async with self._lock:
            return list(self._jobs.keys())

    async def _transition(
        self, record: JobRecord, status: JobStatus, detail: str | None = None
    ) -> None:
        async with self._lock:
            record.status = status
            record.updated_at = _utcnow()
            record.stage_history.append(
                StageEvent(status=status, at=record.updated_at, detail=detail)
            )
        logger.info(
            "job.transition",
            extra=log_context(job_id=record.job_id, status=status.value, detail=detail),
        )

    async def run_pipeline(
        self, job_id: str, *, settings: Settings | None = None
    ) -> JobRecord:
        """
        Execute extraction -> validation -> assembly for a queued job.

        Idempotent enough for a demo: re-running a completed job re-processes it.
        Any failure is captured on the record (FAILED + error) rather than raised
        to the caller, mirroring dead-letter handling.
        """
        settings = settings or get_settings()
        record = await self.get(job_id)

        try:
            await self._transition(record, JobStatus.EXTRACTING, "Running structured extraction.")
            document, extraction_meta = await extract_document(
                record.raw_text, settings=settings
            )

            await self._transition(record, JobStatus.VALIDATING, "Running deterministic validation.")
            outcome = await validate_document(document, extraction_meta, settings=settings)

            final_status = (
                JobStatus.NEEDS_REVIEW
                if outcome.requires_human_review
                else JobStatus.COMPLETED
            )

            result = ProcessingResult(
                job_id=record.job_id,
                source_filename=record.source_filename,
                status=final_status,
                document=document,
                extraction_metadata=extraction_meta,
                validation_issues=outcome.issues,
                validation_summary=outcome.summary,
                requires_human_review=outcome.requires_human_review,
                review_reasons=outcome.review_reasons,
            )

            async with self._lock:
                record.result = result
                record.requires_human_review = outcome.requires_human_review

            detail = (
                "Routed to human review queue."
                if outcome.requires_human_review
                else "Validated and ready for dashboard sync."
            )
            await self._transition(record, final_status, detail)
            return record

        except PipelineError as exc:
            await self._fail(record, exc.message)
            logger.error(
                "job.failed",
                extra=log_context(
                    job_id=job_id, error_code=exc.code, error_message=exc.message
                ),
            )
            return record
        except Exception as exc:  # noqa: BLE001 - last-resort dead-letter guard
            await self._fail(record, f"Unexpected error: {exc}")
            logger.exception("job.failed.unexpected", extra=log_context(job_id=job_id))
            return record

    async def _fail(self, record: JobRecord, message: str) -> None:
        async with self._lock:
            record.error = message
        await self._transition(record, JobStatus.FAILED, message)

    async def get_result(self, job_id: str) -> ProcessingResult:
        record = await self.get(job_id)
        if record.result is None:
            raise ResultNotReadyError(
                f"Result for job '{job_id}' is not ready (status: {record.status.value}).",
                details={"job_id": job_id, "status": record.status.value},
            )
        return record.result


# Module-level singleton store for the running app. Tests can construct their own.
job_store = JobStore()
