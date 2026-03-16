from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_project_contract_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='district',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='project',
            name='start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='budget',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
    ]
