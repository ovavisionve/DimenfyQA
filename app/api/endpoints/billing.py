import logging
import os
from datetime import datetime, timezone

try:
    import stripe
except ImportError:
    stripe = None  # type: ignore[assignment]
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

STRIPE_PRICES = {
    "starter": os.getenv("STRIPE_PRICE_STARTER", ""),
    "pro": os.getenv("STRIPE_PRICE_PRO", ""),
    "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", ""),
}

PLANS = {
    "starter": {
        "name": "Starter",
        "price": 49,
        "currency": "usd",
        "interval": "month",
        "dms_per_month": 500,
        "ig_accounts": 1,
        "campaigns": 3,
    },
    "pro": {
        "name": "Pro",
        "price": 99,
        "currency": "usd",
        "interval": "month",
        "dms_per_month": 2000,
        "ig_accounts": 5,
        "campaigns": "unlimited",
    },
    "enterprise": {
        "name": "Enterprise",
        "price": 249,
        "currency": "usd",
        "interval": "month",
        "dms_per_month": 10000,
        "ig_accounts": "unlimited",
        "campaigns": "unlimited",
    },
}

# In-memory subscription store (replace with DB table in production)
_subscriptions: dict[str, dict] = {}


def _ensure_stripe() -> None:
    """Raise 503 if Stripe is not configured."""
    if not STRIPE_SECRET_KEY or stripe is None:
        raise HTTPException(status_code=503, detail="Billing not configured")
    stripe.api_key = STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    plan: str  # "starter" | "pro" | "enterprise"
    client_id: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class SubscriptionUsage(BaseModel):
    dms_sent: int
    dms_limit: int


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    current_period_end: str | None = None
    usage: SubscriptionUsage


class PlanDetail(BaseModel):
    name: str
    price: int
    currency: str
    interval: str
    dms_per_month: int
    ig_accounts: int | str
    campaigns: int | str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanDetail])
async def list_plans():
    """Return available subscription plans with pricing."""
    return [PlanDetail(**plan) for plan in PLANS.values()]


@router.post("/create-checkout", response_model=CheckoutResponse)
async def create_checkout(body: CheckoutRequest):
    """Create a Stripe Checkout session for a subscription plan."""
    _ensure_stripe()

    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {body.plan}. Must be one of: {', '.join(PLANS)}")

    price_id = STRIPE_PRICES.get(body.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Stripe price not configured for plan: {body.plan}")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            metadata={"client_id": body.client_id, "plan": body.plan},
            success_url=os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/settings?billing=success"),
            cancel_url=os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/settings?billing=cancel"),
        )
    except stripe.StripeError as exc:
        logger.error("Stripe checkout creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to create checkout session") from exc

    return CheckoutResponse(checkout_url=session.url, session_id=session.id)


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events. Verifies webhook signature."""
    _ensure_stripe()

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError as exc:
        logger.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature") from exc
    except ValueError as exc:
        logger.warning("Stripe webhook payload invalid: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload") from exc

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        client_id = data_object.get("metadata", {}).get("client_id")
        plan = data_object.get("metadata", {}).get("plan")
        subscription_id = data_object.get("subscription")

        if client_id and plan:
            _subscriptions[client_id] = {
                "plan": plan,
                "status": "active",
                "stripe_subscription_id": subscription_id,
                "current_period_end": None,
                "dms_sent": 0,
            }
            logger.info("Subscription activated for client %s: plan=%s", client_id, plan)

    elif event_type == "invoice.paid":
        subscription_id = data_object.get("subscription")
        period_end = data_object.get("lines", {}).get("data", [{}])[0].get("period", {}).get("end")

        for client_id, sub in _subscriptions.items():
            if sub.get("stripe_subscription_id") == subscription_id:
                sub["status"] = "active"
                sub["dms_sent"] = 0  # Reset usage on renewal
                if period_end:
                    sub["current_period_end"] = datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
                logger.info("Invoice paid — subscription renewed for client %s", client_id)
                break

    elif event_type == "invoice.payment_failed":
        subscription_id = data_object.get("subscription")

        for client_id, sub in _subscriptions.items():
            if sub.get("stripe_subscription_id") == subscription_id:
                sub["status"] = "past_due"
                logger.warning("Payment failed for client %s", client_id)
                break

    elif event_type == "customer.subscription.deleted":
        subscription_id = data_object.get("id")

        for client_id, sub in _subscriptions.items():
            if sub.get("stripe_subscription_id") == subscription_id:
                sub["status"] = "canceled"
                logger.info("Subscription canceled for client %s", client_id)
                break

    else:
        logger.debug("Unhandled Stripe event type: %s", event_type)

    return {"status": "ok"}


@router.get("/subscription/{client_id}", response_model=SubscriptionResponse)
async def get_subscription(client_id: str):
    """Get current subscription status for a client."""
    _ensure_stripe()

    sub = _subscriptions.get(client_id)
    if not sub:
        return SubscriptionResponse(
            plan="none",
            status="inactive",
            current_period_end=None,
            usage=SubscriptionUsage(dms_sent=0, dms_limit=0),
        )

    plan_key = sub.get("plan", "starter")
    dms_limit = PLANS.get(plan_key, {}).get("dms_per_month", 0)

    return SubscriptionResponse(
        plan=plan_key,
        status=sub.get("status", "unknown"),
        current_period_end=sub.get("current_period_end"),
        usage=SubscriptionUsage(
            dms_sent=sub.get("dms_sent", 0),
            dms_limit=dms_limit,
        ),
    )
