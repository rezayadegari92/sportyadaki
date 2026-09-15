from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Project user model, defined up front so fields can be added later without
    swapping AUTH_USER_MODEL on a live database."""

    phone = models.CharField('موبایل', max_length=20, blank=True, db_index=True)
    wp_user_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)
