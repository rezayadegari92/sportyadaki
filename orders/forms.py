from django import forms


class CheckoutForm(forms.Form):
    address = forms.ModelChoiceField(
        label='ارسال به', queryset=None, widget=forms.RadioSelect, empty_label=None,
        error_messages={'required': 'لطفاً آدرس ارسال را انتخاب کنید.'},
    )
    note = forms.CharField(
        label='توضیحات سفارش (اختیاری)', required=False, max_length=500,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'مثلاً زمان مناسب تحویل'}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        addresses = user.addresses.all()
        self.fields['address'].queryset = addresses
        default = next((address for address in addresses if address.is_default), None)
        if default:
            self.fields['address'].initial = default.pk


class TrackOrderForm(forms.Form):
    order_number = forms.CharField(
        label='شماره سفارش', max_length=20,
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'off', 'placeholder': 'مثلاً ۱۲۴۵'}),
    )
    phone = forms.CharField(
        label='شماره موبایل', max_length=20,
        widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'tel', 'placeholder': '۰۹۱۲۳۴۵۶۷۸۹'}),
    )
