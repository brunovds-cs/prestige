# Prestige — System Architecture

## Overview

Prestige is an **insurance claim processing pipeline** that automates the end-to-end flow of reading claim PDFs, extracting structured data using an LLM, submitting that data to a web form via browser automation, and logging every action to an audit database.

The system is designed around four independent modules connected by a central orchestrator. Each module can be tested and used in isolation. The pipeline never crashes — every failure is caught, logged, and the next PDF continues processing.

```
                         PIPELINE FLOW

  inbound_claims/          src/ingestion.py        src/extraction.py
  ┌──────────┐            ┌──────────────┐        ┌──────────────────┐
  │ PDF file │──scan──>   │ Extract raw  │──text──>│ Send to LLM      │
  │ PDF file │            │ text from    │        │ (OpenRouter API)  │
  │ PDF file │            │ each PDF     │        │ Parse JSON into   │
  └──────────┘            └──────────────┘        │ ClaimData model   │
                                                   └────────┬─────────┘
                                                            │
                                                      ClaimData
                                                            │
                                                            v
  audit.db                 src/logging_db.py        src/automation.py
  ┌──────────┐            ┌──────────────┐        ┌──────────────────┐
  │processing│<──insert── │ Log result   │<─result─│ Open Chromium    │
  │  _log    │            │ to SQLite    │        │ Fill form fields  │
  │  table   │            │              │        │ Click submit      │
  └──────────┘            └──────────────┘        │ Wait for confirm  │
                                                   └──────────────────┘
                                                            │
                                                     web_form/index.html
                                                   ┌──────────────────┐
                                                   │ Insurance Claim  │
                                                   │ Submission Form  │
                                                   └──────────────────┘
```

---

## Project Structure

```
prestige/
├── src/                        # Application code (5 modules)
│   ├── __init__.py
│   ├── schemas.py              # Pydantic data models
│   ├── ingestion.py            # PDF scanning and text extraction
│   ├── extraction.py           # LLM-based structured data extraction
│   ├── automation.py           # Playwright browser form filling
│   ├── logging_db.py           # SQLite audit log
│   └── pipeline.py             # Main orchestrator + CLI entry point
│
├── tests/                      # Test suite (76 tests, 91% coverage)
│   ├── __init__.py
│   ├── test_schemas.py         # Schema validation tests
│   ├── test_ingestion.py       # PDF reading tests
│   ├── test_extraction.py      # LLM extraction tests (mocked API)
│   ├── test_automation.py      # Playwright tests (real browser)
│   ├── test_logging_db.py      # SQLite tests (temp databases)
│   ├── test_pipeline.py        # Orchestrator tests (all deps mocked)
│   ├── test_integration.py     # End-to-end tests (real PDFs + browser)
│   └── test_generate_pdfs.py   # Verifies dummy PDFs exist and are valid
│
├── inbound_claims/             # Input PDF files
│   ├── claim_standard_01.pdf   # Clean table layout (Maria Santos)
│   ├── claim_standard_02.pdf   # Labeled-line layout (John Rivera)
│   └── claim_messy_03.pdf      # Unstructured letter (Patricia Almeida)
│
├── web_form/
│   └── index.html              # Dummy insurance claim submission form
│
├── scripts/
│   ├── generate_pdfs.py        # Creates the 3 dummy claim PDFs
│   ├── clean_db.sh             # Deletes audit.db for fresh runs
│   └── show_logs.sh            # Displays audit log as formatted table
│
├── screenshots/                # Playwright error captures (auto-generated)
├── demo.sh                     # Full demo script (server + pipeline + logs)
├── pyproject.toml              # Project config and dependencies
├── CLAUDE.md                   # AI assistant instructions
├── PLAN.md                     # Original 10-step implementation plan
├── ARCHITECTURE.md             # This file
├── .env                        # API key (gitignored)
└── .gitignore
```

---

## Source Modules — Detailed Breakdown

### `src/schemas.py` — Data Models

Defines the two Pydantic models that flow through the entire pipeline. Every module communicates through these models — no raw dicts cross module boundaries.

**`ClaimData`** — Structured data extracted from a PDF:

| Field | Type | Validation | Description |
|-------|------|-----------|-------------|
| `policyholder_name` | `str` | required | Name of the insured person |
| `policy_number` | `str` | required | Policy identifier (e.g., `POL-2024-78432`) |
| `claim_amount` | `float` | must be > 0 | Dollar amount being claimed |
| `incident_date` | `str` | regex `YYYY-MM-DD` | Date of the incident in ISO format |
| `raw_source` | `str` | required | Filename of the source PDF |
| `confidence` | `float` | 0.0 to 1.0 | Extraction confidence score |

