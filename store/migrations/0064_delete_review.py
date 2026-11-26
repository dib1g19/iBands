from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0063_category_status"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Review",
        ),
    ]
