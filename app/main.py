"""
FastAPI application entry point.

Exposes the document-intelligence pipeline as a typed HTTP service:

    POST /documents/upload          -> ingest a document (multipart file)
    POST /documents/demo            -> ingest the bundled sample document
    POST /documents/{job_id}/process-> run extraction + validation
    GET  /jobs/{job_id}             -> job status + stage history
    GET  /documents/{job_id}/result -> the dashboard-ready ProcessingResult
    GET  /reference/materials       -> reference catalog codes
    GET  /health                    -> liveness probe

Run locally:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .exceptions import PipelineError, UnsupportedDocumentError
from .jobs import job_store
from .logging_config import configure_logging, get_logger, log_context
from .reference_data import all_codes, catalog_size
from .schemas import (
    ErrorResponse,
    HealthResponse,
    JobStatusResponse,
    ProcessingResult,
    UploadResponse,
)

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DOCUMENT = PROJECT_ROOT / "sample_data" / "messy_input.txt"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "app.startup",
        extra=log_context(
            app=settings.app_name,
            environment=settings.environment,
            catalog_size=catalog_size(),
        ),
    )
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="Technical Document Intelligence & Workflow Automation Pipeline",
    description=(
        "Self-built, production-style demo (Pulse Method). Ingests messy technical/"
        "project documents, extracts structured data (simulated LLM step), validates "
        "it deterministically against a reference catalog, and emits a clean, "
        "dashboard-ready record. The extraction step is simulated locally — no "
        "external credentials are required to run this demo."
    ),
    version=__version__,
    lifespan=lifespan,
)


# --------------------------------------------------------------------------------------
# Exception handling — translate domain errors into typed JSON
# --------------------------------------------------------------------------------------
@app.exception_handler(PipelineError)
async def pipeline_error_handler(_: Request, exc: PipelineError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=ErrorResponse(
            code=exc.code, message=exc.message, details=exc.details
        ).model_dump(),
    )


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------
@app.get("/", tags=["meta"])
async def index() -> dict[str, str]:
    return {
        "service": app.title,
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        app=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@app.get("/reference/materials", tags=["reference"])
async def reference_materials() -> dict[str, object]:
    """Expose the reference catalog the validator checks against."""
    return {"count": catalog_size(), "codes": all_codes()}


async def _ingest(filename: str, raw_bytes: bytes) -> UploadResponse:
    settings = get_settings()

    if len(raw_bytes) == 0:
        raise UnsupportedDocumentError("Uploaded document is empty.")
    if len(raw_bytes) > settings.max_document_bytes:
        raise UnsupportedDocumentError(
            "Uploaded document exceeds the size limit.",
            details={
                "received_bytes": len(raw_bytes),
                "max_bytes": settings.max_document_bytes,
            },
        )
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError(
            "Document must be UTF-8 text (this demo simulates the OCR/text layer).",
            details={"reason": str(exc)},
        ) from exc

    record = await job_store.create(source_filename=filename, raw_text=text)
    return UploadResponse(
        job_id=record.job_id,
        status=record.status,
        source_filename=record.source_filename,
        received_bytes=len(raw_bytes),
    )


@app.post(
    "/documents/upload",
    response_model=UploadResponse,
    status_code=202,
    tags=["documents"],
)
async def upload_document(file: UploadFile) -> UploadResponse:
    """Ingest a document (multipart upload). Returns a job id in QUEUED state."""
    raw_bytes = await file.read()
    filename = file.filename or "uploaded.txt"
    return await _ingest(filename, raw_bytes)


@app.post(
    "/documents/demo",
    response_model=UploadResponse,
    status_code=202,
    tags=["documents"],
)
async def ingest_demo_document() -> UploadResponse:
    """Ingest the bundled sample document so the pipeline can be tried with no upload."""
    if not SAMPLE_DOCUMENT.exists():
        raise UnsupportedDocumentError(
            "Bundled sample document is missing.",
            details={"expected_path": str(SAMPLE_DOCUMENT)},
        )
    raw_bytes = SAMPLE_DOCUMENT.read_bytes()
    return await _ingest(SAMPLE_DOCUMENT.name, raw_bytes)


@app.post(
    "/documents/{job_id}/process",
    response_model=JobStatusResponse,
    tags=["documents"],
)
async def process_document(job_id: str) -> JobStatusResponse:
    """
    Run extraction + validation for a queued job.

    In production this would enqueue async work; for the demo it runs inline and
    returns the resulting job status (completed / needs_review / failed).
    """
    record = await job_store.run_pipeline(job_id)
    return record.to_status_response()


@app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["jobs"])
async def get_job(job_id: str) -> JobStatusResponse:
    record = await job_store.get(job_id)
    return record.to_status_response()


@app.get("/jobs", tags=["jobs"])
async def list_jobs() -> dict[str, list[str]]:
    return {"job_ids": await job_store.list_ids()}


@app.get(
    "/documents/{job_id}/result",
    response_model=ProcessingResult,
    tags=["documents"],
)
async def get_result(job_id: str) -> ProcessingResult:
    """Return the clean, dashboard-ready record once processing has completed."""
    return await job_store.get_result(job_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
