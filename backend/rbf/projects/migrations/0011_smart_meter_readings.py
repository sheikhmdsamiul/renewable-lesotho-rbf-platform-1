from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('projects', '0010_installation_verification'),
    ]

    operations = [
        migrations.CreateModel(
            name='SmartMeterReading',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('meter_id', models.CharField(max_length=64)),
                ('kwh', models.FloatField(default=0)),
                ('recorded_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='smart_meter_readings', to='projects.project')),
            ],
            options={
                'ordering': ['-recorded_at'],
            },
        ),
    ]
