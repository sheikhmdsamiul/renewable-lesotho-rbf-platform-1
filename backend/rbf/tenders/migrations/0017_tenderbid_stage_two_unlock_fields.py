from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0016_tender_bid_submission_schema'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenderbid',
            name='stage_two_source_bid',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stage_two_drafts', to='tenders.tenderbid'),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='stage_two_unlocked',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tenderbid',
            name='stage_two_unlocked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
