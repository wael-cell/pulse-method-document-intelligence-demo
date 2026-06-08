# Portfolio Case Study

## Autonomous Technical Document Intelligence & Workflow Automation Pipeline

> **What this is:** a **self-built, production-style demonstration project** by
> Pulse Method. It is **not** a client engagement, and the scenario, company, and
> documents in it are illustrative. There are no real client names, no claimed
> revenue savings, no measured accuracy figures, and no production deployment.
> The code is real, runs locally, and is tested — the *scenario* is a realistic
> stand-in for the kind of work this pattern is built for.
>
> Pulse Method builds operations systems, technical-review workflows, project
> documentation tooling, and AI-assisted automation. It does **not** provide
> licensed engineering services and nothing here should be read as licensed
> engineering work.

---

## Short version (Upwork portfolio entry)

**Autonomous Technical Document Intelligence & Workflow Automation Pipeline — self-built demo**

A production-style demo that turns messy project documents into clean,
dashboard-ready data. It ingests a technical document (a material schedule / scope
note, the kind an operations or construction-services admin team retypes by hand),
runs a structured-extraction step to pull out project IDs, materials, quantities,
units, dimensions, deadlines, compliance notes, and risk flags, then runs a
**deterministic validation** pass that checks every field against a reference
catalog and a rule set. Clean records pass straight through; records with bad data
(unknown material codes, impossible quantities, wrong units, inconsistent dates)
are automatically flagged and routed to a human-review queue with a precise list of
what to fix.

Built with **FastAPI + Pydantic v2**, fully typed, async, with structured JSON
logging, custom exceptions, job-status tracking, a dead-letter path for failures,
and a test suite. The extraction step is simulated locally so the whole thing runs
offline with **no external credentials** — the architecture is designed to drop a
real OCR + LLM provider into the exact same typed interface.

It's designed to **reduce manual document-review and re-keying time** and to **catch
data-entry errors before they reach a spreadsheet or dashboard**. Repo includes the
API, sample messy input, a strict output JSON schema, populated example outputs, an
architecture diagram, and a README.

---

## Long version (portfolio / GitHub)

### Project title
**Autonomous Technical Document Intelligence & Workflow Automation Pipeline**
*(self-built production-style demo — Pulse Method)*

### Problem
Operations, construction-services, and technical-admin teams sit on a recurring,
unglamorous bottleneck: documents arrive as messy PDFs, scans, exported
spreadsheets, scope notes, and material schedules, and a person has to **read each
one and retype the important fields** — project/job numbers, materials, quantities,
units, dimensions, deadlines, compliance notes, and risk items — into a spreadsheet
or system of record.

That manual step is slow, it doesn't scale with volume, and it's where errors are
born: a transposed quantity, a wrong unit of measure, a material code that doesn't
exist, a milestone date that contradicts the document. Those errors then propagate
silently into dashboards, procurement, and reporting, where they're expensive to
find and fix.

### Demo scenario
*(illustrative, not a real client)*

A mid-sized operations / construction-services firm regularly receives project
documents from multiple sources. Their admin team manually extracts the key fields
into spreadsheets so the rest of the business can use them. We model **one such
document** — a "Northgate Logistics Hub – Phase 2" material schedule with scope and
QA notes — that has been deliberately seeded with the kinds of real-world problems
these teams hit: a negative quantity, a material code not in the catalog, a unit of
measure that doesn't match the material, a completion date that predates the
document, and a compliance item left unaddressed.

### Solution
A pipeline that does the read-and-retype work automatically and, critically,
**knows when it isn't sure**. It extracts the structured fields, then runs a
separate, deterministic validation pass that checks the extracted data against a
reference material catalog and an explicit rule set. The output is a single clean,
typed record per document, plus a precise list of any issues and a clear verdict:
ready to use, or needs a human's eyes.

