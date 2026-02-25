# Intake-to-Web AI Pipeline

## Project Overview

Python micro-service that reads insurance claim PDFs, extracts structured data via LLM (MiniMax M2.5 via OpenRouter), fills web forms via Playwright, and logs everything to SQLite. Built as a demo for a job interview in the commercial insurance automation space.

## Tech Stack

- **Python 3.12+**
- **pymupdf** — PDF text extraction
- **httpx** — LLM calls via OpenRouter API (MiniMax M2.5)
- **pydantic** — data validation and schemas
- **playwright** — browser automation (chromium)
- **sqlite3** — audit logging
- **pytest** — testing with `unittest.mock` for external services

## Project Structure

```
src/           → all application code
tests/         → all test files (mirror src/ naming: test_<module>.py)
inbound_claims/ → input PDF files
web_form/      → dummy HTML form for demo
screenshots/   → Playwright error captures
scripts/       → helper scripts (PDF generation, etc.)
```

## Code Conventions

- Type hints on all function signatures
- Pydantic models for all data structures crossing module boundaries
- Functions return `None` on failure instead of raising — the pipeline never crashes
- All external calls (LLM API, Playwright) wrapped in try/except with logging
- No bare `except:` — always catch specific exceptions
- Use `pathlib.Path` instead of string paths
- Use `logging` module, not `print()`, for operational messages (`print` only for user-facing CLI output)

## Testing

- Unit tests mock all external dependencies (OpenRouter API, Playwright browser, filesystem)
- Integration tests use real dummy PDFs and local HTML form
- Run tests: `pytest tests/ -v`
- Target coverage: >80%

## Environment

- API key via `OPENROUTER_API_KEY` environment variable (never hardcoded)
- `.env` file must be in `.gitignore`

## Key Design Decisions

- Each module (`ingestion`, `extraction`, `automation`, `logging_db`) is independent and testable in isolation
- Pipeline orchestrator (`pipeline.py`) is the only module that imports all others
- Failures in one PDF don't affect processing of others — the pipeline always continues
- Every action (success or failure) is logged to SQLite with timestamp and source file
- Playwright screenshots are captured on automation failures for debugging
