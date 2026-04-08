from django.conf import settings
from django.db import migrations, models


def normalize_prospect_sync_statuses(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    InstallationReport = apps.get_model('projects', 'InstallationReport')
    ProspectSyncLog = apps.get_model('projects', 'ProspectSyncLog')

    status_map = {
        'Pending': 'pending',
        'Synced': 'success',
        'Failed': 'failed',
    }

    for model in (Project, InstallationReport):
        for old_value, new_value in status_map.items():
            model.objects.filter(prospect_sync_status=old_value).update(prospect_sync_status=new_value)

    for old_value, new_value in status_map.items():
        ProspectSyncLog.objects.filter(status=old_value).update(status=new_value)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('projects', '0024_project_assignment_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='actor_role',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='ip_address',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='module',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='new_status',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='old_status',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='record_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='record_type',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='auditlog',
            name='entity_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='auditlog',
            name='entity_type',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='prospectsynclog',
            name='record_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='prospectsynclog',
            name='record_type',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='prospectsynclog',
            name='error_message',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='prospectsynclog',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed')], default='pending', max_length=16),
        ),
        migrations.RunPython(normalize_prospect_sync_statuses, migrations.RunPython.noop),
    ]
