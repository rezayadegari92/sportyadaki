import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from core.text import normalize_iran_mobile, to_ascii_digits

from .models import Address

User = get_user_model()
MOBILE_PATTERN = re.compile(r'09\d{9}')


def clean_mobile(value):
    phone = normalize_iran_mobile(value)
    if not MOBILE_PATTERN.fullmatch(phone):
        raise ValidationError('شماره موبایل معتبر نیست؛ مثلاً ۰۹۱۲۳۴۵۶۷۸۹')
    return phone


def tel_input(**attrs):
    return forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'tel', 'dir': 'ltr', 'placeholder': '۰۹۱۲۳۴۵۶۷۸۹', **attrs})


class RegisterForm(forms.ModelForm):
    """Sign-up with mobile number, name and password. When OTP login arrives,
    the phone can be verified by SMS before this form is shown."""

    phone = forms.CharField(label='شماره موبایل', max_length=20, widget=tel_input())
    password1 = forms.CharField(
        label='رمز عبور', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='حداقل ۸ کاراکتر؛ فقط عدد یا مشابه اطلاعات شما نباشد.',
    )
    password2 = forms.CharField(
        label='تکرار رمز عبور', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        labels = {'first_name': 'نام', 'last_name': 'نام خانوادگی'}
        widgets = {
            'first_name': forms.TextInput(attrs={'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={'autocomplete': 'family-name'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.order_fields(['phone', 'first_name', 'last_name', 'password1', 'password2'])

    def clean_phone(self):
        phone = clean_mobile(self.cleaned_data['phone'])
        if User.objects.filter(phone=phone).exists() or User.objects.filter(username=phone).exists():
            raise ValidationError('با این شماره قبلاً ثبت‌نام شده است؛ لطفاً وارد شوید.')
        return phone

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get('password1'), cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'رمزهای عبور یکسان نیستند.')
        if password1:
            candidate = User(
                username=cleaned.get('phone', ''), phone=cleaned.get('phone', ''),
                first_name=cleaned.get('first_name', ''), last_name=cleaned.get('last_name', ''),
            )
            try:
                validate_password(password1, user=candidate)
            except ValidationError as error:
                self.add_error('password1', error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.phone = user.username = self.cleaned_data['phone']
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='شماره موبایل', max_length=20, widget=tel_input(autofocus=True))
    password = forms.CharField(
        label='رمز عبور', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'شماره موبایل یا رمز عبور اشتباه است.',
    }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        labels = {'first_name': 'نام', 'last_name': 'نام خانوادگی'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            'title', 'recipient_name', 'recipient_phone', 'province', 'city',
            'street', 'plaque', 'unit', 'postal_code', 'is_default',
        ]
        widgets = {
            'recipient_phone': tel_input(),
            'street': forms.Textarea(attrs={'rows': 2, 'autocomplete': 'street-address'}),
            'postal_code': forms.TextInput(attrs={'inputmode': 'numeric', 'dir': 'ltr', 'autocomplete': 'postal-code'}),
            'plaque': forms.TextInput(attrs={'inputmode': 'numeric'}),
            'unit': forms.TextInput(attrs={'inputmode': 'numeric'}),
        }

    def clean_recipient_phone(self):
        return clean_mobile(self.cleaned_data['recipient_phone'])

    def clean_postal_code(self):
        postal_code = re.sub(r'\D', '', to_ascii_digits(self.cleaned_data['postal_code']))
        if len(postal_code) != 10:
            raise ValidationError('کد پستی باید ۱۰ رقم باشد.')
        return postal_code
