"""Local operator commands; never expose role changes through public registration."""
import argparse
from sqlalchemy import select
from app.db import SessionLocal,User,Audit
parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['make-admin'])
parser.add_argument('email')
args=parser.parse_args()
with SessionLocal() as db:
    user=db.scalar(select(User).where(User.email==args.email.lower()))
    if not user: raise SystemExit('Register this account first.')
    user.role='admin';db.add(Audit(actor_id='local-operator',action='grant_admin',details={'user_id':user.id}));db.commit()
    print('Administrator role assigned to the registered account.')
