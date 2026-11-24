from django.db import migrations, models


def mark_completed_orders_delivered(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    Order.objects.filter(order_status="completed").update(order_status="delivered")


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0059_pigeon_shipping_service"),
    ]

    operations = [
        migrations.RunPython(mark_completed_orders_delivered, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="order_status",
            field=models.CharField(
                choices=[
                    ("initiated", "Незавършена"),
                    ("received", "Получена"),
                    ("shipped", "Изпратена"),
                    ("delivered", "Доставена"),
                    ("canceled", "Отказана"),
                ],
                default="initiated",
                max_length=100,
            ),
        ),
    ]
