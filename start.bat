@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: follow the Windows setup steps in README.md.
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env"
echo Open http://127.0.0.1:8000 in your browser, or the PORT configured in .env.
echo Keep this window open. Press Ctrl+C to stop EduMind.
".venv\Scripts\python.exe" main.py
pause