**`ProcessingResult`** — Outcome of processing one claim:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"success" \| "extraction_failed" \| "automation_failed"` | What happened |
| `timestamp` | `str` | ISO timestamp of when processing occurred |
| `source_file` | `str` | Which PDF this result refers to |
| `screenshot_path` | `str \| None` | Path to error screenshot (only on automation failure) |
| `error_message` | `str \| None` | What went wrong (only on failure) |

---

### `src/ingestion.py` — PDF Scanning and Text Extraction

Responsible for finding PDFs in a folder and converting them to raw text. Uses **PyMuPDF** (a C-based library) for fast, accurate text extraction that preserves layout and reading order.

**Functions:**

- **`scan_inbox(path: Path) -> list[Path]`**
  - Globs `*.pdf` files in the given directory
  - Returns a sorted list (alphabetical order ensures consistent processing)
  - Returns empty list if directory doesn't exist (no crash)

- **`extract_text(pdf_path: Path) -> str | None`**
  - Opens the PDF with `pymupdf.open()`
  - Extracts text from every page and joins with newlines
  - Returns `None` if: file doesn't exist, file is corrupted, file has no text
  - The `try/except` catches any PyMuPDF error — the pipeline never crashes here

**Why PyMuPDF over pypdf:** PyMuPDF is built on MuPDF (C library), making it ~10x faster and significantly better at preserving table layouts, column ordering, and whitespace — critical for insurance claim documents that often have tabular data.

---

### `src/extraction.py` — LLM-Based Data Extraction

Takes raw text from a PDF and uses an LLM to extract structured claim data. This is the "AI brain" of the pipeline.

**Architecture:**

```
Raw text ──> LLMClient.chat() ──> JSON string ──> json.loads() ──> Pydantic validation ──> ClaimData
                  │                                                         │
                  │ (if fails)                                              │ (if fails)
                  v                                                         v
            Return None                                              Retry with stricter prompt
                                                                            │
                                                                     (if fails again)
                                                                            v
                                                                      Return None
```

**Classes:**

- **`LLMClient`** — Thin wrapper around the OpenRouter API using `httpx`:
  - `__init__(api_key?)` — Reads `OPENROUTER_API_KEY` from environment if not provided
  - `chat(system, user_message) -> str` — Sends a chat completion request to the `minimax/minimax-m2.5` model and returns the response text
  - `close()` — Closes the HTTP client

**Functions:**

- **`extract_claim_data(raw_text, source_file, client?) -> ClaimData | None`**
  - Main entry point. Creates an `LLMClient` if none is provided (dependency injection for testing)
  - Delegates to `_extract_with_retry()` and ensures the client is closed in `finally`

- **`_extract_with_retry(client, raw_text, source_file) -> ClaimData | None`**
  - **Attempt 1:** Sends the raw text with `SYSTEM_PROMPT` (asks for strict JSON with the 4 required fields)
  - Parses the response with `_parse_response()`
  - If parsing fails (bad JSON, missing fields, invalid values): **Attempt 2** with `RETRY_SYSTEM_PROMPT` (even stricter, explicitly states the previous response was invalid)
  - If both attempts fail: returns `None`
  - If the API itself errors (network, auth, rate limit): catches `httpx.HTTPError` and returns `None`

- **`_parse_response(response_text, source_file) -> ClaimData | None`**
  - `json.loads()` to parse the raw string
  - Pydantic validation to build a `ClaimData` (this catches: missing keys, negative amounts, bad date formats)
  - Returns `None` on any parsing or validation failure

**Prompts:**
- `SYSTEM_PROMPT` — Instructs the model to return ONLY a JSON object with 4 fields, no markdown, no explanation
- `RETRY_SYSTEM_PROMPT` — Even more explicit, tells the model its previous response was invalid

---

### `src/automation.py` — Browser Form Filling

Uses **Playwright** (Chromium) to open a web form, fill in the claim data, and click submit. This simulates an employee manually entering data into an insurance system.

**Functions:**

- **`fill_web_form(claim: ClaimData, form_url: str, headless: bool) -> ProcessingResult`**
  - Launches Chromium (`headless=True` for CI, `headless=False` for demo with `slow_mo=400ms`)
  - Navigates to the form URL
  - Fills text fields (`#policyholder_name`, `#policy_number`) with `page.fill()`
  - Fills number/date fields (`#claim_amount`, `#incident_date`) with `_set_input_value()` (JavaScript approach for proper visual rendering)
  - Clicks `#submit-btn`
  - Waits up to 5 seconds for `#confirmation` div to become visible
  - On success: returns `ProcessingResult(status="success")`
  - On any error: captures screenshot, returns `ProcessingResult(status="automation_failed")`
  - Browser is **always** closed in `finally` block

