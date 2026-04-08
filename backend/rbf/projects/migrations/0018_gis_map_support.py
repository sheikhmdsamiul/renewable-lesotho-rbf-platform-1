from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0017_project_legacy_fields_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='installationreport',
            name='beneficiary_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='gis_status',
            field=models.CharField(
                choices=[('green', 'green'), ('yellow', 'yellow'), ('red', 'red')],
                default='yellow',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='household_type',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='installation_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='verificationtask',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pending', 'Pending'),
                    ('Paused', 'Paused'),
                    ('Partial', 'Partial'),
                    ('Verified', 'Verified'),
                    ('Flagged', 'Flagged'),
                    ('Terminated', 'Terminated'),
                ],
                default='Pending',
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name='AnomalyFlag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('flag_type', models.CharField(max_length=64)),
                ('description', models.TextField(blank=True)),
                ('is_resolved', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('installation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='anomaly_flags', to='projects.installationreport')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='anomaly_flags', to='projects.project')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='installationreport',
            index=models.Index(fields=['gps_lat', 'gps_lng'], name='projects_ins_gps_lat_95a4c6_idx'),
        ),
        migrations.AddIndex(
            model_name='installationreport',
            index=models.Index(fields=['project', 'status'], name='projects_ins_project_9fe959_idx'),
        ),
        migrations.AddIndex(
            model_name='installationreport',
            index=models.Index(fields=['gis_status'], name='projects_ins_gis_sta_32f31d_idx'),
        ),
        migrations.AddIndex(
            model_name='installationreport',
            index=models.Index(fields=['vendor', 'project'], name='projects_ins_vendor__50708e_idx'),
        ),
        migrations.AddIndex(
            model_name='anomalyflag',
            index=models.Index(fields=['installation', 'is_resolved'], name='projects_ano_install_3c0f09_idx'),
        ),
        migrations.AddIndex(
            model_name='anomalyflag',
            index=models.Index(fields=['project', 'flag_type'], name='projects_ano_project_1b0424_idx'),
        ),
    ]
