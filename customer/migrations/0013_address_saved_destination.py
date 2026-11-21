from django.db import migrations, models


def mark_saved_destinations(apps, schema_editor):
    Address = apps.get_model("customer", "Address")
    from customer.models import saved_destination_winners

    for winner in saved_destination_winners(Address.objects.exclude(user_id=None)):
        if not winner.saved:
            Address.objects.filter(pk=winner.pk).update(saved=True)


class Migration(migrations.Migration):

    dependencies = [
        ("customer", "0012_pigeon_delivery_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="saved",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="address",
            name="site_id",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="address",
            name="city_id",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="address",
            name="street_id",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="address",
            name="street_number",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(mark_saved_destinations, migrations.RunPython.noop),
    ]
