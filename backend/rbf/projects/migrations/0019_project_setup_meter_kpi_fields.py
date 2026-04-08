from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0018_gis_map_support'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='setup_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='smartmeterreading',
            name='installation',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='smart_meter_readings',
                to='projects.installationreport',
            ),
        ),
        migrations.AddField(
            model_name='smartmeterreading',
            name='uptime_pct',
            field=models.FloatField(default=0),
        ),
    ]
