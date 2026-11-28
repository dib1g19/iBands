from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0066_stripe_attempt_failures"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("processing", "Очаква потвърждение"),
                    ("paid", "Платено"),
                    ("failed", "Неуспешно плащане"),
                    ("cash_on_delivery", "Потвърден наложен платеж"),
                ],
                default="processing",
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("card", "Карта"),
                    ("cash_on_delivery", "Наложен платеж"),
                ],
                default=None,
                max_length=100,
                null=True,
            ),
        ),
    ]
