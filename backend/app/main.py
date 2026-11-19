import csv
import io
import os
import re
import secrets
import smtplib
import threading
import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from . import ml, search
from .config import ALLOWED_ORIGINS, APP_URL, ROOT, DEMO_LOGIN_EMAIL, DEMO_LOGIN_PASSWORD
from .db import User, Session, ResetToken, Prediction, Usage, Plan, Audit, get_db
from .security import current_user, admin, issue_session, public_user, has_unlimited_credits, hasher, verify, digest, DUMMY
from .reports import render_report

app=FastAPI(title='DeepDTA Research API',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=list(ALLOWED_ORIGINS),allow_credentials=True,allow_methods=['GET','POST','DELETE','PATCH'],allow_headers=['Content-Type','X-Research-Client'])
rate_lock=threading.Lock()
requests_by_key=defaultdict(deque)
write_lock=threading.RLock()
logger=logging.getLogger('research')

@app.middleware('http')
async def guard(request, call_next):
    if request.url.path.startswith('/api/'):
        if request.method in ['POST','PATCH','DELETE'] and request.url.path != '/api/billing/webhook':
            origin=request.headers.get('origin')
            if request.headers.get('X-Research-Client') != 'web' or (origin and origin not in ALLOWED_ORIGINS):
                return JSONResponse({'detail':'Request origin or CSRF header is invalid.'},status_code=403)
        try: length=int(request.headers.get('content-length','0'))
        except ValueError: return JSONResponse({'detail':'Invalid content length.'},status_code=400)
        if length > 2_000_000: return JSONResponse({'detail':'Request too large (2 MB maximum).'},status_code=413)
        # Single-worker limiter. Production uses one worker per deployment; add gateway limits before scaling.
        key=(request.client.host if request.client else 'unknown','auth' if '/auth/' in request.url.path else 'api')
        limit=25 if key[1]=='auth' else 180
        with rate_lock:
            stamp=time.monotonic()
            bucket=requests_by_key[key]
            while bucket and bucket[0]<stamp-60: bucket.popleft()
            if len(bucket)>=limit: return JSONResponse({'detail':'Too many requests. Retry in one minute.'},status_code=429,headers={'Retry-After':'60'})
            bucket.append(stamp)
            if len(requests_by_key)>10000:
                for k in list(requests_by_key):
                    if not requests_by_key[k] or requests_by_key[k][-1]<stamp-60: del requests_by_key[k]
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(ml.ModelUnavailable)
async def unavailable(request,exc): return JSONResponse({'detail':str(exc)},status_code=503)
@app.exception_handler(ValueError)
async def invalid(request,exc): return JSONResponse({'detail':str(exc)},status_code=422)

class Register(BaseModel):
    email: EmailStr
    name: str=Field(min_length=1,max_length=100)
    password: str=Field(min_length=12,max_length=128)
class Login(BaseModel):
    email: EmailStr
    password: str=Field(min_length=1,max_length=128)
class EmailInput(BaseModel): email: EmailStr
class ResetInput(BaseModel):
    token: str=Field(min_length=20,max_length=100)
    password: str=Field(min_length=12,max_length=128)
class PredictInput(BaseModel):
    smiles: str=Field(min_length=1,max_length=2000)
    sequence: str=Field(min_length=1,max_length=10000)
    drug_name: str=Field(default='Unnamed compound',max_length=200)
    protein_name: str=Field(default='Unnamed protein',max_length=200)
    dataset: Literal['davis','kiba']='davis'
    pubchem_cid: int | None=Field(default=None,gt=0)
    uniprot_accession: str | None=Field(default=None,pattern=r'^[A-Z0-9]{6,10}$')
class Selection(BaseModel): ids: list[str]=Field(min_length=1,max_length=100)

@app.get('/api/health')
def health(): return {'status':'ok'}
@app.get('/api/models')
def models(): return [ml.inspect('davis'),ml.inspect('kiba')]
@app.post('/api/auth/register',status_code=201)
def register(body:Register,response:Response,db=Depends(get_db)):
    if DEMO_LOGIN_EMAIL and str(body.email).lower()==DEMO_LOGIN_EMAIL:
        raise HTTPException(409,'This email is reserved for the shared demo login.')
    user=User(email=str(body.email).lower(),name=body.name.strip(),password_hash=hasher.hash(body.password))
    if not user.name: raise HTTPException(422,'Name is required.')
    db.add(user)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,'Unable to register this email. Try signing in or resetting your password.')
    issue_session(user,db,response)
    return public_user(user)
