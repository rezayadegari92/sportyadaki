import logging

from .base import SMSResult, SMSService

logger = logging.getLogger('notifications.sms')


class ConsoleSMSService(SMSService):
    """Placeholder until the SMS panel is available: messages are written to
    the log instead of being sent. `outbox` keeps them in memory so tests can
    check what would have been sent."""

    outbox = []

    def send(self, phone, message):
        self.outbox.append((phone, message))
        logger.info('SMS (not sent, placeholder) to %s: %s', phone, message)
        return SMSResult(success=True, message_id=f'console-{len(self.outbox)}')
