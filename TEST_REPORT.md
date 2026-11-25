# Delivery verification

Run date: 23 November 2026.

## Automated checks

- Python **3.10.12**, Linux.
- `python -m pytest -q`: **23 passed in 3.54s**.
- One upstream Starlette deprecation warning concerning its current httpx test-client adapter. No test failures. This is a test dependency warning, not an application error.
- `node --check edumind/static/app.js`: passed.
- Python source compilation: passed.
- Official Google GenAI SDK imported successfully; `GenerateContentConfig` with JSON response mode and `HttpOptions(timeout=90000)` constructed successfully.

### Tested behavior

- Password hashing, salting and verification.
- Question validation and objective versus subjective grading.
- Passage retrieval and source labeling.
- First-admin setup, duplicate-setup rejection, request protection, sign-in and logout.
- Student registration cannot elevate itself to teacher/admin.
- Teacher isolation, course update/delete and cascades.
- Real TXT uploads, private downloads, malformed-file rejection and deletion.
- Real DOCX/PPTX parsing and blank PDF parsing.
- Draft lesson and exam visibility.
- Complete teacher-to-student exam flow, answer-key hiding before submission, immutable published exams, autosave, resume, objective grading, manual grading, results and Word export.
- Server rejection of answers after the deadline.
- Missing-key AI failure, mocked summary persistence, valid generated questions and rejection of invalid lesson references with no partial save.
- Copy-on-edit question reuse and reorder validation.
- Login throttling.
- Backup/restore roundtrip, overwrite refusal and archive path-traversal rejection.

## Rendered browser verification

`python tests/visual_smoke.py`: passed with headless Chromium and disposable test data.

- Sign-in screen; teacher/admin dashboard; course/lesson view; exam editor.
- English LTR and Arabic RTL dashboard.
- Mobile viewport **390 × 844**, with no horizontal page overflow.
- Student timed exam, selecting an answer, autosave, confirmed submission and the expected **5/5** result.
- No JavaScript page errors in the tested flow.
- Browser-generated printable exam PDF inspected: readable layout, choices present, answer/explanation and controls excluded.
- Exported Word answer key converted to PDF for inspection: readable title, question, choices and answer key. Arabic direction flag checked through the RTL export route; a full Arabic-content Word export was not separately proofread.

Actual screenshots were visually inspected. A compact selection is included under `previews/`, clearly using fictional test names and course data. These examples are not installed in the application's database.

## Not verified

- Native Windows execution. Exact Windows commands are provided; runtime and tests ran on Linux using Python 3.10.
- A real Gemini or other provider request, account quota, model availability, generated factual accuracy or citation quality. No API key was supplied. Provider boundaries and output validation were tested without services.
- Public internet deployment, penetration testing, multi-server concurrency, high-load behavior, accessibility certification or production disaster recovery.

This is a tested local MVP, not a claim of full implementation of all phases in the original SaaS brief. README lists implemented behavior and remaining features explicitly.