@app.post('/api/auth/login')
def login(body:Login,response:Response,db=Depends(get_db)):
    email=str(body.email).lower()
    user=db.scalar(select(User).where(User.email==email))
    if DEMO_LOGIN_EMAIL and email==DEMO_LOGIN_EMAIL:
        if not DEMO_LOGIN_PASSWORD or not secrets.compare_digest(body.password,DEMO_LOGIN_PASSWORD):
            raise HTTPException(401,'Email or password is incorrect.')
        if user and user.role!='demo':
            raise HTTPException(409,'This email belongs to another account; demo login is unavailable.')
        if not user:
            # Real predictions, sessions, and reports require an account row.
            # No reusable password hash is stored for this shared demo account.
            with write_lock:
                user=db.scalar(select(User).where(User.email==email).with_for_update())
                if not user:
                    user=User(email=email,name='Rohith Demo',role='demo',plan='free',
                              password_hash=hasher.hash(secrets.token_urlsafe(48)))
                    db.add(user)
                    try: db.commit()
                    except IntegrityError:
                        db.rollback()
                        user=db.scalar(select(User).where(User.email==email))
                if not user or user.role!='demo':
                    raise HTTPException(409,'This email belongs to another account; demo login is unavailable.')
    else:
        valid=verify(user.password_hash if user else DUMMY,body.password)
        if not user or not valid: raise HTTPException(401,'Email or password is incorrect.')
    issue_session(user,db,response)
    return public_user(user)
@app.get('/api/auth/me')
def me(user=Depends(current_user)): return public_user(user)
@app.post('/api/auth/logout')
def logout(request:Request,response:Response,db=Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash==digest(request.cookies.get('research_session','')))); db.commit()
    response.delete_cookie('research_session',path='/')
    return {'ok':True}
@app.post('/api/auth/forgot-password')
def forgot(body:EmailInput,db=Depends(get_db)):
    if not os.getenv('SMTP_HOST'): raise HTTPException(503,'Password reset email is not configured. Ask the administrator to configure SMTP.')
    user=db.scalar(select(User).where(User.email==str(body.email).lower()))
    if user:
        token=secrets.token_urlsafe(32)
        db.execute(delete(ResetToken).where(ResetToken.user_id==user.id))
        db.add(ResetToken(token_hash=digest(token),user_id=user.id,expires_at=time.time()+1800)); db.commit()
        message=EmailMessage(); message['Subject']='Reset your DeepDTA Research password'
        message['From']=os.getenv('SMTP_FROM','research@example.com'); message['To']=user.email
        message.set_content(f'Reset your password within 30 minutes: {APP_URL}/?reset={token}')
        try:
            with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=15) as smtp:
                smtp.starttls()
                if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
                smtp.send_message(message)
        except Exception:
            logger.error('Password reset delivery failed')
    return {'message':'If this email has an account, a reset link will be sent.'}
@app.post('/api/auth/reset-password')
def reset(body:ResetInput,db=Depends(get_db)):
    with write_lock:
        token=db.scalar(select(ResetToken).where(ResetToken.token_hash==digest(body.token)).with_for_update())
        if not token or token.expires_at<time.time(): raise HTTPException(400,'Reset link is invalid or expired.')
        user=db.get(User,token.user_id); user.password_hash=hasher.hash(body.password)
        db.execute(delete(Session).where(Session.user_id==user.id)); db.delete(token); db.commit()
    return {'message':'Password changed. Sign in with your new password.'}

class ProfileInput(BaseModel): name:str=Field(min_length=1,max_length=100)
@app.patch('/api/auth/profile')
def profile(body:ProfileInput,user=Depends(current_user),db=Depends(get_db)):
    if not body.name.strip(): raise HTTPException(422,'Name is required.')
    user.name=body.name.strip(); db.commit(); return public_user(user)

def serialize(p):
    from .strength_guide import describe
    return {**{k:getattr(p,k) for k in ['id','drug_name','protein_name','smiles','sequence','dataset','score','model_version','provenance','created_at']},
            'strength_guide':describe(p.dataset,p.score)}
def owned(prediction_id,user,db):
    p=db.scalar(select(Prediction).where(Prediction.id==prediction_id,Prediction.user_id==user.id))
    if not p: raise HTTPException(404,'Prediction not found.')
    return p

