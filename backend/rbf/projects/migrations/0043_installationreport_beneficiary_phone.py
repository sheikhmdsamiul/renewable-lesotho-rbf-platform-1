from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0042_project_lot'),
    ]

    operations = [
        migrations.AddField(
            model_name='installationreport',
            name='beneficiary_phone',
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
