from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


ORDER_LADDER = [
    (1, "free_shipping", None, None, "Безплатна доставка до офис"),
    (3, "discount_percent", 10, None, "10% отстъпка"),
    (5, "mystery_box_min_total", None, Decimal("25.00"), "Mini мистериозна кутия при поръчка от 25 €"),
]


def add_order_ladder(apps, schema_editor):
    SpinMilestone = apps.get_model("store", "SpinMilestone")
    for threshold, prize_type, discount, minimum, label in ORDER_LADDER:
        SpinMilestone.objects.get_or_create(
            counts="orders",
            threshold_spins=threshold,
            prize_type=prize_type,
            discount_percent=discount,
            min_order_total=minimum,
            defaults={"label": label, "active": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0060_order_status_received_label"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="spinmilestone",
            options={"ordering": ["counts", "threshold_spins", "id"], "verbose_name": "milestone"},
        ),
        migrations.AlterModelOptions(
            name="spinmilestoneaward",
            options={"ordering": ["-awarded_at"], "verbose_name": "milestone award"},
        ),
        migrations.AlterUniqueTogether(
            name="spinmilestone",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="spinmilestone",
            name="counts",
            field=models.CharField(
                choices=[("spins", "Spins"), ("orders", "Placed orders")],
                db_index=True,
                default="spins",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="spinmilestoneaward",
            name="earned_order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="earned_milestone_awards",
                to="store.order",
            ),
        ),
        migrations.AlterField(
            model_name="spinmilestone",
            name="threshold_spins",
            field=models.PositiveIntegerField(
                db_index=True,
                help_text="Award triggers when the customer reaches this many spins or placed orders.",
                verbose_name="threshold",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="spinmilestone",
            unique_together={("counts", "threshold_spins", "prize_type", "discount_percent", "min_order_total")},
        ),
        migrations.RunPython(add_order_ladder, migrations.RunPython.noop),
    ]
