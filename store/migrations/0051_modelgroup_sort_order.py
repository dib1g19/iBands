from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0050_mystery_box_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelgroup",
            name="sort_order",
            field=models.PositiveIntegerField(default=0, db_index=True),
        ),
        migrations.AlterModelOptions(
            name="modelgroup",
            options={"ordering": ["sort_order", "name"], "verbose_name": "Model group", "verbose_name_plural": "Model groups"},
        ),
    ]


