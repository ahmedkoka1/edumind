# EduMind

A working local educational workspace built with Python 3.10+, FastAPI, SQLite and plain HTML/CSS/JavaScript. No Node.js or frontend build is needed.

**This is a functional local MVP, not the entire production SaaS described in the original brief.** There are no fake AI responses, seeded accounts or dashboard numbers. The first run starts empty. AI functions need your own configured provider and may cost money on that provider.

## ابدأ هنا: Windows 10 / 11

1. فك ضغط `EduMind.zip` في فولدر مثل `C:\EduMind`، وليس داخل ملف ZIP نفسه.
2. افتح الفولدر، اكتب `cmd` في شريط العنوان واضغط Enter.
3. نفّذ الأوامر التالية بالترتيب. الأوامر مناسبة لـ Command Prompt، ولا تحتاج تفعيل PowerShell:

```bat
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
notepad .env
```

ضع مفتاحك بعد `GEMINI_API_KEY=` واحفظ الملف. لا ترسل المفتاح في المحادثات. يمكنك تركه فارغًا لتجربة باقي المنصة بدون AI.

```bat
.venv\Scripts\python.exe main.py
```

افتح **http://127.0.0.1:8000** في المتصفح. لا تقفل نافذة الأوامر أثناء الاستخدام. لإيقاف البرنامج اضغط `Ctrl+C`.

إذا لم يعمل `py -3.10` لكن `python --version` يظهر Python 3.10 أو أحدث، استخدم `python -m venv .venv` بدل أول أمر.

في التشغيل التالي، استخدم `start.bat` أو:

```bat
.venv\Scripts\python.exe main.py
```

### أول تجربة من أول الكورس لنتيجة الطالب

1. في أول فتح، أنشئ حساب المدير. لا توجد كلمة مرور افتراضية.
2. من **Students & Classes** أنشئ حساب Teacher وحساب Student، أو اسمح للطالب بتسجيل حساب بنفسه من شاشة الدخول. التسجيل العام يعطي Student فقط.
3. سجل الدخول كمدرس، أنشئ كورس، أضف Unit ثم Lesson، وحدد نشر الدرس.
4. ارفع ملف TXT أو PDF نصي أو DOCX أو PPTX. راجع النص المستخرج بزر Read.
5. جرّب Summary أو المساعد التعليمي بعد ضبط المفتاح. المحتوى المحدد يُرسل لمزود AI.
6. أضف الطالب للكورس باستخدام نفس بريده المسجل.
7. أنشئ امتحانًا، أضف أسئلة يدويًا أو ولّد أسئلة من دروس محددة. راجع الإجابات والدرجات ثم انشر الامتحان. النشر يقفل التعديل لحماية النتائج.
8. في متصفح آخر أو نافذة خاصة، ادخل بحساب الطالب، افتح الكورس ثم الامتحان واضغط Start. اختر الإجابة ثم Submit.
9. بحساب المدرس افتح Results & grading لتصحيح الأسئلة المقالية. درجات الاختيار/صح وخطأ تتصحح آليًا.
10. زر العربية يغيّر اتجاه الواجهة إلى RTL. لغة المحتوى الذي يكتبه المستخدم لا تُترجم تلقائيًا.

**مهم:** إنشاء حساب المدير متاح مرة واحدة فقط. شغّل البرنامج محليًا أثناء الإعداد. الأداة ليست بوتًا لمنصة QUREO ولا تسجل دخولًا لأي منصة أخرى.

## What works

