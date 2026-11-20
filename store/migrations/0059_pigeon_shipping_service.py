from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0058_staff_update"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="shipping_service",
            field=models.CharField(
                blank=True,
                choices=[
                    ("econt", "Еконт"),
                    ("speedy", "Спиди"),
                    ("pigeon", "Pigeon Express"),
                ],
                default=None,
                max_length=100,
                null=True,
            ),
        ),
    ]
