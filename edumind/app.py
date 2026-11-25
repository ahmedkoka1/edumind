import io
import json
import logging
import os
import secrets
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, core

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
app = FastAPI(title='EduMind', version='1.0.0', docs_url='/api/docs', redoc_url=None)
STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')
LOGIN_TRIES = {}

@app.middleware('http')
async def security(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        # All browser mutations require a custom header. Cross-origin sites cannot send it without a preflight, and CORS is not enabled.
        if request.headers.get('X-EduMind') != '1':
            return Response('Missing request protection header', 403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response

@app.get('/')
def index():
    return FileResponse(STATIC / 'index.html')

def user(request: Request):
    token = request.cookies.get('edumind_session','')
    with core.db() as con:
        u = con.execute('SELECT u.id,u.name,u.email,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(core.token_hash(token),time.time())).fetchone()
    if not u:
        raise HTTPException(401,'Please sign in')
    return dict(u)

def staff(u):
    if u['role'] not in ('teacher','admin'):
        raise HTTPException(403,'Teacher access required')

def course_access(con, cid, u, write=False):
    c = con.execute('SELECT * FROM courses WHERE id=?',(cid,)).fetchone()
    if not c:
        raise HTTPException(404,'Course not found')
    if u['role']=='admin' or (u['role']=='teacher' and c['owner_id']==u['id']):
        return dict(c)
    if not write and u['role']=='student' and con.execute('SELECT 1 FROM enrollments WHERE course_id=? AND student_id=?',(cid,u['id'])).fetchone():
        return dict(c)
    raise HTTPException(403,'You do not have access to this course')

def lesson_access(con, lid, u, write=False):
    row = con.execute('SELECT l.*,un.course_id FROM lessons l JOIN units un ON un.id=l.unit_id WHERE l.id=?',(lid,)).fetchone()
    if not row:
        raise HTTPException(404,'Lesson not found')
    course_access(con,row['course_id'],u,write)
    if u['role']=='student' and not row['published']:
        raise HTTPException(404,'Lesson not published')
    return dict(row)

def exam_access(con,eid,u,write=False):
    row = con.execute('SELECT * FROM exams WHERE id=?',(eid,)).fetchone()
    if not row:
        raise HTTPException(404,'Exam not found')
    course_access(con,row['course_id'],u,write)
    if u['role']=='student' and not row['published']:
        raise HTTPException(404,'Exam not published')
    return dict(row)

def questions_for(con,eid):
    return [dict(id=r['id'],lesson_id=r['lesson_id'],**json.loads(r['data'])) for r in con.execute('SELECT q.* FROM questions q JOIN exam_questions e ON e.question_id=q.id WHERE e.exam_id=? ORDER BY e.position',(eid,))]

def log(con,u,text):
    con.execute('INSERT INTO activity(user_id,text,created) VALUES(?,?,?)',(u['id'],text,time.time()))

class Credentials(BaseModel):
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=10,max_length=128)
    name: str = Field(default='Learner',min_length=1,max_length=100)

class CourseBody(BaseModel):
    title: str = Field(min_length=1,max_length=200)
    description: str = Field(default='',max_length=10000)
    tags: str = Field(default='',max_length=500)

class UnitBody(BaseModel):
    title: str = Field(min_length=1,max_length=200)

class LessonBody(CourseBody):
    objectives: str = Field(default='',max_length=10000)
    published: bool = False

@app.get('/api/status')
def status():
    with core.db() as con:
        return {'needs_setup':con.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0}

def create_user(body,role,first=False):
    email=body.email.strip().lower()
    if '@' not in email or '.' not in email.split('@')[-1]:
        raise HTTPException(422,'Enter a valid email address')
    with core.db() as con:
        con.execute('BEGIN IMMEDIATE')
        if first and con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise HTTPException(409,'Setup is already complete')
        if not first and not con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise HTTPException(409,'Complete administrator setup first')
        try:
            cur=con.execute('INSERT INTO users(name,email,password,role,created) VALUES(?,?,?,?,?)',(body.name,email,core.password_hash(body.password),role,time.time()))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Email is already registered')
        return {'id':cur.lastrowid}

@app.post('/api/setup')
def setup(body:Credentials):
    return create_user(body,'admin',True)

@app.post('/api/register')
def register(body:Credentials):
    return create_user(body,'student')

@app.post('/api/login')
def login(body:Credentials,request:Request,response:Response):
    addr=request.client.host if request.client else 'local'
    now=time.time()
    attempts=[t for t in LOGIN_TRIES.get(addr,[]) if now-t<300]
    LOGIN_TRIES[addr]=attempts
    if len(attempts)>=10:
        raise HTTPException(429,'Too many sign-in attempts. Wait five minutes.')
    attempts.append(now)
    with core.db() as con:
        row=con.execute('SELECT * FROM users WHERE email=?',(body.email.strip().lower(),)).fetchone()
        if not row or not core.password_check(body.password,row['password']):
            raise HTTPException(401,'Incorrect email or password')
        token=secrets.token_urlsafe(32)
        con.execute('DELETE FROM sessions WHERE expires<?',(now,))
        con.execute('INSERT INTO sessions VALUES(?,?,?,?)',(core.token_hash(token),row['id'],secrets.token_hex(16),now+43200))
        response.set_cookie('edumind_session',token,httponly=True,samesite='strict',secure=os.getenv('COOKIE_SECURE','false').lower()=='true',max_age=43200)
    return {'ok':True}

@app.post('/api/logout')
def logout(request:Request,response:Response):
    with core.db() as con:
        con.execute('DELETE FROM sessions WHERE token=?',(core.token_hash(request.cookies.get('edumind_session','')),))
    response.delete_cookie('edumind_session')
    return {'ok':True}

@app.get('/api/me')
def me(u=Depends(user)):
    return u

class NewUser(Credentials):
    role: Literal['admin','teacher','student']='student'

@app.get('/api/users')
def users(u=Depends(user)):
    staff(u)
    with core.db() as con:
        if u['role']=='admin':
            return core.rows(con,'SELECT id,name,email,role FROM users ORDER BY name')
        return core.rows(con,"SELECT DISTINCT u.id,u.name,u.email,u.role FROM users u JOIN enrollments e ON e.student_id=u.id JOIN courses c ON c.id=e.course_id WHERE c.owner_id=?",(u['id'],))

@app.post('/api/users')
def add_user(body:NewUser,u=Depends(user)):
    if u['role']!='admin':
        raise HTTPException(403,'Admin only')
    return create_user(body,body.role)

@app.get('/api/courses')
def courses(u=Depends(user)):
    with core.db() as con:
        if u['role']=='admin':
            return core.rows(con,'SELECT * FROM courses ORDER BY id DESC')
        if u['role']=='teacher':
            return core.rows(con,'SELECT * FROM courses WHERE owner_id=? ORDER BY id DESC',(u['id'],))
        return core.rows(con,'SELECT c.* FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE e.student_id=? ORDER BY c.id DESC',(u['id'],))

@app.post('/api/courses')
def add_course(body:CourseBody,u=Depends(user)):
    staff(u)
    with core.db() as con:
        cur=con.execute('INSERT INTO courses(owner_id,title,description,tags,created) VALUES(?,?,?,?,?)',(u['id'],body.title,body.description,body.tags,time.time()))
        log(con,u,'Created course: '+body.title)
        return {'id':cur.lastrowid}

@app.put('/api/courses/{cid}')
def edit_course(cid:int,body:CourseBody,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u,True)
        con.execute('UPDATE courses SET title=?,description=?,tags=? WHERE id=?',(body.title,body.description,body.tags,cid))
    return {'ok':True}

@app.delete('/api/courses/{cid}')
def delete_course(cid:int,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u,True)
        files=core.rows(con,'SELECT d.stored FROM documents d JOIN lessons l ON d.lesson_id=l.id JOIN units un ON un.id=l.unit_id WHERE un.course_id=?',(cid,))
        con.execute('DELETE FROM courses WHERE id=?',(cid,))
    for f in files:
        (core.DATA/'uploads'/f['stored']).unlink(missing_ok=True)
    return {'ok':True}

@app.get('/api/courses/{cid}')
def detail(cid:int,u=Depends(user)):
    with core.db() as con:
        c=course_access(con,cid,u)
        units=core.rows(con,'SELECT * FROM units WHERE course_id=?',(cid,))
        for unit in units:
            unit['lessons']=core.rows(con,'SELECT * FROM lessons WHERE unit_id=?'+(' AND published=1' if u['role']=='student' else ''),(unit['id'],))
            for lesson in unit['lessons']:
                lesson['documents']=core.rows(con,'SELECT id,name,created,length(text) as characters FROM documents WHERE lesson_id=?',(lesson['id'],))
                lesson['summaries']=core.rows(con,'SELECT * FROM summaries WHERE lesson_id=? ORDER BY id DESC',(lesson['id'],))
        c['units']=units
        c['exams']=core.rows(con,'SELECT * FROM exams WHERE course_id=?'+(' AND published=1' if u['role']=='student' else ''),(cid,))
        c['students']=core.rows(con,'SELECT u.id,u.name,u.email FROM users u JOIN enrollments e ON e.student_id=u.id WHERE e.course_id=?',(cid,)) if u['role']!='student' else []
        c['announcements']=core.rows(con,'SELECT * FROM announcements WHERE course_id=? ORDER BY id DESC',(cid,))
        return c

@app.post('/api/courses/{cid}/units')
def add_unit(cid:int,body:UnitBody,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u,True)
        return {'id':con.execute('INSERT INTO units(course_id,title) VALUES(?,?)',(cid,body.title)).lastrowid}

@app.post('/api/units/{uid}/lessons')
def add_lesson(uid:int,body:LessonBody,u=Depends(user)):
    with core.db() as con:
        unit=con.execute('SELECT course_id FROM units WHERE id=?',(uid,)).fetchone()
        if not unit: raise HTTPException(404,'Unit not found')
        course_access(con,unit['course_id'],u,True)
        return {'id':con.execute('INSERT INTO lessons(unit_id,title,description,objectives,published) VALUES(?,?,?,?,?)',(uid,body.title,body.description,body.objectives,body.published)).lastrowid}

@app.put('/api/lessons/{lid}')
def edit_lesson(lid:int,body:LessonBody,u=Depends(user)):
    with core.db() as con:
        lesson_access(con,lid,u,True)
        con.execute('UPDATE lessons SET title=?,description=?,objectives=?,published=?,version=version+1 WHERE id=?',(body.title,body.description,body.objectives,body.published,lid))
    return {'ok':True}

class Enrollment(BaseModel):
    email:str

@app.post('/api/courses/{cid}/enroll')
def enroll(cid:int,body:Enrollment,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u,True)
        s=con.execute("SELECT id FROM users WHERE email=? AND role='student'",(body.email.strip().lower(),)).fetchone()
        if not s: raise HTTPException(404,'Student must register first')
        con.execute('INSERT OR IGNORE INTO enrollments VALUES(?,?)',(cid,s['id']))
    return {'ok':True}

@app.post('/api/courses/{cid}/announcements')
def announce(cid:int,body:UnitBody,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u,True)
        con.execute('INSERT INTO announcements(course_id,text,created) VALUES(?,?,?)',(cid,body.title,time.time()))
    return {'ok':True}


def extract_text(data,suffix):
    if suffix in ('.docx','.pptx'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist())>60*1024*1024:
                raise ValueError('Expanded document is too large')
    if suffix=='.txt':
        return data.decode('utf-8-sig')
    if suffix=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data))
        if len(reader.pages)>300: raise ValueError('Maximum 300 pages')
        return '\n'.join(p.extract_text() or '' for p in reader.pages)
    if suffix=='.docx':
        from docx import Document
        doc=Document(io.BytesIO(data))
        return '\n'.join([p.text for p in doc.paragraphs]+[' | '.join(c.text for c in r.cells) for t in doc.tables for r in t.rows])
    if suffix=='.pptx':
        from pptx import Presentation
        return '\n'.join(s.text for slide in Presentation(io.BytesIO(data)).slides for s in slide.shapes if s.has_text_frame)
    raise ValueError('Use PDF, DOCX, PPTX or UTF-8 TXT')