def run_predictions(bodies,user,db):
    results=[ml.predict(body.dataset,body.smiles.strip(),body.sequence) for body in bodies]
    with write_lock:
        account=db.scalar(select(User).where(User.id==user.id).with_for_update())
        month=datetime.now(timezone.utc).strftime('%Y-%m')
        usage=db.get(Usage,(user.id,month))
        plan=db.get(Plan,account.plan) or db.get(Plan,'free')
        if not plan: raise HTTPException(503,'Plans have not been initialized. Run database migrations.')
        if not has_unlimited_credits(account) and (usage.count if usage else 0)+len(bodies)>plan.monthly_limit:
            raise HTTPException(402,'Insufficient monthly prediction credits for this operation. Review your subscription.')
        if not usage:
            usage=Usage(user_id=user.id,month=month,count=0); db.add(usage)
        records=[]
        for body,result in zip(bodies,results):
            sources=[]
            if body.pubchem_cid: sources.append(f'User-selected PubChem CID: https://pubchem.ncbi.nlm.nih.gov/compound/{body.pubchem_cid}')
            if body.uniprot_accession: sources.append(f'User-selected UniProt accession: https://www.uniprot.org/uniprotkb/{body.uniprot_accession}/entry')
            result['provenance']['sources']=sources
            p=Prediction(user_id=user.id,drug_name=body.drug_name,protein_name=body.protein_name,smiles=body.smiles.strip(),sequence=result['sequence'],dataset=body.dataset,score=result['score'],model_version=result['model_version'],provenance=result['provenance'])
            db.add(p); records.append(p)
        usage.count+=len(bodies); db.commit()
        return records

def run_prediction(body,user,db): return run_predictions([body],user,db)[0]
@app.post('/api/predictions',status_code=201)
def create_prediction(body:PredictInput,user=Depends(current_user),db=Depends(get_db)):
    return serialize(run_prediction(body,user,db))
@app.get('/api/predictions')
def history(q:str='',dataset:str='',offset:int=0,user=Depends(current_user),db=Depends(get_db)):
    stmt=select(Prediction).where(Prediction.user_id==user.id)
    if q:
        q=q[:200]; stmt=stmt.where(Prediction.drug_name.icontains(q,autoescape=True)|Prediction.protein_name.icontains(q,autoescape=True)|Prediction.id.icontains(q,autoescape=True))
    if dataset: stmt=stmt.where(Prediction.dataset==dataset)
    return [serialize(p) for p in db.scalars(stmt.order_by(Prediction.created_at.desc()).offset(max(0,offset)).limit(100))]
@app.get('/api/predictions/{prediction_id}')
def detail(prediction_id:str,user=Depends(current_user),db=Depends(get_db)): return serialize(owned(prediction_id,user,db))
class EvidenceInput(BaseModel):
    compound_id: str=Field(default='',max_length=30)
    accession: str=Field(default='',max_length=20)
@app.post('/api/predictions/{prediction_id}/experimental')
def experimental_comparison(prediction_id:str,body:EvidenceInput,user=Depends(current_user),db=Depends(get_db)):
    from .experimental import compare
    prediction=owned(prediction_id,user,db)
    evidence=compare(prediction,body.compound_id,body.accession)
    # Reassign JSON so SQLAlchemy persists the immutable evidence snapshot.
    prediction.provenance={**prediction.provenance,'experimental_evidence':evidence}
    db.commit()
    return evidence

@app.delete('/api/predictions/{prediction_id}')
def remove(prediction_id:str,user=Depends(current_user),db=Depends(get_db)):
    db.delete(owned(prediction_id,user,db)); db.commit(); return {'ok':True}
