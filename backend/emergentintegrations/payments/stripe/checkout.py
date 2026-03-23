"""Stub for emergentintegrations.payments.stripe.checkout - not available in public package."""

class StripeCheckout:
    def __init__(self, api_key=None, webhook_secret=None):
        self.api_key = api_key
        self.webhook_secret = webhook_secret

    async def create_checkout_session(self, *args, **kwargs):
        raise NotImplementedError("StripeCheckout not available - payment integration not configured")

class CheckoutSessionRequest:
    def __init__(self, *args, **kwargs):
        pass
