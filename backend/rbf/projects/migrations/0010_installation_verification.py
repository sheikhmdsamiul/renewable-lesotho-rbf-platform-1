from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ('projects', '0009_project_updates_documents'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstallationReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gps_lat', models.DecimalField(decimal_places=6, max_digits=9)),
                ('gps_lng', models.DecimalField(decimal_places=6, max_digits=9)),
                ('serial_number', models.CharField(max_length=128)),
                ('beneficiary_id', models.CharField(max_length=128)),
                ('receipt_file', models.FileField(blank=True, null=True, upload_to='installation_receipts/')),
                ('photo_files', models.JSONField(blank=True, default=list)),
                ('meter_id', models.CharField(blank=True, max_length=64)),
                ('kwh_reading', models.FloatField(default=0)),
                ('status', models.CharField(choices=[('Submitted', 'Submitted'), ('Verified', 'Verified'), ('Flagged', 'Flagged')], default='Submitted', max_length=16)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('milestone', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='installation_reports', to='projects.milestone')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='installation_reports', to='projects.project')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='installation_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-submitted_at'],
            },
        ),
        migrations.CreateModel(
            name='VerificationTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_lat', models.DecimalField(decimal_places=6, max_digits=9)),
                ('vendor_lng', models.DecimalField(decimal_places=6, max_digits=9)),
                ('verifier_lat', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('verifier_lng', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('distance_meters', models.FloatField(blank=True, null=True)),
                ('anomaly_flag', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('Pending', 'Pending'), ('Verified', 'Verified'), ('Flagged', 'Flagged')], default='Pending', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_verifier', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verification_tasks', to=settings.AUTH_USER_MODEL)),
                ('report', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='verification_task', to='projects.installationreport')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
