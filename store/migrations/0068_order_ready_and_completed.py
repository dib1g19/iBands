from django.db import migrations, models


def mark_delivered_orders_completed(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    Order.objects.filter(order_status="delivered").update(order_status="completed")


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0067_order_payment_labels"),
    ]

    operations = [
        migrations.RunPython(mark_delivered_orders_completed, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="order_status",
            field=models.CharField(
                choices=[
                    ("initiated", "Незавършена"),
                    ("received", "Получена"),
                    ("shipped", "Изпратена"),
                    ("ready", "Готова за взимане"),
                    ("completed", "Завършена"),
                    ("canceled", "Отказана"),
                ],
                default="initiated",
                max_length=100,
            ),
        ),
    ]
