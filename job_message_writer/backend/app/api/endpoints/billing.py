"""Stripe billing endpoints — checkout sessions, webhook, plan info."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging
import stripe

from app.db.database import get_db
from app.db import models
from app.core.supabase_auth import get_current_user
from app.core.config import settings
from app.core.rate_limit import TIER_LIMITS

router = APIRouter()
logger = logging.getLogger(__name__)

# Plan definitions
PLANS = {
    "pro": {
        "name": "Pro",
        "price": 1000,  # cents
        "price_display": "$10",
        "messages": TIER_LIMITS["pro"]["message_generation"],
        "resumes": TIER_LIMITS["pro"]["resume_tailor"],
        "tier": "pro",
    },
    "business": {
        "name": "Business",
        "price": 2000,
        "price_display": "$20",
        "messages": TIER_LIMITS["business"]["message_generation"],
        "resumes": TIER_LIMITS["business"]["resume_tailor"],
        "tier": "business",
    },
    "enterprise": {
        "name": "Enterprise",
        "price": 10000,
        "price_display": "$100",
        "messages": TIER_LIMITS["enterprise"]["message_generation"],
        "resumes": TIER_LIMITS["enterprise"]["resume_tailor"],
        "tier": "enterprise",
    },
}

# Map Stripe Price IDs → plan keys (populated at runtime from settings)
PRICE_TO_PLAN = {}


def _init_stripe():
    """Initialize Stripe API key and price mapping."""
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
    if settings.STRIPE_PRO_PRICE_ID:
        PRICE_TO_PLAN[settings.STRIPE_PRO_PRICE_ID] = "pro"
    if settings.STRIPE_BUSINESS_PRICE_ID:
        PRICE_TO_PLAN[settings.STRIPE_BUSINESS_PRICE_ID] = "business"
    if settings.STRIPE_ENTERPRISE_PRICE_ID:
        PRICE_TO_PLAN[settings.STRIPE_ENTERPRISE_PRICE_ID] = "enterprise"


_init_stripe()


def _get_price_id(plan_key: str) -> str:
    mapping = {
        "pro": settings.STRIPE_PRO_PRICE_ID,
        "business": settings.STRIPE_BUSINESS_PRICE_ID,
        "enterprise": settings.STRIPE_ENTERPRISE_PRICE_ID,
    }
    return mapping.get(plan_key, "")


class CheckoutRequest(BaseModel):
    plan: str  # "pro", "business", "enterprise"


@router.get("/plans")
async def get_plans():
    """Return available plans with pricing and limits."""
    return {
        "plans": [
            {
                "key": key,
                "name": p["name"],
                "price": p["price"],
                "price_display": p["price_display"],
                "messages": p["messages"],
                "resumes": p["resumes"],
            }
            for key, p in PLANS.items()
        ],
        "stripe_configured": bool(settings.STRIPE_SECRET_KEY),
    }


@router.post("/create-checkout-session")
async def create_checkout_session(
    request: CheckoutRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout Session for a one-time plan purchase."""
    if request.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payments not configured yet")

    price_id = _get_price_id(request.plan)
    if not price_id:
        raise HTTPException(status_code=503, detail="Stripe price not configured for this plan")

    try:
        # Get or create Stripe customer
        if current_user.stripe_customer_id:
            customer_id = current_user.stripe_customer_id
        else:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": str(current_user.id)},
            )
            customer_id = customer.id
            current_user.stripe_customer_id = customer_id
            db.commit()

        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            client_reference_id=str(current_user.id),
            metadata={"plan": request.plan, "user_id": str(current_user.id)},
            success_url=f"{settings.FRONTEND_URL}/pricing?success=true&plan={request.plan}",
            cancel_url=f"{settings.FRONTEND_URL}/pricing?canceled=true",
        )

        return {"url": session.url}

    except stripe.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=500, detail="Payment service error")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events. No auth — verified by signature."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret not configured, skipping verification")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id")
        plan_key = session.get("metadata", {}).get("plan")

        if not user_id or not plan_key:
            logger.warning(f"Webhook missing user_id or plan: {session.get('id')}")
            return {"status": "ignored"}

        plan = PLANS.get(plan_key)
        if not plan:
            logger.warning(f"Unknown plan key in webhook: {plan_key}")
            return {"status": "ignored"}

        user = db.query(models.User).filter(models.User.id == int(user_id)).first()
        if not user:
            logger.error(f"User {user_id} not found for webhook")
            return {"status": "user_not_found"}

        user.tier = plan["tier"]
        if not user.stripe_customer_id:
            user.stripe_customer_id = session.get("customer")
        db.commit()
        logger.info(f"Upgraded user {user_id} ({user.email}) to tier={plan['tier']} via Stripe")

    return {"status": "ok"}
