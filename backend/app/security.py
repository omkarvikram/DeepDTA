import hashlib
import secrets
import time
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from .db import Session, User, get_db
from .config import COOKIE_SECURE
from . import config

hasher = PasswordHasher()
DUMMY = hasher.hash('not-a-real-user-password')
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def verify(stored, raw):
    try: return hasher.verify(stored, raw)
    except (VerifyMismatchError, InvalidHashError): return False

def issue_session(user, db, response):
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=digest(token), user_id=user.id, expires_at=time.time()+86400))
    db.commit()
    response.set_cookie('research_session', token, httponly=True, secure=COOKIE_SECURE, samesite='lax', max_age=86400, path='/')

def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get('research_session', '')
    session = db.get(Session, digest(token))
    if not session or session.expires_at < time.time(): raise HTTPException(401, 'Please sign in.')
    user = db.get(User, session.user_id)
    if not user: raise HTTPException(401, 'Please sign in.')
    return user

def admin(user=Depends(current_user)):
    if user.role != 'admin': raise HTTPException(403, 'Administrator access required.')
    return user

def has_unlimited_credits(user):
    return user.id in config.UNLIMITED_CREDIT_USER_IDS or (
        bool(config.DEMO_LOGIN_EMAIL) and user.role == 'demo' and user.email == config.DEMO_LOGIN_EMAIL
    )

def public_user(user):
    return {**{k:getattr(user,k) for k in ['id','name','email','role','plan','created_at']}, 'unlimited_credits':has_unlimited_credits(user)}
