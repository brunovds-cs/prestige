# Intake-to-Web AI Pipeline — Implementation Plan

Python micro-service that reads insurance claim PDFs, extracts data via LLM, fills web forms via Playwright, and logs everything to SQLite.

---

## Step 1 — Project Scaffold and Dependencies

- Initialize project with `pyproject.toml` (or `requirements.txt`)
- Dependencies: `pypdf`, `anthropic`, `playwright`, `pydantic`, `pytest`, `sqlite3` (stdlib)
- Folder structure:

```
prestige/
├── inbound_claims/          # Incoming PDFs (simulated)
├── src/
│   ├── ingestion.py         # PDF reading and detection
│   ├── extraction.py        # LLM call + JSON parsing
│   ├── automation.py        # Playwright - form filling
│   ├── logging_db.py        # SQLite audit log
│   ├── schemas.py           # Pydantic models (ClaimData)
│   └── pipeline.py          # Main orchestrator
├── web_form/
│   └── index.html           # Local dummy form
├── tests/
│   ├── test_ingestion.py
│   ├── test_extraction.py
│   ├── test_automation.py
│   └── test_pipeline.py
├── screenshots/             # Playwright error captures
├── PLAN.md
└── pyproject.toml
```

- Install Playwright browsers: `playwright install chromium`

---

## Step 2 — Pydantic Schemas and Dummy HTML Form

- Create `schemas.py` with `ClaimData` model:
  - `policyholder_name: str`
  - `policy_number: str`
  - `claim_amount: float`
  - `incident_date: str` (ISO format)
  - `raw_source: str` (source file name)
  - `confidence: float` (0-1, extraction confidence)
- Create `ProcessingResult` with status (`success | extraction_failed | automation_failed`), timestamp, optional screenshot_path, optional error_message
- Create `web_form/index.html` — form with 4 matching fields + submit button + post-submit confirmation div
- **Test:** validate schemas with valid and invalid data via pytest

---

## Step 3 — Generate Dummy Claim PDFs

- Create 3 PDFs in `inbound_claims/`:
  1. `claim_standard_01.pdf` — clean layout, clear fields (table with Policyholder, Policy #, Amount, Date)
  2. `claim_standard_02.pdf` — slightly different format, same fields
  3. `claim_messy_03.pdf` — unstructured running text, data mixed into paragraphs, formatting errors
- Use `fpdf2` or `reportlab` in a helper script `scripts/generate_pdfs.py`
- **Test:** verify all 3 PDFs exist and are readable with `pypdf`

---

## Step 4 — Ingestion Module (`ingestion.py`)

- Function `scan_inbox(path: str) -> list[Path]`: returns PDFs found in folder
- Function `extract_text(pdf_path: Path) -> str`: extracts raw text via `pypdf`
- Handle corrupted/empty PDFs with try/except and logging
- Return `None` for unreadable PDFs (don't break the pipeline)
- **Test:** test with valid PDF, empty PDF, non-PDF file, empty folder

---

## Step 5 — LLM Extraction Module (`extraction.py`)

- Function `extract_claim_data(raw_text: str, source_file: str) -> ClaimData | None`
- System prompt instructing the model to return strict JSON in the defined schema
- Use `claude-3-haiku` (fast and cheap) via `anthropic` SDK
- Force JSON output with explicit prompt instruction + parse with `json.loads` + Pydantic validation
- If the LLM returns invalid JSON or missing fields: retry 1x with a more explicit prompt
- If it fails after retry: return `None` and log the error
- **Test:** mock the Anthropic API with `unittest.mock.patch`, test with valid responses, malformed JSON, and missing fields

---

## Step 6 — Playwright Automation Module (`automation.py`)

- Function `fill_web_form(claim: ClaimData, form_url: str) -> ProcessingResult`
- Open browser (chromium, headful for demo, headless for CI)
- Navigate to form, fill each field with explicit selectors
- Click submit and wait for confirmation (wait for success element)
- On error (element not found, timeout):
  - Capture screenshot → save to `screenshots/{timestamp}_{policy_number}.png`
  - Return `ProcessingResult` with status `automation_failed`
- Close browser in `finally`
- **Test:** serve `index.html` locally with a simple server, test correct filling and simulate failure (form with removed field)

---

## Step 7 — SQLite Audit Log (`logging_db.py`)

- Create/connect database `audit.db` with table:
  ```sql
  CREATE TABLE IF NOT EXISTS processing_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL,
      source_file TEXT NOT NULL,
      status TEXT NOT NULL,
      policyholder_name TEXT,
      policy_number TEXT,
      claim_amount REAL,
      error_message TEXT,
      screenshot_path TEXT
  )
  ```
- Function `log_result(result: ProcessingResult, claim: ClaimData | None) -> None`
- Function `get_logs() -> list[dict]` — for querying/demo
- **Test:** insert success and failure records, verify queries

---

## Step 8 — Pipeline Orchestrator (`pipeline.py`)

- Function `run_pipeline(inbox_path: str, form_url: str) -> list[ProcessingResult]`
- Flow:
  1. `scan_inbox()` → list of PDFs
  2. For each PDF:
     - `extract_text()` → raw text
     - If failed → log and continue (`continue`)
     - `extract_claim_data()` → ClaimData
     - If failed → log and continue
     - `fill_web_form()` → ProcessingResult
     - `log_result()` → persist to SQLite
  3. Return list of results
- Print summary at the end: X processed, Y succeeded, Z failed
- Entry point `if __name__ == "__main__"` with argparse for `--inbox` and `--form-url`
- **Test:** end-to-end test with mocks on LLM and browser layers

---

## Step 9 — Integration Tests and Final Error Handling

- Real E2E test (no mocks): run the entire pipeline with the 3 dummy PDFs + loical form
- Failure scenarios to test:
  - Corrupted PDF → pipeline continues, log records error
  - LLM returns garbage → retry + graceful failure, log records
  - Form with missing field → screenshot captured, log records
  - Empty inbox folder → returns empty list, no error
  - No LLM API connection → timeout handled, log records
- Ensure no failure scenario causes an unhandled exception in the pipeline
- Run `pytest` with coverage > 80%

---

## Step 10 — Demo Polish and README

- Add `--headful` flag to pipeline for visible demo (browser opens on screen)
- Colored terminal output (green for success, red for failure) with each PDF's status
- Script `demo.sh` that:
  1. Starts a local HTTP server for the form (`python -m http.server`)
  2. Runs the pipeline with `--headful`
  3. Opens `audit.db` and displays logs in the terminal
- Ensure the project runs with `python -m src.pipeline --inbox ./inbound_claims --form-url http://localhost:8000/web_form/index.html`
- Clean up any debug prints, ensure `.env` with API key is in `.gitignore`

---

## Stack Summary

| Layer | Technology |
|---|---|
| PDF parsing | `pypdf` |
| LLM | Claude 3 Haiku via `anthropic` SDK |
| Validation | `pydantic` |
| Browser automation | `playwright` |
| Audit log | `sqlite3` |
| Testing | `pytest` + `unittest.mock` |
