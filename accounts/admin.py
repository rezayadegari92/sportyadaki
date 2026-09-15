from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class SiteUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('اطلاعات تماس', {'fields': ('phone',)}),)
    list_display = ('username', 'phone', 'email', 'first_name', 'last_name', 'is_staff')
    search_fields = UserAdmin.search_fields + ('phone',)
