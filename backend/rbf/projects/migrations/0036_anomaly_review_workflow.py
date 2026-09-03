from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('projects', '0035_alter_project_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='anomalyflag',
            name='status',
            field=models.CharField(choices=[('open', 'Open'), ('under_investigation', 'Under Investigation'), ('correction_requested', 'Correction Requested'), ('awaiting_evidence', 'Awaiting Evidence'), ('resolved', 'Resolved'), ('false_positive', 'False Positive'), ('escalated', 'Escalated'), ('reopened', 'Reopened')], default='open', max_length=32),
        ),
        migrations.AddField(
            model_name='anomalyflag',
            name='severity',
            field=models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='medium', max_length=16),
        ),
        migrations.AddField(
            model_name='anomalyflag',
            name='assigned_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_anomaly_flags', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(model_name='anomalyflag', name='investigation_notes', field=models.TextField(blank=True)),
        migrations.AddField(model_name='anomalyflag', name='corrective_action', field=models.TextField(blank=True)),
        migrations.AddField(model_name='anomalyflag', name='resolution_reason', field=models.TextField(blank=True)),
        migrations.AddField(model_name='anomalyflag', name='evidence_reference', field=models.TextField(blank=True)),
        migrations.AddField(model_name='anomalyflag', name='due_date', field=models.DateField(blank=True, null=True)),
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model('projects', 'AnomalyFlag').objects.filter(is_resolved=True).update(status='resolved'),
            migrations.RunPython.noop,
        ),
    ]
