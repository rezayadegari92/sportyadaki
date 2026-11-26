"""Point the homepage banner's «مشاهده لوازم اسپرت» button at the new /products/ page.

Only banners still carrying the old label and link are touched, so a button the
staff has since edited by hand is left alone.
"""
from django.db import migrations

OLD = {'primary_cta_label': 'مشاهده لوازم اسپرت', 'primary_cta_url': '/sport/'}
NEW = {'primary_cta_label': 'مشاهده لوازم', 'primary_cta_url': '/products/'}


def forwards(apps, schema_editor):
    apps.get_model('core', 'HeroBanner').objects.filter(**OLD).update(**NEW)


def backwards(apps, schema_editor):
    apps.get_model('core', 'HeroBanner').objects.filter(**NEW).update(**OLD)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_checkoutsuggestion'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
