import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('EDUMIND_DATA', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
(DATA / 'uploads').mkdir(exist_ok=True)
DB = DATA / 'edumind.db'

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','teacher','student')), created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, csrf TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, description TEXT DEFAULT '', tags TEXT DEFAULT '', created REAL);
CREATE TABLE IF NOT EXISTS enrollments(course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE, student_id INTEGER REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(course_id,student_id));
CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY, course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE, title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, unit_id INTEGER REFERENCES units(id) ON DELETE CASCADE, title TEXT NOT NULL, description TEXT DEFAULT '', objectives TEXT DEFAULT '', published INTEGER DEFAULT 0, version INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE, name TEXT, stored TEXT, text TEXT, created REAL);
CREATE TABLE IF NOT EXISTS summaries(id INTEGER PRIMARY KEY, lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE, text TEXT, style TEXT, created REAL);
CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE, title TEXT, duration INTEGER, published INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE, lesson_id INTEGER REFERENCES lessons(id) ON DELETE SET NULL, data TEXT NOT NULL, created REAL);
CREATE TABLE IF NOT EXISTS exam_questions(exam_id INTEGER REFERENCES exams(id) ON DELETE CASCADE, question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE, position INTEGER, PRIMARY KEY(exam_id,question_id));
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, exam_id INTEGER REFERENCES exams(id) ON DELETE CASCADE, student_id INTEGER REFERENCES users(id) ON DELETE CASCADE, started REAL, deadline REAL, submitted REAL, answers TEXT DEFAULT '{}', grading TEXT, UNIQUE(exam_id,student_id));
CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY, course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE, text TEXT, created REAL);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, text TEXT, created REAL);
CREATE INDEX IF NOT EXISTS ix_documents_lesson ON documents(lesson_id);
CREATE INDEX IF NOT EXISTS ix_courses_owner ON courses(owner_id);
'''

@contextmanager
def db():
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with db() as con:
        con.executescript(SCHEMA)

def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]

def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310000)
    return salt.hex() + ':' + digest.hex()

def password_check(password, stored):
    try:
        salt, digest = stored.split(':')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000)
        return hmac.compare_digest(actual.hex(), digest)
    except (ValueError, TypeError):
        return False

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

KINDS = ('mcq','true_false','fill_blank','matching','short_answer','essay','explain_why','compare','complete','scenario','critical_thinking','application')
OBJECTIVE = ('mcq', 'true_false', 'fill_blank', 'complete')

def validate_question(q):
    if not isinstance(q, dict):
        raise ValueError('Question must be an object')
    kind = q.get('kind', 'mcq')
    if kind not in KINDS:
        raise ValueError('Unsupported question type')
    text = str(q.get('text', '')).strip()
    if not text or len(text) > 10000:
        raise ValueError('Question text is required (max 10,000 characters)')
    marks = float(q.get('marks', 1))
    if not 0 < marks <= 100:
        raise ValueError('Marks must be between 0 and 100')
    options = q.get('options', [])
    if not isinstance(options, list) or len(options) > 10:
        raise ValueError('Options must be an array of at most 10 strings')
    options = [str(v).strip()[:2000] for v in options]
    answer = str(q.get('answer', '')).strip()
    if kind == 'true_false':
        options = ['True', 'False']
    if kind in ('mcq', 'true_false') and (len(options) < 2 or len(set(options)) != len(options) or answer not in options):
        raise ValueError('Choice questions need unique options and an answer matching an option')
    if not answer:
        raise ValueError('An answer or grading rubric is required')
    difficulty = q.get('difficulty', 'Medium')
    if difficulty not in ('Easy','Medium','Hard'):
        difficulty = 'Medium'
    return dict(kind=kind,text=text,options=options,answer=answer,marks=marks,difficulty=difficulty,explanation=str(q.get('explanation',''))[:10000])

def normalized(value):
    return ' '.join(str(value).strip().casefold().split())

def grade(questions, answers):
    details = []
    for q in questions:
        value = str(answers.get(str(q['id']), ''))
        objective = q['kind'] in OBJECTIVE
        points = q['marks'] if objective and normalized(value) == normalized(q['answer']) else (0 if objective else None)
        details.append(dict(question_id=q['id'], score=points, max=q['marks'], response=value, answer=q['answer'], explanation=q.get('explanation','')))
    return dict(score=sum(d['score'] or 0 for d in details), total=sum(d['max'] for d in details), pending=sum(d['score'] is None for d in details), details=details)

def chunks(text, size=1800, overlap=200):
    return [text[i:i+size] for i in range(0,len(text),size-overlap) if text[i:i+size].strip()]

def retrieve(documents, query, limit=8):
    import re
    terms = set(re.findall(r'\w+', query.casefold()))
    entries = [(f"[Document {d['id']}: {d['name']}, passage {i+1}]\n{c}", len(terms & set(re.findall(r'\w+',c.casefold())))) for d in documents for i,c in enumerate(chunks(d['text']))]
    entries.sort(key=lambda x: x[1], reverse=True)
    return '\n\n'.join(c for c,_ in entries[:limit])

init_db()
