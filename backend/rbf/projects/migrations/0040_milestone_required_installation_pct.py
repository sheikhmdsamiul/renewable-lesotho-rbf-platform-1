from django.db import migrations, models


def backfill_required_installation_pct(apps, schema_editor):
    # Existing projects were created with the fixed 80% (M2) / 100% (M3) rule.
    Milestone = apps.get_model('projects', 'Milestone')
    Milestone.objects.filter(milestone_number=2, required_installation_pct=0).update(required_installation_pct=80)
    Milestone.objects.filter(milestone_number=3, required_installation_pct=0).update(required_installation_pct=100)


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0039_anomalyevidencefile_anomalyreviewevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='milestone',
            name='required_installation_pct',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_required_installation_pct, migrations.RunPython.noop),
    ]
