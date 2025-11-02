from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0049_spinmilestone_spinprize_spinmilestoneaward_spinentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_mystery_box",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="cart",
            name="note",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="cart",
            name="mystery_device_models",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="note",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="mystery_device_models",
            field=models.JSONField(blank=True, null=True),
        ),
    ]


