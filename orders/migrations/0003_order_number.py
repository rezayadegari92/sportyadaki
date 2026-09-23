from django.db import migrations, models
from django.utils import timezone


def fill_numbers(apps, schema_editor):
    """Give existing orders a number, numbering each day in the order it happened."""
    Order = apps.get_model('orders', 'Order')
    per_day = {}
    for order in Order.objects.order_by('created_at', 'pk'):
        day = timezone.localtime(order.created_at).strftime('%Y%m%d')
        per_day[day] = per_day.get(day, 0) + 1
        order.number = f'ORD-{day}-{per_day[day]:04d}'
        order.save(update_fields=['number'])


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_order_cancelled_at_order_shipped_at_order_staff_note_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='number',
            field=models.CharField(default='', editable=False, max_length=30, verbose_name='شماره سفارش'),
            preserve_default=False,
        ),
        migrations.RunPython(fill_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order',
            name='number',
            field=models.CharField(editable=False, max_length=30, unique=True, verbose_name='شماره سفارش'),
        ),
    ]
