from decimal import Decimal

from django.db import migrations, models


def copy_terms_to_awards(apps, schema_editor):
    SpinMilestoneAward = apps.get_model("store", "SpinMilestoneAward")
    for award in SpinMilestoneAward.objects.select_related("milestone"):
        milestone = award.milestone
        award.label = milestone.label
        award.prize_type = milestone.prize_type
        award.discount_percent = milestone.discount_percent
        award.min_order_total = milestone.min_order_total
        award.save(update_fields=["label", "prize_type", "discount_percent", "min_order_total"])


def update_order_ladder(apps, schema_editor):
    SpinMilestone = apps.get_model("store", "SpinMilestone")
    SpinMilestone.objects.filter(
        counts="orders", threshold_spins=1, prize_type="free_shipping", min_order_total__isnull=True,
    ).update(min_order_total=Decimal("10.00"))
    SpinMilestone.objects.filter(
        counts="orders", label="Mini мистериозна кутия при поръчка от 25 €",
    ).update(label="Mini мистериозна кутия")


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0061_order_milestones'),
    ]

    operations = [
        migrations.AddField(
            model_name='spinmilestoneaward',
            name='discount_percent',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='spinmilestoneaward',
            name='label',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='spinmilestoneaward',
            name='min_order_total',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='spinmilestoneaward',
            name='prize_type',
            field=models.CharField(choices=[('none', 'No prize'), ('discount_percent', 'Percentage discount'), ('free_shipping', 'Free shipping'), ('mystery_box_min_total', 'Mystery box over minimum total')], default='none', max_length=32),
        ),
        migrations.RunPython(copy_terms_to_awards, migrations.RunPython.noop),
        migrations.RunPython(update_order_ladder, migrations.RunPython.noop),
    ]
