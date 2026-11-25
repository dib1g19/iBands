from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0062_milestone_award_terms'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='status',
            field=models.CharField(
                choices=[('published', 'Published'), ('disabled', 'Disabled')],
                default='published',
                max_length=50,
            ),
        ),
    ]
