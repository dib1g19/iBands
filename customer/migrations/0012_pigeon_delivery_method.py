from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customer", "0011_wishlist_wishlist_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="address",
            name="delivery_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("econt_office", "Еконт офис"),
                    ("econt", "Еконт адрес"),
                    ("speedy_office", "Спиди офис"),
                    ("speedy", "Спиди адрес"),
                    ("pigeon_office", "Pigeon офис"),
                    ("pigeon_locker", "Pigeon автомат"),
                    ("pigeon", "Pigeon адрес"),
                ],
                max_length=16,
                null=True,
            ),
        ),
    ]