The key design decision is the **split between probabilistic extraction and
deterministic validation**. The extraction step (an LLM/OCR in production) is
allowed to be fuzzy; the validation step is not. That's what makes it safe to
automate the routine majority of documents while routing the risky exceptions to
a person — instead of trusting a model's output blindly.

### Workflow
1. **Ingest** — a document is uploaded; a job is created in `queued` state.
2. **Extract** — OCR/text + structured extraction produce a typed record with
   per-field confidence (simulated deterministically in the demo).
3. **Validate** — every field is checked: material codes against the catalog, units
   against what's allowed for that material, quantities for sign and range, deadlines
   for internal consistency, compliance items for open status.
4. **Route** — clean records are emitted as-is; records with errors or low confidence
   go to a **human-review queue**; hard failures go to a **dead-letter** state with a
   captured reason.
5. **Deliver** — the clean record is returned as dashboard-ready JSON (trivially
   flattened to CSV) for sync into a dashboard, database, or CRM.

### Tools / stack
- **API:** FastAPI (async endpoints, automatic OpenAPI docs)
- **Schemas / typing:** Pydantic v2 (strict models, bounded confidences, enums)
- **Validation:** hand-written deterministic rules engine + reference catalog
- **Reliability:** structured JSON logging, custom exception hierarchy, job-status
  lifecycle, dead-letter handling
- **Testing:** pytest end-to-end suite (clean-path and needs-review-path)
- **Runtime:** pure-Python, no external services or credentials required for the demo
- **Production extension points (designed-in):** OCR (Tesseract / cloud OCR), an LLM
  with JSON-mode extraction, S3-style storage, a Celery/RQ/Arq queue, Postgres for
  the reference data, and email/Slack/webhook notifications

### Features
- Typed, schema-validated output contract (one record shape for the whole business)
- Deterministic validation independent of the model: unknown material codes, unit
  mismatches, non-positive / out-of-range quantities, unparseable dimensions,
  inconsistent or stale deadlines, unaddressed compliance items, duplicate line items
- Per-field confidence with a configurable review threshold
- Automatic human-review routing with a precise, field-level fix list
- Dead-letter path so failures are captured, never silently dropped
- Full job lifecycle with stage history (`queued → extracting → validating → done`)
- Structured JSON logs suitable for a log aggregator
- Runs in one command with bundled sample data

### Example outputs
The repo ships three representative outputs (in `sample_data/`):
- **`output_populated.json`** — a clean document that validates with zero errors and
  passes straight through (`status: completed`).
- **`output_human_review.json`** — the seeded messy document: extracted correctly,
  but validation finds the planted problems and routes it to review
  (`status: needs_review`).
- **`output_validation_error.json`** — a focused look at the field-level issue records
  (error / warning / info, each with `observed`, `expected`, and a `suggested_action`).

Every output conforms to **`output_schema.json`**, the strict JSON Schema generated
directly from the Pydantic models.

### What a real business could use this for
- Converting incoming PDFs / scans / scope docs / material schedules into clean
  structured data without manual re-keying
- Catching data-entry and consistency errors **before** they reach a spreadsheet,
  dashboard, ERP, or procurement step
- Standing up a "review-only-the-exceptions" workflow so staff spend time on the
  ambiguous documents, not the routine ones
- Normalizing supplier / project documents against an internal catalog or master list
- A reusable backbone for invoice, form, compliance-checklist, inspection-report, and
  operational-report intake — same ingest → extract → validate → route shape

### Honest impact framing
This is a demonstration of capability, so the claims are about **design intent**, not
measured results:
- **Designed to reduce** the manual time spent reading and re-keying technical
  documents.
- **Designed to catch** common data-entry and consistency errors at intake rather than
  downstream.
- **Designed to scale** review effort with document *complexity* instead of document
  *volume*, by auto-passing clean records and escalating only exceptions.

Actual time savings and accuracy depend entirely on a real client's documents,
volume, and rules — which is exactly what a paid discovery/pilot would measure. No
specific percentages, dollar savings, or accuracy numbers are claimed here because
none have been measured on real client data.
