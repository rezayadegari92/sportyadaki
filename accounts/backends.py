from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from core.text import normalize_iran_mobile


class PhoneBackend(ModelBackend):
    """Sign in with mobile number + password.

    The login form's field is still named `username`; it accepts a phone typed
    in any format (Persian digits, +98...). Staff can still use their username
    through Django's ModelBackend, listed after this one.

    When the SMS panel is available, OTP login can be added as another backend
    (e.g. authenticate(request, phone=..., otp=...)) without touching this one.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        phone = normalize_iran_mobile(username)
        if len(phone) != 11 or password is None:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            User().set_password(password)  # same hashing cost as a real attempt (timing)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
