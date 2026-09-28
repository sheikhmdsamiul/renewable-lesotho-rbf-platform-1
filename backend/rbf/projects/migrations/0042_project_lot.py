from django.db import migrations, models
import django.db.models.deletion


def backfill_project_lot(apps, schema_editor):
    # Projects created before Project carried its own lot reference are still recoverable:
    # their contract already points at the lot (or is null for single-award tenders).
    Project = apps.get_model('projects', 'Project')
    for project in Project.objects.filter(lot_id__isnull=True, contract_id__isnull=False).select_related('contract'):
        lot_id = getattr(project.contract, 'lot_id', None)
        if lot_id:
            project.lot_id = lot_id
            project.save(update_fields=['lot'])


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0041_milestone_completion_review'),
        ('tenders', '0058_intenttoawardrequest_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='lot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='projects', to='tenders.tenderlot'),
        ),
        migrations.RunPython(backfill_project_lot, migrations.RunPython.noop),
    ]