@app.post('/api/lessons/{lid}/documents')
def upload(lid:int,file:UploadFile=File(...),u=Depends(user)):
    with core.db() as con: lesson_access(con,lid,u,True)
    suffix=Path(file.filename or '').suffix.lower()
    data=file.file.read(10*1024*1024+1)
    if len(data)>10*1024*1024: raise HTTPException(413,'Maximum file size is 10 MB')
    try:
        text=extract_text(data,suffix).strip()
        if not text: raise ValueError('No readable text. Scanned documents need OCR, which is not included.')
        if len(text)>1000000: raise ValueError('Extracted text exceeds 1 million characters')
    except Exception as exc:
        raise HTTPException(422, str(exc) if isinstance(exc,ValueError) else 'Could not parse file. Check that it is a valid, unencrypted document.')
    stored=secrets.token_hex(20)+suffix
    (core.DATA/'uploads'/stored).write_bytes(data)
    try:
        with core.db() as con:
            cur=con.execute('INSERT INTO documents(lesson_id,name,stored,text,created) VALUES(?,?,?,?,?)',(lid,Path(file.filename.replace('\\','/')).name[:200],stored,text,time.time()))
            log(con,u,'Uploaded lesson material')
            return {'id':cur.lastrowid,'characters':len(text)}
    except Exception:
        (core.DATA/'uploads'/stored).unlink(missing_ok=True)
        raise

