from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0014_contract_signature_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenderbid',
            name='boq_items',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='collection_method',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='daily_payment_amount_lsl',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='female_target_pct',
            field=models.PositiveIntegerField(default=50),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='inclusion_commitment_confirmed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='local_technicians_to_be_trained',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='low_income_target_pct',
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='offer_paygo',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='om_strategy_summary',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='paygo_platform',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='system_configuration',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='vulnerable_target_pct',
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='warranty_period_months',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tenderbidsite',
            name='estimated_energy_demand_kwh_month',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='tenderbidsite',
            name='number_of_households',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='tenderbidsite',
            name='road_access_available',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tenderbidsite',
            name='target_beneficiary_type',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='tenderbidsite',
            name='village_sub_district',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
