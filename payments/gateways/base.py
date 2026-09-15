"""Interface every payment gateway integration implements.

The flow (same shape for Zarinpal, IDPay, Pay.ir, Sadad, ...):

1. request_payment()  Ask the gateway for a payment session for a Payment row;
                      return the gateway's token and the URL to send the customer to.
2. The customer pays on the gateway's page and is redirected back to our
   callback URL (payments:callback) with the token in the query string or POST body.
3. get_authority()    Read that token from the callback request.
4. verify_payment()   Confirm server-to-server that the money was received.
                      Never trust the callback's parameters on their own.

To connect a real gateway:

1. Create payments/gateways/<provider>.py with a subclass of PaymentGatewayService.
2. Read the merchant ID / API key from environment variables in __init__.
3. Set PAYMENT_GATEWAY=payments.gateways.<provider>.<ClassName> (config/settings.py).

Checkout, the callback view, stock and invoices (payments/services.py and
orders/services.py) only talk to this interface, so nothing else changes.

Amounts are in Toman, the store's currency. Most Iranian gateways expect Rial:
multiply by 10 inside the implementation.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class PaymentGatewayError(Exception):
    """The gateway couldn't be reached or refused to create the payment."""


@dataclass
class PaymentRequest:
    authority: str  # the gateway's token for this payment session
    redirect_url: str  # the gateway page to send the customer to
    raw: dict = field(default_factory=dict)  # response body, stored on Payment.raw_response


@dataclass
class PaymentVerification:
    success: bool
    reference_id: str = ''  # the gateway's reference/tracking number for a successful payment
    card_pan: str = ''  # masked card number, if the gateway returns it
    error: str = ''  # human-readable reason when success is False
    raw: dict = field(default_factory=dict)


class PaymentGatewayService(ABC):
    #: Short name stored on Payment.gateway, e.g. 'zarinpal'.
    code = ''

    @abstractmethod
    def request_payment(self, *, payment, callback_url: str, description: str, mobile: str = '') -> PaymentRequest:
        """Create a payment session for `payment` (payment.amount in Toman).

        Raise PaymentGatewayError if the session can't be created.
        """

    @abstractmethod
    def get_authority(self, request) -> str:
        """Return this gateway's payment token from the callback request ('' if absent)."""

    @abstractmethod
    def verify_payment(self, *, payment, request) -> PaymentVerification:
        """Confirm with the gateway whether `payment` was paid.

        Called once per payment. Must return success=False (not raise) when the
        customer cancelled or the gateway reports a failure.
        """
