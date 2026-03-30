from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0011_smart_meter_readings'),
    ]

    operations = [
        migrations.AddField(
            model_name='milestone',
            name='completed_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='milestone',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='milestone',
            name='progress_percentage',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='milestone',
            name='target_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