@app.get('/api/documents/{did}')
def document(did:int,u=Depends(user)):
    with core.db() as con:
        d=con.execute('SELECT * FROM documents WHERE id=?',(did,)).fetchone()
        if not d: raise HTTPException(404,'Document not found')
        lesson_access(con,d['lesson_id'],u)
        return {'id':d['id'],'name':d['name'],'text':d['text']}

@app.get('/api/documents/{did}/download')
def download(did:int,u=Depends(user)):
    with core.db() as con:
        d=con.execute('SELECT * FROM documents WHERE id=?',(did,)).fetchone()
        if not d: raise HTTPException(404,'Document not found')
        lesson_access(con,d['lesson_id'],u)
        return FileResponse(core.DATA/'uploads'/d['stored'],filename=d['name'],media_type='application/octet-stream')

@app.delete('/api/documents/{did}')
def delete_document(did:int,u=Depends(user)):
    with core.db() as con:
        d=con.execute('SELECT * FROM documents WHERE id=?',(did,)).fetchone()
        if not d: raise HTTPException(404,'Document not found')
        lesson_access(con,d['lesson_id'],u,True)
        con.execute('DELETE FROM documents WHERE id=?',(did,))
    (core.DATA/'uploads'/d['stored']).unlink(missing_ok=True)
    return {'ok':True}

