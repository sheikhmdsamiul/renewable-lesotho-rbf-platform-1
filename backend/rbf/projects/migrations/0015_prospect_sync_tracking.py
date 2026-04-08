from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0014_blacklisting_verification_statuses'),
    ]

    operations = [
        migrations.AddField(
            model_name='installationreport',
            name='prospect_sync_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='prospect_sync_status',
            field=models.CharField(choices=[('Pending', 'Pending'), ('Synced', 'Synced'), ('Failed', 'Failed')], default='Pending', max_length=16),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='prospect_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='prospect_sync_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='project',
            name='prospect_sync_status',
            field=models.CharField(choices=[('Pending', 'Pending'), ('Synced', 'Synced'), ('Failed', 'Failed')], default='Pending', max_length=16),
        ),
        migrations.AddField(
            model_name='project',
            name='prospect_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ProspectSyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('method_name', models.CharField(max_length=128)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('Pending', 'Pending'), ('Synced', 'Synced'), ('Failed', 'Failed')], default='Pending', max_length=16)),
                ('error_message', models.TextField(blank=True)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='prospectsynclog',
            index=models.Index(fields=['method_name'], name='projects_pro_method__8b7102_idx'),
        ),
        migrations.AddIndex(
            model_name='prospectsynclog',
            index=models.Index(fields=['status'], name='projects_pro_status_7c9c56_idx'),
        ),
    ]
