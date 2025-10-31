from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customer", "0010_address_face_address_post_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="wishlist",
            name="wishlist_id",
            field=models.CharField(max_length=1000, null=True, blank=True),
        ),
    ]


