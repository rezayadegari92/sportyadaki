from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ProductRating, refresh_product_rating


@receiver([post_save, post_delete], sender=ProductRating)
def keep_product_rating_in_sync(sender, instance, **kwargs):
    # Signals also fire for admin bulk deletes, which skip Model.delete().
    refresh_product_rating(instance.product_id)