| Area | Implemented behavior |
| --- | --- |
| Authentication | First-admin setup, student registration, admin-created users in all three roles, salted PBKDF2 password hashes, opaque hashed session tokens, HttpOnly/SameSite cookies, 12-hour sessions, logout, basic in-process login throttling. |
| Authorization | API checks on every course, lesson, upload, exam, bank and attempt. Teachers own courses, students see enrolled courses and published material, admin sees all. Teacher student lists only show students in their courses. |
| Courses | Create/read/update/delete courses; units; create/edit/publish lessons; learning objectives; lesson version counter; tags and course search. Course deletion cascades database content and removes uploaded files. |
| Files | Actual uploads and text extraction for PDF, DOCX, PPTX, UTF-8 TXT. Multiple documents per lesson, extracted-text preview, authorized download/delete. 10 MB/file, 300 PDF pages, 1 million extracted characters, 60 MB expanded Office archive limit. |
| AI | Official `google-genai` SDK by default; optional OpenAI-compatible provider. Detailed/revision/key-concept summaries, citation-prompted course document Q&A, validated exam question generation. No key means a clear configuration error, not simulated output. |
| Retrieval | Local lexical retrieval over overlapping text passages for Q&A, with document/passage labels. Summaries and exam generation use selected lesson text, up to 150,000 characters; oversized requests are rejected, not silently truncated. |
| Exams | Draft creation; all 12 named question categories stored as choice or written questions; text/options/answer/marks/difficulty editing; up/down reorder; remove; reuse from course bank; publishing lock; total marks are the sum of question marks. |
| Question bank | Persistent questions with type/difficulty/text filtering, model answers, explanations, usage counts. Copy-on-edit avoids changing another exam that reused the same bank item. Removed exam questions remain in the bank. |
| Student exams | One attempt per student/exam, server-set start/deadline, countdown, question navigation, debounced answer autosave, resume, submit confirmation, server rejection of late answers, objective grading and feedback. No correct answers are sent before submission. |
| Grading | MCQ/true-false and normalized exact matching for fill_blank/complete. All other categories, including matching, are written responses graded by a teacher. Pending scores are marked provisional. |
| Dashboard | Real scoped counts, recent personal activity, exam list, charts from submitted attempts. No fabricated history or statistics. |
| Export | Word exam and separate answer-key exports; Arabic paragraph RTL option. Browser Print / Save as PDF uses the exam's print layout and excludes answers. No server-side PDF renderer is required. |
| Communication | Course announcements visible to enrolled students. |
| Interface | Responsive desktop/tablet/mobile layout; Arabic RTL and English LTR core screens and labels; separate role-aware navigation. Technical question-type IDs and some provider/server error text remain English. |
| Operations | Local data persistence, manual backup/restore scripts, environment-only provider keys, interactive API documentation at `/api/docs`, repeatable tests. |

## What is intentionally not implemented

These are extension points, not hidden buttons that pretend to work:

- Subscription billing, quotas, SaaS tenant isolation, online payment, admin subscription management.
- Class/group entities beyond per-course enrollment; assignment workflow, due dates, scheduled exams, push/email reminders or a full notifications inbox.
- Image upload/OCR, scanned PDF OCR, faithful embedded PDF/Office previews, media transcoding.
- Background task queue, long-running document jobs, vector embeddings/vector database, conversation memory for chat, automated backups or monitoring dashboards.
- Course duplication, unit/lesson deletion/reordering, full content history/rollback. Lesson versions are counters, not saved historic snapshots.
- Drag-and-drop editing (up/down buttons are used), multi-version shuffling, per-lesson numeric blueprints, individual-question AI regeneration, psychometric quality analysis, semantic near-duplicate detection. AI generation distributes across selected lessons but does not enforce a per-lesson count.
- Automatic essay/matching grading, handwritten work, personalized remediation, anti-cheat/proctoring, retakes, results-release scheduling, exam accommodations.
- Password reset/email verification/MFA, password-change screen, user deletion/role-change UI, distributed login throttling, malware scanning, storage encryption, database migrations.
- Fully translated server messages, Arabic content translation, or guarantees that an LLM's citations/facts are correct.

## AI configuration

Copy `.env.example` to `.env` once. Restart after changes.

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The model is configurable, not guaranteed available on every account. If your account uses another model, change `GEMINI_MODEL`. The live provider was **not called during delivery testing**, because no API key was supplied. Validation and service-free tests cover both successful and malformed generated output, not real model quality or account quotas.

Alternative protocol:

```dotenv
AI_PROVIDER=openai_compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your_key_here
LLM_MODEL=your_model
```

`LLM_BASE_URL` is the base URL including `/v1` if that provider requires it, but without `/chat/completions`. Configure only a provider you trust. No model is installed locally. To add another protocol, implement it behind `edumind/ai.py:complete()`; the rest of the application consumes text or validated question JSON.

