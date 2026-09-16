from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Address, User


class AddressInline(admin.StackedInline):
    model = Address
    extra = 0
    fields = (('title', 'is_default'), ('recipient_name', 'recipient_phone'), ('province', 'city', 'postal_code'), 'street', ('plaque', 'unit'))


@admin.register(User)
class SiteUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('اطلاعات تماس', {'fields': ('phone',)}),)
    list_display = ('username', 'phone', 'first_name', 'last_name', 'is_staff', 'date_joined')
    search_fields = UserAdmin.search_fields + ('phone',)
    inlines = [AddressInline]
