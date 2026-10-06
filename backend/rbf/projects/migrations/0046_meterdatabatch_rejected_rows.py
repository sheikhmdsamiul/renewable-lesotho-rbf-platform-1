from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0045_meter_data_batch_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='meterdatabatch',
            name='rejected_rows',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
