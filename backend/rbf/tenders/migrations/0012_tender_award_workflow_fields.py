from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0011_tenderbid_reporting_templates_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='tender',
            name='cooling_off_days',
            field=models.PositiveIntegerField(default=7),
        ),
        migrations.AddField(
            model_name='tender',
            name='cooling_off_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tender',
            name='financial_weight',
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name='tender',
            name='intent_to_award_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tender',
            name='intent_to_award_bid',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='intent_awards', to='tenders.tenderbid'),
        ),
        migrations.AddField(
            model_name='tender',
            name='technical_threshold',
            field=models.PositiveIntegerField(default=70),
        ),
        migrations.AddField(
            model_name='tender',
            name='technical_weight',
            field=models.PositiveIntegerField(default=70),
        ),
    ]
