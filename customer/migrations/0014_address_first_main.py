from django.db import migrations


def mark_first_saved_main(apps, schema_editor):
    Address = apps.get_model("customer", "Address")
    from customer.models import earliest_saved_without_main

    for address in earliest_saved_without_main(Address.objects.filter(saved=True)):
        Address.objects.filter(user_id=address.user_id, is_main=True).update(is_main=False)
        Address.objects.filter(pk=address.pk).update(is_main=True)


class Migration(migrations.Migration):

    dependencies = [
        ("customer", "0013_address_saved_destination"),
    ]

    operations = [
        migrations.RunPython(mark_first_saved_main, migrations.RunPython.noop),
    ]