class AIRequest(BaseModel):
    style: Literal['Detailed','Revision','Key concepts']='Detailed'
    language: Literal['English','Arabic']='English'
    query:str=Field(default='',max_length=2000)

def ai_call(*args,**kwargs):
    try: return ai.complete(*args,**kwargs)
    except ai.AIError as exc: raise HTTPException(503,str(exc))

@app.post('/api/lessons/{lid}/summary')
def summarize(lid:int,body:AIRequest,u=Depends(user)):
    with core.db() as con:
        lesson_access(con,lid,u,True)
        docs=core.rows(con,'SELECT * FROM documents WHERE lesson_id=?',(lid,))
    source='\n\n'.join(f"[Document {d['id']}: {d['name']}]\n{d['text']}" for d in docs)
    text=ai_call(f'Write a {body.style} summary in {body.language}. Include key concepts and cite document IDs.',source)
    with core.db() as con:
        con.execute('INSERT INTO summaries(lesson_id,text,style,created) VALUES(?,?,?,?)',(lid,text,body.style,time.time()))
    return {'text':text}

@app.post('/api/courses/{cid}/chat')
def chat(cid:int,body:AIRequest,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u)
        docs=core.rows(con,'SELECT d.* FROM documents d JOIN lessons l ON l.id=d.lesson_id JOIN units un ON un.id=l.unit_id WHERE un.course_id=?'+(' AND l.published=1' if u['role']=='student' else ''),(cid,))
    return {'text':ai_call(f'Answer in {body.language}, citing document and passage IDs. Question: {body.query}',core.retrieve(docs,body.query))}