Summaries, selected question-generation sources and retrieved chat passages leave this computer for the selected provider. Do not upload student personal data or copyrighted/private material without the appropriate permission. The source text is treated as untrusted data in the prompt, but no LLM can guarantee resistance to hostile documents. AI output is displayed as escaped text, never executable HTML.

## Tests

```bat
.venv\Scripts\python.exe -m pytest -q
```

The suite uses disposable temporary databases. It never needs a provider key, and does not erase your real data. See `TEST_REPORT.md` for the delivered run.

Optional rendered browser smoke check, using a temporary populated database:

```bat
.venv\Scripts\python.exe -m pip install playwright
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe tests\visual_smoke.py
```

Visual smoke screenshots are saved to your system temporary directory, not your project data. Test credentials are disposable fixtures only; no fixture accounts are installed into your normal database.

## Backups and restore

Stop the server before backup:

```bat
.venv\Scripts\python.exe backup.py
```

This writes a timestamped ZIP under `backups`, containing the database and uploads, **not `.env`**. Keep it private, because it contains user data and password hashes. Copy `.env` separately to a secure location if needed. API keys are not recoverable from a data backup.

To restore while the server is stopped:

```bat
.venv\Scripts\python.exe backup.py --restore backups\YOUR-BACKUP.zip
```

Restore refuses to overwrite an existing data directory. Move the existing `data` folder somewhere safe first. Use the same `EDUMIND_DATA` path configured in `.env`. The tool validates archive paths before extracting.

## Architecture and important limits

```text
main.py                  local 127.0.0.1 server entry point
edumind/app.py           FastAPI routes and authorization
edumind/core.py          SQLite schema, password/grade/validation/retrieval logic
edumind/ai.py            configurable provider boundary
edumind/static/          browser UI; no build step or CDN dependencies
backup.py                offline backup/restore utility
tests/test_app.py        service-free unit/integration tests
tests/visual_smoke.py    optional Chromium end-to-end smoke
```

- SQLite foreign keys and parameterized statements are used throughout. Upload filenames are randomized on disk and never used as executable paths. Downloads require authorization.
- Browser mutations require a custom request header; CORS is not enabled. Scripts are served from this app only. Session tokens are stored hashed. This is a local MVP, not a security audit or production certification.
- Parsing and AI calls are synchronous worker-thread requests with bounded input sizes, not durable background jobs. A production app should use isolated parsing workers and a job queue.
- There is no forced auto-submit task running in the background. The browser submits at zero; the server finalizes expired attempts when the attempt is resumed/saved or a teacher requests results. The server deadline still rejects late answers even with the browser closed. An answer typed but not yet saved when time runs out cannot be recovered.
- Autosave requires a connection. Do not close the page until it says answers are saved. Teacher-facing answers become available to a student immediately after their final submission; this is not appropriate for high-stakes shared exams without a results-release policy.
- The server binds to `127.0.0.1` intentionally. Students on other computers cannot reach this local version. Public/multi-machine hosting requires explicit deployment work, HTTPS, secure cookies, enrollment/invitation controls, migrations, backups, isolated uploads, monitoring and review of all auth/data policies. Do not expose the initial setup screen to the internet.
- `COOKIE_SECURE=true` is for HTTPS deployment. Leave false on the default local HTTP address, otherwise sign-in cookies will not work.
- Dependency versions were exercised on Python 3.10 in Linux. Windows commands are provided for the same Python version; Windows itself was not available for a native test.
- Keep `.env`, `data`, `backups` and `.venv` private and out of source control. Do not copy a populated project ZIP to other people.

## Troubleshooting

- **Port already in use:** change `PORT=8001` in `.env`, restart, open `http://127.0.0.1:8001`.
- **AI unavailable:** check the selected provider, key, model availability, network and provider quota. Manual questions and courses work without AI.
- **Unreadable PDF:** only text-based, unencrypted PDFs are supported. OCR is not included. Try exporting a DOCX/TXT copy.
- **Student sees nothing:** enroll the exact registered student email and publish both the lesson and exam.
- **Cannot edit exam:** published exams are locked, even before the first attempt. Create another draft and reuse bank questions.
- **No default login:** first opening creates the admin. Preserve your credentials. There is no password recovery service in this local MVP.
