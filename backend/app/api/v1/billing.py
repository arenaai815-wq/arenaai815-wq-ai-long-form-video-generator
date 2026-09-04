"""Plans, subscription and Stripe-ready checkout/webhooks.

When STRIPE_SECRET_KEY is unset the API runs in *manual* mode: plan changes apply
immediately (useful for development and self-hosted deployments). With Stripe
configured, checkout sessions are created and the webhook keeps `subscriptions`
in sync - the rest of the platform only ever reads the local Subscription row.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Header, Request, status

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.models.billing import PLAN_CATALOG, Subscription
from app.models.enums import CreditTransactionKind, PlanTier, SubscriptionStatus
from app.models.user import User
from app.schemas.billing import ChangePlanRequest, CheckoutRequest, CheckoutResponse, CreditPurchaseRequest, PlanPublic, SubscriptionPublic
from app.schemas.common import Message
from app.services.billing_service import add_credits, apply_plan, ensure_subscription

router = APIRouter()
log = get_logger(__name__)

STRIPE_API = "https://api.stripe.com/v1"


def _stripe_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def _price_for(plan: PlanTier) -> str | None:
    return {PlanTier.CREATOR: settings.stripe_price_creator, PlanTier.PRO: settings.stripe_price_pro, PlanTier.STUDIO: settings.stripe_price_studio}.get(plan)


@router.get("/plans", response_model=list[PlanPublic])
async def list_plans(user: CurrentUser, db: DB) -> list[PlanPublic]:
    sub = await ensure_subscription(db, user)
    return [PlanPublic(id=pid, **{k: v for k, v in cat.items()}, is_current=(sub.plan.value == pid)) for pid, cat in PLAN_CATALOG.items()]


@router.get("/subscription", response_model=SubscriptionPublic)
async def get_subscription(user: CurrentUser, db: DB) -> Subscription:
    return await ensure_subscription(db, user)


@router.post("/subscription/change", response_model=SubscriptionPublic, summary="Change plan (manual mode) or get redirected to checkout (Stripe mode)")
async def change_plan(body: ChangePlanRequest, user: CurrentUser, db: DB) -> Subscription:
    sub = await ensure_subscription(db, user)
    if body.plan == sub.plan:
        return sub
    if _stripe_enabled() and body.plan != PlanTier.FREE:
        raise ValidationError("Use /billing/checkout to upgrade when Stripe is enabled", details={"checkout": True})
    old_credits = sub.monthly_credits
    apply_plan(sub, body.plan)
    sub.status = SubscriptionStatus.ACTIVE
    sub.payment_provider = None if body.plan == PlanTier.FREE else "manual"
    sub.current_period_start = datetime.now(UTC)
    sub.current_period_end = datetime.now(UTC) + timedelta(days=30)
    sub.cancel_at_period_end = False
    delta = sub.monthly_credits - old_credits
    if delta > 0:
        await add_credits(db, user, delta, CreditTransactionKind.GRANT, description=f"Upgrade to {PLAN_CATALOG[body.plan.value]['name']}", reference=f"upgrade:{user.id}:{body.plan.value}:{int(time.time())}")
    return sub


@router.post("/subscription/cancel", response_model=SubscriptionPublic)
async def cancel_subscription(user: CurrentUser, db: DB) -> Subscription:
    sub = await ensure_subscription(db, user)
    if sub.plan == PlanTier.FREE:
        raise ValidationError("You are on the free plan")
    if _stripe_enabled() and sub.external_subscription_id:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{STRIPE_API}/subscriptions/{sub.external_subscription_id}", auth=(settings.stripe_secret_key, ""), data={"cancel_at_period_end": "true"})
            if r.status_code >= 400:
                raise ValidationError("Stripe rejected the cancellation", details={"stripe": r.text[:300]})
    sub.cancel_at_period_end = True
    return sub


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(body: CheckoutRequest, user: CurrentUser, db: DB) -> CheckoutResponse:
    sub = await ensure_subscription(db, user)
    if not _stripe_enabled():
        return CheckoutResponse(checkout_url=None, mode="manual", message="Payments are not configured. Plan changes are applied instantly via /billing/subscription/change.")
    price = _price_for(body.plan)
    if not price:
        raise ValidationError(f"No Stripe price configured for plan {body.plan.value}")
    success = body.success_url or f"{settings.frontend_url}/billing?checkout=success"
    cancel = body.cancel_url or f"{settings.frontend_url}/billing?checkout=cancel"
    data = {
        "mode": "subscription",
        "success_url": success,
        "cancel_url": cancel,
        "line_items[0][price]": price,
        "line_items[0][quantity]": "1",
        "client_reference_id": str(user.id),
        "customer_email": user.email,
        "metadata[user_id]": str(user.id),
        "metadata[plan]": body.plan.value,
        "subscription_data[metadata][user_id]": str(user.id),
        "subscription_data[metadata][plan]": body.plan.value,
    }
    if sub.external_customer_id:
        data["customer"] = sub.external_customer_id
        data.pop("customer_email")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{STRIPE_API}/checkout/sessions", auth=(settings.stripe_secret_key, ""), data=data)
    if r.status_code >= 400:
        log.error("stripe checkout failed", body=r.text[:500])
        raise ValidationError("Could not start checkout", details={"stripe": r.text[:300]})
    return CheckoutResponse(checkout_url=r.json()["url"], mode="stripe", message="Redirect the user to checkout_url")


@router.post("/credits/purchase", response_model=CheckoutResponse, summary="Buy extra credits (manual mode grants instantly)")
async def purchase_credits(body: CreditPurchaseRequest, user: CurrentUser, db: DB) -> CheckoutResponse:
    if _stripe_enabled():
        if not settings.stripe_price_credits:
            raise ValidationError("Credit top-ups are not configured in Stripe")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{STRIPE_API}/checkout/sessions", auth=(settings.stripe_secret_key, ""),
                data={"mode": "payment", "success_url": f"{settings.frontend_url}/billing?credits=success", "cancel_url": f"{settings.frontend_url}/billing?credits=cancel", "line_items[0][price]": settings.stripe_price_credits, "line_items[0][quantity]": str(body.credits // 100), "client_reference_id": str(user.id), "metadata[user_id]": str(user.id), "metadata[credits]": str(body.credits)},
            )
        if r.status_code >= 400:
            raise ValidationError("Could not start checkout", details={"stripe": r.text[:300]})
        return CheckoutResponse(checkout_url=r.json()["url"], mode="stripe", message="Redirect the user to checkout_url")
    if settings.is_production:
        raise ValidationError("Credit purchases require a payment provider in production")
    await add_credits(db, user, body.credits, CreditTransactionKind.PURCHASE, description="Development credit top-up", reference=f"devtopup:{user.id}:{int(time.time())}")
    return CheckoutResponse(checkout_url=None, mode="manual", message=f"Granted {body.credits} credits (development mode)")


# --- Stripe webhook ----------------------------------------------------------------------


def _verify_stripe_signature(payload: bytes, header: str | None, secret: str, tolerance: int = 300) -> bool:
    if not header:
        return False
    parts = dict(kv.split("=", 1) for kv in header.split(",") if "=" in kv)
    ts, sig = parts.get("t"), parts.get("v1")
    if not ts or not sig:
        return False
    if abs(time.time() - int(ts)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK, include_in_schema=True, summary="Stripe webhook receiver")
async def stripe_webhook(request: Request, db: DB, stripe_signature: str | None = Header(default=None, alias="Stripe-Signature")) -> dict:
    payload = await request.body()
    if not settings.stripe_webhook_secret or not _verify_stripe_signature(payload, stripe_signature, settings.stripe_webhook_secret):
        raise ValidationError("Invalid Stripe signature")
    event = json.loads(payload)
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    meta = obj.get("metadata") or {}
    user_id = meta.get("user_id") or obj.get("client_reference_id")
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        log.warning("stripe event without resolvable user", type=etype)
        return {"received": True}
    sub = await ensure_subscription(db, user)

    if etype == "checkout.session.completed":
        sub.external_customer_id = obj.get("customer") or sub.external_customer_id
        if obj.get("mode") == "subscription":
            sub.external_subscription_id = obj.get("subscription")
            plan = PlanTier(meta.get("plan", sub.plan.value))
            apply_plan(sub, plan)
            sub.status = SubscriptionStatus.ACTIVE
            sub.payment_provider = "stripe"
            sub.current_period_start = datetime.now(UTC)
            sub.current_period_end = datetime.now(UTC) + timedelta(days=30)
            await add_credits(db, user, sub.monthly_credits, CreditTransactionKind.SUBSCRIPTION_RENEWAL, description=f"{PLAN_CATALOG[plan.value]['name']} plan activated", reference=f"stripe:{event.get('id')}")
        elif obj.get("mode") == "payment" and meta.get("credits"):
            await add_credits(db, user, int(meta["credits"]), CreditTransactionKind.PURCHASE, description="Credit top-up", reference=f"stripe:{event.get('id')}")
    elif etype == "invoice.paid" and obj.get("billing_reason") == "subscription_cycle":
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_start = datetime.fromtimestamp(obj.get("period_start", time.time()), UTC)
        sub.current_period_end = datetime.fromtimestamp(obj.get("period_end", time.time() + 30 * 86400), UTC)
        await add_credits(db, user, sub.monthly_credits, CreditTransactionKind.SUBSCRIPTION_RENEWAL, description="Monthly credits", reference=f"stripe:{event.get('id')}")
    elif etype == "invoice.payment_failed":
        sub.status = SubscriptionStatus.PAST_DUE
    elif etype == "customer.subscription.deleted":
        apply_plan(sub, PlanTier.FREE)
        sub.status = SubscriptionStatus.CANCELED
        sub.external_subscription_id = None
        sub.cancel_at_period_end = False
    elif etype == "customer.subscription.updated":
        sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        st = obj.get("status")
        if st in {s.value for s in SubscriptionStatus}:
            sub.status = SubscriptionStatus(st)
    return {"received": True}


@router.get("/portal", response_model=Message, summary="Stripe customer portal link")
async def billing_portal(user: CurrentUser, db: DB) -> Message:
    sub = await ensure_subscription(db, user)
    if not _stripe_enabled() or not sub.external_customer_id:
        return Message(message=f"{settings.frontend_url}/billing")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{STRIPE_API}/billing_portal/sessions", auth=(settings.stripe_secret_key, ""), data={"customer": sub.external_customer_id, "return_url": f"{settings.frontend_url}/billing"})
    if r.status_code >= 400:
        raise ValidationError("Could not open billing portal")
    return Message(message=r.json()["url"])
