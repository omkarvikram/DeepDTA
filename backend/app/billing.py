import os
import threading
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import Plan, User, BillingEvent, get_db
from .security import current_user
from .config import APP_URL
router=APIRouter(prefix='/api/billing')
lock=threading.RLock()
def configured():
    key=os.getenv('STRIPE_SECRET_KEY','')
    return key.startswith('sk_test_') and bool(os.getenv('STRIPE_WEBHOOK_SECRET'))
def client():
    if not configured(): raise HTTPException(503,'Stripe test billing is not configured. Add test API and webhook keys on the server.')
    stripe.api_key=os.environ['STRIPE_SECRET_KEY']
    return stripe
@router.get('/plans')
def plans(db=Depends(get_db)):
    prices={'free':0,'plus':599,'pro':1299,'ultra':2499}
    return {'configured':configured(),'mode':'test','plans':[{'id':p.id,'monthly_limit':p.monthly_limit,'price_inr':prices[p.id],'description':p.description,'checkout_enabled':configured() and bool(p.price_id)} for p in db.scalars(select(Plan).order_by(Plan.monthly_limit)) if p.id in prices]}
class CheckoutInput(BaseModel): plan:str
@router.post('/checkout')
def checkout(body:CheckoutInput,user=Depends(current_user),db=Depends(get_db)):
    api=client(); plan=db.get(Plan,body.plan)
    if not plan or not plan.price_id or plan.id=='free': raise HTTPException(422,'Select a paid plan with a configured Stripe test price.')
    if user.stripe_subscription: raise HTTPException(409,'Manage your existing subscription in the billing portal.')
    try:
        with lock:
            if not user.stripe_customer:
                customer=api.Customer.create(email=user.email,metadata={'user_id':user.id},idempotency_key='customer-'+user.id)
                user.stripe_customer=customer.id; db.commit()
        session=api.checkout.Session.create(mode='subscription',customer=user.stripe_customer,line_items=[{'price':plan.price_id,'quantity':1}],success_url=APP_URL+'/?billing=success',cancel_url=APP_URL+'/?billing=cancelled',subscription_data={'metadata':{'user_id':user.id}},client_reference_id=user.id)
        return {'url':session.url}
    except stripe.StripeError as exc: raise HTTPException(502,'Stripe test checkout could not be created. Check server billing configuration.') from exc
@router.post('/portal')
def portal(user=Depends(current_user)):
    api=client()
    if not user.stripe_customer: raise HTTPException(404,'No billing customer exists yet.')
    try: return {'url':api.billing_portal.Session.create(customer=user.stripe_customer,return_url=APP_URL).url}
    except stripe.StripeError as exc: raise HTTPException(502,'Billing portal unavailable. Configure the Stripe test customer portal.') from exc
@router.post('/webhook')
async def webhook(request:Request,db=Depends(get_db)):
    api=client(); payload=await request.body()
    if len(payload)>1_000_000: raise HTTPException(413,'Webhook too large.')
    try: event=api.Webhook.construct_event(payload,request.headers.get('stripe-signature',''),os.environ['STRIPE_WEBHOOK_SECRET'])
    except (ValueError,stripe.SignatureVerificationError): raise HTTPException(400,'Invalid webhook signature.')
    if event.livemode: raise HTTPException(400,'Only test-mode events are accepted.')
    with lock:
        if db.get(BillingEvent,event.id): return {'received':True}
        obj=event.data.object
        if event.type.startswith('customer.subscription.'):
            # Fetch current state to avoid granting access from stale or out-of-order event payloads.
            try: subscription=api.Subscription.retrieve(obj.id)
            except stripe.StripeError as exc: raise HTTPException(502,'Could not reconcile subscription; retry webhook.') from exc
            user=db.scalar(select(User).where(User.stripe_customer==subscription.customer).with_for_update())
            if user:
                price=subscription['items']['data'][0]['price']['id'] if subscription['items']['data'] else None
                plan=db.scalar(select(Plan).where(Plan.price_id==price)) if price else None
                user.plan=plan.id if plan and subscription.status in ['active','trialing'] else 'free'
                user.stripe_subscription=subscription.id if subscription.status not in ['canceled','incomplete_expired'] else None
        db.add(BillingEvent(id=event.id,event_type=event.type))
        try: db.commit()
        except IntegrityError: db.rollback()
    return {'received':True}