- **`_set_input_value(page, selector, value)`**
  - Uses JavaScript to set the value via the native HTMLInputElement setter
  - Dispatches `input` and `change` events so the browser visually updates
  - This is necessary because `page.fill()` on `type="number"` and `type="date"` inputs does not always trigger visual rendering

- **`_capture_screenshot(page, policy_number, timestamp) -> Path | None`**
  - Saves a PNG screenshot to `screenshots/{timestamp}_{policy_number}.png`
  - Returns `None` if the page object doesn't exist or the screenshot fails
  - These screenshots are invaluable for debugging why a form submission failed

---

### `src/logging_db.py` — SQLite Audit Log

Every processing result (success or failure) is persisted to an SQLite database. This provides a complete audit trail.

**Database Schema:**

```sql
CREATE TABLE IF NOT EXISTS processing_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,       -- ISO 8601 timestamp
    source_file         TEXT NOT NULL,       -- PDF filename
    status              TEXT NOT NULL,       -- success | extraction_failed | automation_failed
    policyholder_name   TEXT,                -- NULL if extraction failed
    policy_number       TEXT,                -- NULL if extraction failed
    claim_amount        REAL,                -- NULL if extraction failed
    error_message       TEXT,                -- NULL if success
    screenshot_path     TEXT                 -- NULL unless automation failed
)
```

**Functions:**

- **`log_result(result: ProcessingResult, claim: ClaimData | None, db_path?)`**
  - Inserts one row into `processing_log`
  - If `claim` is `None` (extraction failed), the claim-related columns are NULL
  - The `db_path` parameter defaults to `audit.db` but can be overridden (used in tests with temp directories)

- **`get_logs(db_path?) -> list[dict]`**
  - Returns all rows from `processing_log` ordered by ID
  - Each row is a plain Python dict with all 9 columns
  - Returns empty list if the database doesn't exist yet

- **`_get_connection(db_path) -> sqlite3.Connection`**
  - Opens a connection and creates the table if it doesn't exist (`CREATE TABLE IF NOT EXISTS`)
  - This means the database is self-initializing — no migration step needed

---

### `src/pipeline.py` — Main Orchestrator

The only module that imports all other modules. Chains them together and provides the CLI interface.

**Functions:**

- **`run_pipeline(inbox_path, form_url, headless) -> list[ProcessingResult]`**
  - The core function. For each PDF in the inbox:
    1. `extract_text()` — If fails, log `extraction_failed` and **continue** to next PDF
    2. `extract_claim_data()` — If fails, log `extraction_failed` and **continue**
    3. `fill_web_form()` — Returns `ProcessingResult` (success or automation_failed)
    4. `log_result()` — Persist to SQLite
  - Prints colored status per PDF (`OK` in green, `FAIL` in red)
  - Prints summary at the end
  - Returns the list of all results

- **`main()`** — CLI entry point with argparse:
  - `--inbox` — Path to PDF folder (default: `inbound_claims`)
  - `--form-url` — URL of the web form (default: `http://localhost:8000/web_form/index.html`)
  - `--headful` — Show the browser window (default: headless)
  - Run with: `python -m src.pipeline --inbox ./inbound_claims --form-url http://localhost:8000/web_form/index.html`

**Colored Output:** ANSI escape codes are used for terminal colors, but automatically disabled when stdout is not a TTY (piped to a file or in CI).

---

## Supporting Files

### `web_form/index.html`

A minimal HTML form that simulates a real insurance claim submission portal. Contains:
- 4 input fields: Policyholder Name (`text`), Policy Number (`text`), Claim Amount (`number`), Incident Date (`date`)
- A Submit button
- A hidden `#confirmation` div that appears on submit (JavaScript `preventDefault` + show div)
- This form is served by a local HTTP server during the demo

### `scripts/generate_pdfs.py`

Generates the 3 test claim PDFs using `fpdf2`:
- **`claim_standard_01.pdf`** — Clean table layout (Maria Santos, POL-2024-78432, $12,500, 2025-11-03)
- **`claim_standard_02.pdf`** — Labeled-line format (John Rivera, POL-2025-00193, $8,750.50, 2026-01-15)
- **`claim_messy_03.pdf`** — Unstructured letter with data buried in paragraphs (Patricia Almeida, POL-2023-55671, $23,100, 2025-08-22)

These three formats test the LLM's ability to extract structured data from varying document layouts.

### `scripts/clean_db.sh`

Deletes `audit.db` and reports how many records were removed. Use before a fresh demo run.

### `scripts/show_logs.sh`

Queries `audit.db` with `sqlite3` and displays a formatted table with colored OK/FAIL status, policyholder names, policy numbers, and claim amounts.

### `demo.sh`

