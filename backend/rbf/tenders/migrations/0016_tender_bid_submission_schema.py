from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0015_tender_bid_structured_form'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenderbid',
            name='boq_details',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='device_brand_model',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='distribution_map_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_bids/'),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='energy_target_kwh_month',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='subsidy_requested',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='tech_tier',
            field=models.CharField(blank=True, max_length=16),
        ),
    ]
