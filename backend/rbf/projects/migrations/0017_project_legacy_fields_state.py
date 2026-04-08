from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0016_rename_prospectsynclog_indexes'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='project',
                    name='installation_target_summary',
                    field=models.CharField(blank=True, default='', max_length=255),
                ),
                migrations.AddField(
                    model_name='project',
                    name='project_duration_months',
                    field=models.PositiveIntegerField(default=0),
                ),
                migrations.AddField(
                    model_name='project',
                    name='target_low_income_pct',
                    field=models.PositiveIntegerField(default=0),
                ),
                migrations.AddField(
                    model_name='project',
                    name='verification_method',
                    field=models.CharField(blank=True, default='', max_length=255),
                ),
            ],
            database_operations=[],
        ),
    ]
