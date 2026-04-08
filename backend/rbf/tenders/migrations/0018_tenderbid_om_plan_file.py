from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0017_tenderbid_stage_two_unlock_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenderbid',
            name='om_plan_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_bids/'),
        ),
    ]