Full demo script that:
1. Loads `.env` (exports `OPENROUTER_API_KEY`)
2. Starts a local HTTP server on port 8000
3. Runs the pipeline (headful by default, `--headless` flag available)
4. Displays the audit log
5. Cleans up the HTTP server on exit via `trap`

---

## Test Architecture

The test suite has **76 tests** organized by module, with clear separation between unit tests (mocked dependencies) and integration tests (real components).

### Test Strategy Per Module

| Test File | What It Tests | External Deps | Strategy |
|-----------|--------------|---------------|----------|
| `test_schemas.py` (13 tests) | Pydantic validation — valid data, missing fields, invalid amounts, bad dates, boundary values | None | Direct model instantiation |
| `test_ingestion.py` (10 tests) | PDF scanning and text extraction — valid PDFs, empty/corrupted files, missing folders | Filesystem | Uses real dummy PDFs + `tmp_path` for edge cases |
| `test_extraction.py` (12 tests) | LLM extraction — valid JSON, malformed JSON, missing fields, retry logic, API errors | OpenRouter API | `LLMClient` mocked with `unittest.mock` |
| `test_automation.py` (7 tests) | Form filling — successful submit, field values, broken form, invalid URL, screenshot capture | Playwright + Browser | Real Chromium (headless) for integration, mocks for screenshot unit tests |
| `test_logging_db.py` (8 tests) | SQLite operations — insert success/failure, query all, column presence, ordering | SQLite | Real SQLite with `tmp_path` temp databases |
| `test_pipeline.py` (10 tests) | Orchestrator flow — success, each failure type, mixed results, headless forwarding, summary output | All modules | All 4 dependencies patched with `unittest.mock` |
| `test_integration.py` (10 tests) | End-to-end flow — real PDFs + real Playwright + real SQLite, only LLM mocked | PDF + Browser + SQLite | Full integration, LLM mocked to avoid API key requirement |
| `test_generate_pdfs.py` (6 tests) | PDF generation script — files exist, are readable, contain expected text | Filesystem | Reads real generated PDFs |

### Key Testing Patterns

- **Dependency Injection:** `extraction.py` accepts an optional `client` parameter, `logging_db.py` accepts `db_path`. This avoids patching internals.
- **`tmp_path` Fixture:** All tests that write files (SQLite, PDFs, screenshots) use pytest's `tmp_path` for isolation.
- **Integration tests use a `known_inbox` fixture:** Copies only the 3 known test PDFs to a temp directory, so extra PDFs in `inbound_claims/` don't break assertions.

---

## Error Handling Philosophy

The pipeline is designed to **never crash**. Every failure mode produces a `ProcessingResult` and gets logged:

| Failure | Where Caught | Status Logged | Pipeline Continues? |
|---------|-------------|---------------|-------------------|
| PDF file corrupted/unreadable | `ingestion.py` | `extraction_failed` | Yes |
| PDF has no extractable text | `ingestion.py` | `extraction_failed` | Yes |
| LLM API unreachable/error | `extraction.py` | `extraction_failed` | Yes |
| LLM returns invalid JSON (2 attempts) | `extraction.py` | `extraction_failed` | Yes |
| LLM returns JSON with wrong fields | `extraction.py` | `extraction_failed` | Yes |
| Form field selector not found | `automation.py` | `automation_failed` + screenshot | Yes |
| Form submit timeout | `automation.py` | `automation_failed` + screenshot | Yes |
| Browser crash | `automation.py` | `automation_failed` | Yes |
| Empty inbox folder | `pipeline.py` | Nothing (returns []) | N/A |
| Non-existent inbox path | `ingestion.py` | Nothing (returns []) | N/A |

---

## How to Run

```bash
# Run tests
.venv/bin/pytest tests/ -v

# Run tests with coverage
.venv/bin/pytest tests/ -v --cov=src --cov-report=term-missing

# Run the full demo (headful — visible browser)
./scripts/clean_db.sh
./demo.sh

# Run headless (CI mode)
./demo.sh --headless

# Run pipeline manually
.venv/bin/python -m src.pipeline --inbox ./inbound_claims --form-url http://localhost:8000/web_form/index.html

# View audit log
./scripts/show_logs.sh

# Reset database
./scripts/clean_db.sh
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pymupdf` | >= 1.24 | PDF text extraction (C-based, fast and accurate) |
| `httpx` | (transitive) | HTTP client for OpenRouter API calls |
| `pydantic` | >= 2.0 | Data validation and schema enforcement |
| `playwright` | >= 1.48 | Browser automation (Chromium) |
| `pytest` | >= 8.0 | Test framework |
| `pytest-cov` | >= 5.0 | Coverage reporting |
| `fpdf2` | (scripts only) | Generating dummy test PDFs |
