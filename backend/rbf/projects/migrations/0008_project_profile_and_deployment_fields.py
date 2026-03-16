from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0007_project_schedule_budget_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='project_title',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='project',
            name='target_installations',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='project',
            name='target_female_pct',
            field=models.PositiveIntegerField(default=50),
        ),
        migrations.AddField(
            model_name='project',
            name='target_vulnerable_pct',
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name='project',
            name='target_beneficiaries',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='project',
            name='deployment_team_roster',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='project',
            name='deployment_equipment_plan',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='project',
            name='deployment_work_schedule',
            field=models.TextField(blank=True),
        ),
    ]