class ExamBody(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    duration:int=Field(default=30,ge=1,le=300)

@app.post('/api/courses/{cid}/exams')
def create_exam(cid:int,body:ExamBody,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u,True)
        return {'id':con.execute('INSERT INTO exams(course_id,title,duration,created) VALUES(?,?,?,?)',(cid,body.title,body.duration,time.time())).lastrowid}

@app.get('/api/exams/{eid}')
def exam(eid:int,u=Depends(user)):
    with core.db() as con:
        e=exam_access(con,eid,u)
        if u['role']=='student':
            # Question content is only available after starting a timed attempt.
            return e
        e['questions']=questions_for(con,eid)
        e['attempt_count']=con.execute('SELECT count(*) FROM attempts WHERE exam_id=?',(eid,)).fetchone()[0]
        return e

def editable(con,eid,u):
    e=exam_access(con,eid,u,True)
    if e['published'] or con.execute('SELECT 1 FROM attempts WHERE exam_id=?',(eid,)).fetchone():
        raise HTTPException(409,'Published exams and exams with attempts are locked. Create another exam to revise content.')
    return e

@app.post('/api/exams/{eid}/questions')
def add_question(eid:int,body:dict,u=Depends(user)):
    try: q=core.validate_question(body)
    except (ValueError,TypeError) as exc: raise HTTPException(422,str(exc))
    with core.db() as con:
        e=editable(con,eid,u)
        lid=body.get('lesson_id') or None
        if lid and lesson_access(con,int(lid),u,True)['course_id']!=e['course_id']: raise HTTPException(422,'Lesson belongs to another course')
        qid=con.execute('INSERT INTO questions(course_id,lesson_id,data,created) VALUES(?,?,?,?)',(e['course_id'],lid,json.dumps(q),time.time())).lastrowid
        con.execute('INSERT INTO exam_questions VALUES(?,?,?)',(eid,qid,con.execute('SELECT count(*) FROM exam_questions WHERE exam_id=?',(eid,)).fetchone()[0]))
    return {'id':qid}

@app.put('/api/exams/{eid}/questions/{qid}')
def update_question(eid:int,qid:int,body:dict,u=Depends(user)):
    try: q=core.validate_question(body)
    except (ValueError,TypeError) as exc: raise HTTPException(422,str(exc))
    with core.db() as con:
        e=editable(con,eid,u)
        if not con.execute('SELECT 1 FROM exam_questions WHERE exam_id=? AND question_id=?',(eid,qid)).fetchone(): raise HTTPException(404,'Question not found')
        # Copy on edit keeps other exams using the bank question unchanged.
        old=con.execute('SELECT lesson_id FROM questions WHERE id=?',(qid,)).fetchone()
        new=con.execute('INSERT INTO questions(course_id,lesson_id,data,created) VALUES(?,?,?,?)',(e['course_id'],old['lesson_id'],json.dumps(q),time.time())).lastrowid
        con.execute('UPDATE exam_questions SET question_id=? WHERE exam_id=? AND question_id=?',(new,eid,qid))
    return {'id':new}

@app.delete('/api/exams/{eid}/questions/{qid}')
def remove_question(eid:int,qid:int,u=Depends(user)):
    with core.db() as con:
        editable(con,eid,u)
        con.execute('DELETE FROM exam_questions WHERE exam_id=? AND question_id=?',(eid,qid))
    return {'ok':True}

class IDs(BaseModel):
    ids:list[int]=Field(max_length=100)

@app.put('/api/exams/{eid}/order')
def reorder(eid:int,body:IDs,u=Depends(user)):
    with core.db() as con:
        editable(con,eid,u)
        existing=[q['id'] for q in questions_for(con,eid)]
        if len(body.ids)!=len(existing) or set(body.ids)!=set(existing): raise HTTPException(422,'Provide every question ID exactly once')
        for i,qid in enumerate(body.ids): con.execute('UPDATE exam_questions SET position=? WHERE exam_id=? AND question_id=?',(i,eid,qid))
    return {'ok':True}

@app.post('/api/exams/{eid}/reuse')
def reuse(eid:int,body:IDs,u=Depends(user)):
    with core.db() as con:
        e=editable(con,eid,u)
        for qid in body.ids:
            q=con.execute('SELECT * FROM questions WHERE id=?',(qid,)).fetchone()
            if not q or q['course_id']!=e['course_id']: raise HTTPException(422,'Question must be from this course')
            n=con.execute('SELECT count(*) FROM exam_questions WHERE exam_id=?',(eid,)).fetchone()[0]
            con.execute('INSERT OR IGNORE INTO exam_questions VALUES(?,?,?)',(eid,qid,n))
    return {'ok':True}

@app.get('/api/courses/{cid}/bank')
def bank(cid:int,u=Depends(user)):
    with core.db() as con:
        course_access(con,cid,u,True)
        return [dict(id=r['id'],lesson_id=r['lesson_id'],uses=r['uses'],**json.loads(r['data'])) for r in con.execute('SELECT q.*, (SELECT count(*) FROM exam_questions eq WHERE eq.question_id=q.id) as uses FROM questions q WHERE course_id=? ORDER BY id DESC',(cid,))]

class Generate(AIRequest):
    lesson_ids:list[int]=Field(min_length=1,max_length=30)
    count:int=Field(default=5,ge=1,le=30)
    difficulty:Literal['Easy','Medium','Hard','Mixed']='Mixed'
    kind:str='mcq'

@app.post('/api/exams/{eid}/generate')
def generate(eid:int,body:Generate,u=Depends(user)):
    if body.kind not in core.KINDS: raise HTTPException(422,'Unsupported question type')
    source=[]
    with core.db() as con:
        e=editable(con,eid,u)
        for lid in dict.fromkeys(body.lesson_ids):
            lesson=lesson_access(con,lid,u,True)
            if lesson['course_id']!=e['course_id']: raise HTTPException(422,'Lesson must belong to exam course')
            docs=core.rows(con,'SELECT * FROM documents WHERE lesson_id=?',(lid,))
            source.extend(f"[Lesson {lid}, Document {d['id']}: {d['name']}]\n{d['text']}" for d in docs)
    task=f'''Generate exactly {body.count} distinct {body.kind} questions in {body.language}, difficulty {body.difficulty}, based only on the source. Distribute across the selected lessons. Return a JSON object with key questions (array). Each item must have lesson_id (from source), kind, text, options (array), answer (exact option text for choice questions, model answer/rubric otherwise), marks (1-100), difficulty (Easy/Medium/Hard), explanation (cite source document). For true_false options are True and False. For other non-choice types options is [].'''
    result=ai_call(task,'\n\n'.join(source),True)
    try:
        items=result['questions']
        if not isinstance(items,list) or len(items)!=body.count: raise ValueError('Wrong question count')
        validated=[]
        seen=set()
        for item in items:
            q=core.validate_question(item)
            lid=int(item['lesson_id'])
            if lid not in body.lesson_ids or q['kind']!=body.kind: raise ValueError('Invalid lesson or type')
            key=core.normalized(q['text'])
            if key in seen: raise ValueError('Duplicate questions')
            seen.add(key)
            validated.append((lid,q))
    except (KeyError,ValueError,TypeError):
        raise HTTPException(502,'AI output failed validation. No questions saved. Try again or add manually.')
    with core.db() as con:
        editable(con,eid,u)
        n=len(questions_for(con,eid))
        for i,(lid,q) in enumerate(validated):
            qid=con.execute('INSERT INTO questions(course_id,lesson_id,data,created) VALUES(?,?,?,?)',(e['course_id'],lid,json.dumps(q),time.time())).lastrowid
            con.execute('INSERT INTO exam_questions VALUES(?,?,?)',(eid,qid,n+i))
        log(con,u,'Generated an exam draft for review')
    return {'count':len(validated)}

@app.post('/api/exams/{eid}/publish')
def publish(eid:int,u=Depends(user)):
    with core.db() as con:
        e=editable(con,eid,u)
        if not questions_for(con,eid): raise HTTPException(422,'Add at least one question first')
        con.execute('UPDATE exams SET published=1 WHERE id=?',(eid,))
        log(con,u,'Published exam: '+e['title'])
    return {'ok':True}

def attempt_view(con,a):
    result=dict(a)
    questions=questions_for(con,a['exam_id'])
    if not a['submitted']:
        questions=[{k:v for k,v in q.items() if k not in ('answer','explanation')} for q in questions]
    result['questions']=questions
    result['answers']=json.loads(a['answers'])
    result['grading']=json.loads(a['grading']) if a['grading'] else None
    result['server_time']=time.time()
    return result

def finalize(con,a,questions):
    report=core.grade(questions,json.loads(a['answers']))
    con.execute('UPDATE attempts SET submitted=?,grading=? WHERE id=?',(time.time(),json.dumps(report),a['id']))

@app.post('/api/exams/{eid}/start')
def start(eid:int,u=Depends(user)):
    if u['role']!='student': raise HTTPException(403,'Student account required')
    with core.db() as con:
        e=exam_access(con,eid,u)
        now=time.time()
        con.execute('INSERT OR IGNORE INTO attempts(exam_id,student_id,started,deadline) VALUES(?,?,?,?)',(eid,u['id'],now,now+e['duration']*60))
        a=con.execute('SELECT * FROM attempts WHERE exam_id=? AND student_id=?',(eid,u['id'])).fetchone()
        if not a['submitted'] and time.time()>=a['deadline']:
            finalize(con,a,questions_for(con,eid))
            a=con.execute('SELECT * FROM attempts WHERE id=?',(a['id'],)).fetchone()
        return attempt_view(con,a)

class Answers(BaseModel):
    answers:dict[str,str]

@app.put('/api/attempts/{aid}')
def save(aid:int,body:Answers,u=Depends(user)):
    with core.db() as con:
        a=con.execute('SELECT * FROM attempts WHERE id=? AND student_id=?',(aid,u['id'])).fetchone()
        if not a: raise HTTPException(404,'Attempt not found')
        exam_access(con,a['exam_id'],u)
        if a['submitted']: raise HTTPException(409,'Already submitted')
        qs=questions_for(con,a['exam_id'])
        if time.time()>=a['deadline']:
            finalize(con,a,qs)
            return {'expired':True}
        valid={str(q['id']) for q in qs}
        if set(body.answers)-valid or any(len(v)>20000 for v in body.answers.values()): raise HTTPException(422,'Invalid answer data')
        con.execute('UPDATE attempts SET answers=? WHERE id=?',(json.dumps(body.answers),aid))
    return {'saved':True}

@app.post('/api/attempts/{aid}/submit')
def submit(aid:int,u=Depends(user)):
    with core.db() as con:
        a=con.execute('SELECT * FROM attempts WHERE id=? AND student_id=?',(aid,u['id'])).fetchone()
        if not a: raise HTTPException(404,'Attempt not found')
        exam_access(con,a['exam_id'],u)
        if not a['submitted']: finalize(con,a,questions_for(con,a['exam_id']))
        return attempt_view(con,con.execute('SELECT * FROM attempts WHERE id=?',(aid,)).fetchone())

@app.get('/api/exams/{eid}/results')
def results(eid:int,u=Depends(user)):
    with core.db() as con:
        exam_access(con,eid,u,True)
        attempts=core.rows(con,'SELECT a.*,u.name FROM attempts a JOIN users u ON u.id=a.student_id WHERE a.exam_id=?',(eid,))
        for a in attempts:
            if not a['submitted'] and time.time()>=a['deadline']:
                finalize(con,a,questions_for(con,eid))
                a.update(dict(con.execute('SELECT * FROM attempts WHERE id=?',(a['id'],)).fetchone()))
            a['grading']=json.loads(a['grading']) if a['grading'] else None
            a['answers']=json.loads(a['answers'])
        return attempts

class ManualGrade(BaseModel):
    scores:dict[str,float]

@app.post('/api/attempts/{aid}/grade')
def manual_grade(aid:int,body:ManualGrade,u=Depends(user)):
    with core.db() as con:
        a=con.execute('SELECT * FROM attempts WHERE id=?',(aid,)).fetchone()
        if not a: raise HTTPException(404,'Attempt not found')
        exam_access(con,a['exam_id'],u,True)
        if not a['submitted']: raise HTTPException(409,'Not submitted')
        report=json.loads(a['grading'])
        qmap={str(q['id']):q for q in questions_for(con,a['exam_id'])}
        for key,value in body.scores.items():
            q=qmap.get(key)
            if not q or q['kind'] in core.OBJECTIVE or not 0<=value<=q['marks']: raise HTTPException(422,'Invalid manual score')
            for d in report['details']:
                if str(d['question_id'])==key: d['score']=value
        report['score']=sum(d['score'] or 0 for d in report['details'])
        report['pending']=sum(d['score'] is None for d in report['details'])
        con.execute('UPDATE attempts SET grading=? WHERE id=?',(json.dumps(report),aid))
    return {'ok':True}

@app.get('/api/exams/{eid}/word')
def export_word(eid:int,answer_key:bool=False,language:str='English',u=Depends(user)):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    with core.db() as con:
        e=exam_access(con,eid,u,True)
        qs=questions_for(con,eid)
    doc=Document()
    doc.add_heading(e['title'],0)
    doc.add_paragraph(f"EduMind | {e['duration']} minutes | {sum(q['marks'] for q in qs):g} marks")
    doc.add_paragraph('Name: ____________________    Date: ____________________')
    for i,q in enumerate(qs):
        doc.add_heading(f"{i+1}. {q['text']} ({q['marks']:g})",2)
        for option in q['options']: doc.add_paragraph(option,style='List Bullet')
        if not q['options']: doc.add_paragraph('\n__________________________________________________\n')
        if answer_key: doc.add_paragraph('Answer: '+q['answer']+'\n'+q['explanation'])
    if language=='Arabic':
        for p in doc.paragraphs:
            bidi=OxmlElement('w:bidi');bidi.set(qn('w:val'),'1');p._p.get_or_add_pPr().append(bidi)
    out=io.BytesIO();doc.save(out);out.seek(0)
    return StreamingResponse(out,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':'attachment; filename="EduMind-exam.docx"'})

@app.get('/api/dashboard')
def dashboard(u=Depends(user)):
    with core.db() as con:
        if u['role']=='admin': cs=core.rows(con,'SELECT * FROM courses')
        elif u['role']=='teacher': cs=core.rows(con,'SELECT * FROM courses WHERE owner_id=?',(u['id'],))
        else: cs=core.rows(con,'SELECT c.* FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE e.student_id=?',(u['id'],))
        ids=[c['id'] for c in cs]
        counts={'courses':len(cs),'lessons':0,'documents':0,'students':0,'exams':0}
        exams=[];performance=[]
        if ids:
            placeholders=','.join('?'*len(ids))
            lessons=core.rows(con,f'SELECT l.* FROM lessons l JOIN units un ON un.id=l.unit_id WHERE un.course_id IN ({placeholders})'+(' AND l.published=1' if u['role']=='student' else ''),ids)
            counts['lessons']=len(lessons)
            if lessons:
                lids=[l['id'] for l in lessons]
                counts['documents']=con.execute('SELECT count(*) FROM documents WHERE lesson_id IN ('+','.join('?'*len(lids))+')',lids).fetchone()[0]
            if u['role']!='student': counts['students']=con.execute(f'SELECT count(DISTINCT student_id) FROM enrollments WHERE course_id IN ({placeholders})',ids).fetchone()[0]
            exams=core.rows(con,f'SELECT * FROM exams WHERE course_id IN ({placeholders})'+(' AND published=1' if u['role']=='student' else '')+' ORDER BY id DESC',ids)
            counts['exams']=len(exams)
            records=core.rows(con,f'SELECT a.grading,e.title FROM attempts a JOIN exams e ON e.id=a.exam_id WHERE e.course_id IN ({placeholders}) AND a.submitted IS NOT NULL'+(' AND a.student_id=?' if u['role']=='student' else ''),ids+([u['id']] if u['role']=='student' else []))
            for r in records:
                g=json.loads(r['grading'])
                performance.append({'title':r['title'],'score':g['score'],'total':g['total'],'pending':g['pending']})
        return {'counts':counts,'courses':cs,'exams':exams,'performance':performance,'activity':core.rows(con,'SELECT text,created FROM activity WHERE user_id=? ORDER BY id DESC LIMIT 8',(u['id'],)),'provider':os.getenv('AI_PROVIDER','gemini'),'ai_configured':bool(os.getenv('GEMINI_API_KEY') if os.getenv('AI_PROVIDER','gemini')=='gemini' else os.getenv('LLM_API_KEY'))}
