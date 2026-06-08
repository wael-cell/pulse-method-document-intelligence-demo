# Upwork Packaging Guide

Everything below is copy-and-adapt. Keep the honesty framing — it's a selling point,
not a weakness. Buyers trust "I built this demo to prove the pattern" far more than a
vague claim of a past client win they can't verify.

---

## 1. Portfolio title

Use one of these (first is recommended):

- **Document Intelligence Pipeline — AI Extraction + Validation (Self-Built Demo)**
- **Messy PDFs → Clean, Validated Data: Document Automation Pipeline (Demo)**
- **Autonomous Technical Document Intelligence & Workflow Automation (Demo)**

Keep "Demo" or "Self-Built" in the title. It's honest and it pre-empts the "is this a
real client?" question.

---

## 2. Portfolio description (paste into the portfolio item)

> **Self-built, production-style demo.** I built this to show how I turn messy
> project documents into clean, validated, dashboard-ready data.
>
> The pipeline ingests a technical document (e.g. a material schedule or scope note),
> extracts the key fields — project ID, materials, quantities, units, dimensions,
> deadlines, compliance notes, risk flags — then runs a **deterministic validation**
> pass that checks every field against a reference catalog and a rule set. Clean
> records pass straight through; records with bad data (unknown codes, impossible
> quantities, wrong units, inconsistent dates) are automatically flagged and routed to
> a human-review queue with an exact list of what to fix.
>
> Built with FastAPI + Pydantic v2 — fully typed, async, with structured logging,
> custom exceptions, job-status tracking, a dead-letter path, and a test suite. The AI
> extraction step is simulated locally so it runs offline with no credentials; the
> design drops a real OCR + LLM provider into the same interface.
>
> **Designed to** cut manual document-review/re-keying time and catch data-entry
> errors before they reach a spreadsheet or dashboard. (Demonstration project — no
> client data, no claimed metrics.)
>
> Includes: the API, sample messy input, a strict output JSON schema, populated
> example outputs, an architecture diagram, and full documentation.

---

## 3. Three images / screenshots to include

Upwork portfolio items lead with images, so make them count. Capture these three:

1. **The architecture diagram.**
   Open `docs/ARCHITECTURE.md` on GitHub (it renders the Mermaid diagram) or paste the
   diagram into [mermaid.live](https://mermaid.live) and export a PNG. This is your
   "this person thinks in systems" image. Use it as the **cover**.

2. **A before → after split.**
   Left: a slice of `sample_data/messy_input.txt` (the messy table with the bad rows).
   Right: a slice of `sample_data/output_human_review.json` showing the clean structured
   record **plus** the `validation_issues` list. Add two labels: "Messy input" and
   "Validated output + flags". This is the money shot — it shows the actual
   transformation a buyer is paying for.

3. **The live API docs (Swagger UI).**
   Run `uvicorn app.main:app --reload`, open `http://127.0.0.1:8000/docs`, and
   screenshot the endpoint list (upload / process / status / result) — ideally with one
   endpoint expanded showing the typed response schema. This proves it's a real,
   runnable service, not slideware.

> Optional 4th image if the slot exists: a screenshot of `pytest` passing in the
> terminal — quiet but credible proof it works.

---

## 4. What to write in the project description (the longer body)

Use the **long version** in [`CASE_STUDY.md`](CASE_STUDY.md). Recommended order for the
Upwork body:

1. One-line label: *"Self-built production-style demo — not a client project."*
2. **Problem** (2–3 sentences).
3. **What it does** (the 5-step workflow).
4. **The key idea**: probabilistic extraction + deterministic validation = safe to
   automate the routine, escalate the exceptions.
5. **Stack** (FastAPI, Pydantic v2, async, tests).
6. **What a real business could use it for** (bullet the document types).
7. **Honest impact framing** ("designed to reduce…", no fake metrics).
8. Link to the GitHub repo.

Keep it skimmable. Bold the nouns a buyer is searching for: *PDF extraction, document
automation, validation, dashboard, human review.*

---

## 5. Skills to tag

Tag from Upwork's skill picker (use the autocomplete — names must match its taxonomy).
Prioritize the first group:

**Core (tag all that are available):**
Python · FastAPI · API Integration · API Development · Data Extraction ·
PDF Conversion · Automation · Workflow Automation · Artificial Intelligence ·
Large Language Model · Data Processing · JSON · Data Validation · Web Application

**Secondary / situational:**
OCR (Optical Character Recognition) · Document Processing · ETL · Data Entry
Automation · Pydantic · REST API · Process Optimization · Microsoft Excel ·
Data Cleaning · Backend Development

Match the tags to each specific job post when you attach the portfolio item — Upwork
weights relevance.

---

## 6. Which job posts this asset is meant to help win

Use this portfolio item when bidding on posts like these (search Upwork for the bold
terms):

- **"PDF data extraction"** / "extract data from PDFs into Excel/CSV"
- **"Document automation"** / "automate document processing"
- **"AI workflow automation"** / "LLM automation for our operations"
- **"Invoice / form / receipt extraction"** into a spreadsheet or system
- **"Construction takeoff / material schedule"** data entry or cleanup
- **"Compliance checklist / inspection report"** processing
- **"Data cleanup / CRM data cleanup"** and normalization against a master list
- **"Operations dashboard"** that needs a clean data feed from documents
- **"Spreadsheet automation"** where the source is messy documents
- **"Python developer for data pipeline / API"**

Best-fit buyer: a small/mid-sized ops, construction-services, logistics, or
professional-services firm describing a **manual, repetitive document-to-spreadsheet**
process. When you see "our team manually enters / retypes / copies data from
[documents] into [spreadsheet]," this asset is the proof you can fix it.

---

## 7. How to explain it honestly in a client message

Short, honest, and confident — paste/adapt:

> Quick note on the portfolio piece I linked: that's a demo I built myself to prove out
> the approach, not a past client project — so there are no client names or savings
> figures attached to it, on purpose. The code is real and runs; I used a simulated AI
> extraction step so the whole thing works offline, and it's designed so a real OCR +
> LLM provider drops straight into the same structure.
>
> For your project, the part that matters most is the validation layer: it checks every
> extracted field against your own reference data and rules, so clean documents go
> straight through and anything questionable gets flagged for a quick human check
> instead of silently landing wrong in your spreadsheet. Happy to walk through how I'd
> adapt it to your actual documents on a short call.

This message does three things: states plainly it's a demo, redirects to the real
engineering value (the validation layer), and offers a next step.
