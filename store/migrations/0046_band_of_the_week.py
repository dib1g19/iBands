from django.db import migrations, models
import datetime


def migrate_daily_to_weekly(apps, schema_editor):
    BandOfTheDay = apps.get_model('store', 'BandOfTheDay')
    BandOfTheWeek = apps.get_model('store', 'BandOfTheWeek')
    db_alias = schema_editor.connection.alias

    try:
        daily_qs = BandOfTheDay.objects.using(db_alias).all().order_by('date')
    except Exception:
        daily_qs = []

    seen_weeks = set()
    for d in daily_qs:
        # Compute Monday as week start
        try:
            weekday = d.date.weekday()  # 0=Mon ... 6=Sun
            week_start = d.date - datetime.timedelta(days=weekday)
        except Exception:
            week_start = d.date
        key = (week_start,)
        if key in seen_weeks:
            # Skip duplicates; keep the earliest encountered for that week
            continue
        seen_weeks.add(key)
        BandOfTheWeek.objects.using(db_alias).get_or_create(
            week_start=week_start,
            defaults={"product_id": getattr(d, "product_id", None)},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0045_product_h1_override'),
    ]

    operations = [
        migrations.CreateModel(
            name='BandOfTheWeek',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_start', models.DateField(db_index=True, unique=True, help_text='May be any date in the week; it will auto-normalize to Monday.')),
                ('product', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='weekly_deals', to='store.product')),
            ],
            options={
                'verbose_name': 'Band of the Week',
                'verbose_name_plural': 'Band of the Week',
                'ordering': ['-week_start'],
            },
        ),
        migrations.RunPython(migrate_daily_to_weekly, migrations.RunPython.noop),
        migrations.DeleteModel(
            name='BandOfTheDay',
        ),
    ]


