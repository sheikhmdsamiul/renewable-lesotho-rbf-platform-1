from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0020_adjust_tenderbid_final_submission_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='tender',
            name='target_districts',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