@app.get('/api/predictions/{prediction_id}/report')
def report(prediction_id:str,user=Depends(current_user),db=Depends(get_db)):
    p=owned(prediction_id,user,db)
    return Response(render_report([p],user),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="prediction-{p.id}.pdf"'})
@app.post('/api/reports/combined')
def combined(body:Selection,user=Depends(current_user),db=Depends(get_db)):
    records=[owned(i,user,db) for i in dict.fromkeys(body.ids)]
    return Response(render_report(records,user),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="research-report.pdf"'})
@app.post('/api/export')
def export(body:Selection,user=Depends(current_user),db=Depends(get_db)):
    output=io.StringIO(); fields=['id','drug_name','protein_name','dataset','score','smiles','sequence','model_version','created_at']
    writer=csv.DictWriter(output,fieldnames=fields); writer.writeheader()
    for id in dict.fromkeys(body.ids):
        p=owned(id,user,db); row={k:getattr(p,k) for k in fields}
        for key,value in row.items():
            if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')): row[key]="'"+value
        writer.writerow(row)
    return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="predictions.csv"'})
@app.get('/api/dashboard')
def dashboard(user=Depends(current_user),db=Depends(get_db)):
    counts=dict(db.execute(select(Prediction.dataset,func.count()).where(Prediction.user_id==user.id).group_by(Prediction.dataset)).all())
    month=datetime.now(timezone.utc).strftime('%Y-%m'); usage=db.get(Usage,(user.id,month)); plan=db.get(Plan,user.plan)
    unlimited=has_unlimited_credits(user)
    return {'counts':counts,'total':sum(counts.values()),'month':month,'used':usage.count if usage else 0,'limit':None if unlimited else (plan.monthly_limit if plan else 0),'unlimited_credits':unlimited,'plan':user.plan}
@app.get('/api/search/drugs')
def drug_search(q:str,kind:str='name',user=Depends(current_user)):
    if not 1<=len(q)<=2000: raise HTTPException(422,'Enter a search query (maximum 2000 characters).')
    return search.drugs(q,kind)
@app.get('/api/search/proteins')
def protein_search(q:str,user=Depends(current_user)):
    if not 1<=len(q)<=500: raise HTTPException(422,'Enter a protein name, gene, accession or UniProt query (maximum 500 characters).')
    return search.proteins(q)

@app.post('/api/batch')
async def batch(file:UploadFile=File(...),user=Depends(current_user),db=Depends(get_db)):
    raw=await file.read(1_000_001)
    if len(raw)>1_000_000: raise HTTPException(413,'CSV maximum size is 1 MB.')
    try: rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    except (UnicodeError,csv.Error): raise HTTPException(422,'Upload a UTF-8 CSV.')
    if not rows or len(rows)>50: raise HTTPException(422,'Upload 1–50 rows per batch. Large background jobs are not enabled.')
    if not {'smiles','sequence'}.issubset(rows[0]): raise HTTPException(422,'CSV requires smiles and sequence columns. Optional: dataset, drug_name, protein_name.')
    results=[]
    # Synchronous inference is run in a worker thread, not on the event loop.
    from starlette.concurrency import run_in_threadpool
    for i,row in enumerate(rows):
        try:
            body=PredictInput(**{k:v for k,v in row.items() if v and k in PredictInput.model_fields})
            p=await run_in_threadpool(run_prediction,body,user,db)
            results.append({'row':i+2,'prediction':serialize(p)})
        except (ValueError,ml.ModelUnavailable,HTTPException) as exc:
            db.rollback(); results.append({'row':i+2,'error':getattr(exc,'detail',str(exc))})
    return results

from .advanced import router as advanced_router
from .billing import router as billing_router
from .docking import router as docking_router
from .compound import router as compound_router
app.include_router(advanced_router)
app.include_router(billing_router)
app.include_router(docking_router)
app.include_router(compound_router)

@app.get('/api/admin/stats')
def admin_stats(user=Depends(admin),db=Depends(get_db)):
    return {'users':db.scalar(select(func.count()).select_from(User)),'predictions':db.scalar(select(func.count()).select_from(Prediction)),'subscriptions':dict(db.execute(select(User.plan,func.count()).group_by(User.plan)).all())}
@app.get('/api/admin/plans')
def admin_plans(user=Depends(admin),db=Depends(get_db)):
    return [{'id':p.id,'monthly_limit':p.monthly_limit,'price_id':p.price_id,'description':p.description} for p in db.scalars(select(Plan).order_by(Plan.monthly_limit))]

class PlanInput(BaseModel):
    monthly_limit:int=Field(ge=0,le=1000000)
    price_id:str | None=Field(default=None,pattern=r'^price_[A-Za-z0-9]+$')
    description:str=Field(min_length=1,max_length=500)
@app.patch('/api/admin/plans/{plan_id}')
def update_plan(plan_id:str,body:PlanInput,user=Depends(admin),db=Depends(get_db)):
    plan=db.get(Plan,plan_id)
    if not plan: raise HTTPException(404,'Plan not found.')
    for k,v in body.model_dump().items(): setattr(plan,k,v)
    db.add(Audit(actor_id=user.id,action='update_plan',details={'plan':plan_id,**body.model_dump()})); db.commit()
    return {'ok':True}

from .kiba_data import router as kiba_router
app.include_router(kiba_router)

# API routes must be registered before the production frontend mount.
@app.get('/demo', include_in_schema=False)
def demo_page():
    return FileResponse(ROOT/'frontend/dist/demo.html')

if (ROOT/'frontend/dist').exists(): app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')
