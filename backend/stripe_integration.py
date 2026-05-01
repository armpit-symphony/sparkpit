"""
Coherent Stripe integration used by FastAPI payment routes.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import stripe
from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    mode: str = "payment"
    amount: Optional[float] = None
    currency: Optional[str] = None
    price_id: Optional[str] = None
    product_name: str = "TheSparkPit Membership"
    success_url: str
    cancel_url: str
    customer_email: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
    payment_intent_data: Optional[Dict[str, Any]] = None


class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str
    status: Optional[str] = None


class CheckoutStatusResponse(BaseModel):
    session_id: str
    status: Optional[str] = None
    payment_status: Optional[str] = None
    amount_total: Optional[int] = None
    currency: Optional[str] = None
    customer_id: Optional[str] = None
    metadata: Dict[str, str] = {}


class WebhookEventResult(BaseModel):
    event_id: str
    event_type: str
    session_id: Optional[str] = None
    payment_status: Optional[str] = None
    metadata: Dict[str, str] = {}


class StripeCheckout:
    def __init__(
        self,
        api_key: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        stripe.api_key = api_key
        self.webhook_secret = webhook_secret
        self.webhook_url = webhook_url

    @staticmethod
    def _build_line_items(request: CheckoutSessionRequest) -> list:
        if request.price_id:
            return [{"price": request.price_id, "quantity": 1}]

        if request.amount is None or not request.currency:
            raise ValueError("Either price_id or amount/currency is required")

        return [
            {
                "price_data": {
                    "currency": request.currency,
                    "unit_amount": int(round(request.amount * 100)),
                    "product_data": {"name": request.product_name},
                },
                "quantity": 1,
            }
        ]

    async def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResponse:
        def _create() -> CheckoutSessionResponse:
            session_data: Dict[str, Any] = {
                "mode": request.mode,
                "line_items": self._build_line_items(request),
                "success_url": request.success_url,
                "cancel_url": request.cancel_url,
            }

            if request.customer_email:
                session_data["customer_email"] = request.customer_email
            if request.metadata:
                session_data["metadata"] = request.metadata
            if request.payment_intent_data:
                session_data["payment_intent_data"] = request.payment_intent_data

            session = stripe.checkout.Session.create(**session_data)
            return CheckoutSessionResponse(
                session_id=session.id,
                url=session.url,
                status=getattr(session, "status", None),
            )

        return await asyncio.to_thread(_create)

    async def get_checkout_session(self, session_id: str) -> CheckoutStatusResponse:
        def _get() -> CheckoutStatusResponse:
            session = stripe.checkout.Session.retrieve(session_id)
            return CheckoutStatusResponse(
                session_id=session.id,
                status=getattr(session, "status", None),
                payment_status=getattr(session, "payment_status", None),
                amount_total=getattr(session, "amount_total", None),
                currency=getattr(session, "currency", None),
                customer_id=getattr(session, "customer", None),
                metadata=dict(getattr(session, "metadata", {}) or {}),
            )

        return await asyncio.to_thread(_get)

    async def get_checkout_status(self, session_id: str) -> CheckoutStatusResponse:
        return await self.get_checkout_session(session_id)

    async def handle_webhook(self, payload: bytes, signature: Optional[str]) -> WebhookEventResult:
        def _handle() -> WebhookEventResult:
            event = stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
            data_object = getattr(event.data, "object", None)
            session_id = getattr(data_object, "id", None)
            payment_status = getattr(data_object, "payment_status", None)
            metadata = dict(getattr(data_object, "metadata", {}) or {})
            return WebhookEventResult(
                event_id=event.id,
                event_type=event.type,
                session_id=session_id,
                payment_status=payment_status,
                metadata=metadata,
            )

        return await asyncio.to_thread(_handle)

    async def test_connection(
        self,
        membership_price_id: Optional[str] = None,
        bot_invite_price_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _test() -> Dict[str, Any]:
            account = stripe.Account.retrieve()
            result = {
                "ok": True,
                "account_id": account.id,
                "livemode": bool(getattr(account, "livemode", False)),
                "membership_price_ok": None,
                "bot_invite_price_ok": None,
                "message": "Stripe connection successful.",
            }
            if membership_price_id:
                price = stripe.Price.retrieve(membership_price_id)
                result["membership_price_ok"] = bool(getattr(price, "active", True))
            if bot_invite_price_id:
                price = stripe.Price.retrieve(bot_invite_price_id)
                result["bot_invite_price_ok"] = bool(getattr(price, "active", True))
            return result

        return await asyncio.to_thread(_test)
