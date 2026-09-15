"""Interface for the SMS panel.

To connect the real panel (e.g. Kavenegar, Ghasedak, SMS.ir, Melipayamak):

1. Create notifications/sms/<provider>.py with a subclass of SMSService that
   calls the provider's API in send() (and, ideally, its OTP/pattern endpoint
   in send_otp()).
2. Put the API key in an environment variable and read it in __init__.
3. Set SMS_SERVICE=notifications.sms.<provider>.<ClassName> in the environment
   (see config/settings.py).

Nothing else needs to change: order notifications (notifications/services.py)
and, later, OTP login only talk to this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SMSResult:
    success: bool
    message_id: str = ''
    error: str = ''
    raw: dict = field(default_factory=dict)


class SMSService(ABC):
    """Send text messages to Iranian mobile numbers.

    Phone numbers arrive normalized as 09xxxxxxxxx; convert to the provider's
    format (e.g. 989xxxxxxxxx) inside the implementation.

    Implementations must not raise on delivery problems (network errors, low
    credit, rejected numbers): return SMSResult(success=False, error=...).
    A failed SMS must never break an order or a payment.
    """

    @abstractmethod
    def send(self, phone: str, message: str) -> SMSResult:
        """Send a plain text message."""

    def send_otp(self, phone: str, code: str) -> SMSResult:
        """Send a one-time login code (for OTP login, once the panel is available).

        Most panels offer a dedicated "pattern"/verification endpoint that is
        faster and bypasses advertising filters; override this to use it.
        """
        return self.send(phone, f'کد ورود شما به اسپرت یدکی: {code}')
