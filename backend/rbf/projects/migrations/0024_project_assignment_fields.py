from decimal import Decimal

from django.db import migrations, models
from django.utils import timezone


def backfill_project_assignment_fields(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    technology_map = {
        'shs': 'SHS',
        'solar home system': 'SHS',
        'solar home systems': 'SHS',
        'ics': 'ICS',
        'improved cookstove': 'ICS',
        'improved cookstoves': 'ICS',
        'gmg': 'GMG',
        'mini-grid': 'GMG',
        'mini grid': 'GMG',
        'mini-grids': 'GMG',
        'mini grids': 'GMG',
        'swp': 'SWP',
        'solar water pump': 'SWP',
        'solar water pumps': 'SWP',
        'pue': 'PUE',
        'productive use': 'PUE',
        'productive use equipment': 'PUE',
    }

    for project in Project.objects.all().iterator():
        changed = []

        if not project.created_at:
            project.created_at = timezone.now()
            changed.append('created_at')
        if not project.updated_at:
            project.updated_at = timezone.now()
            changed.append('updated_at')

        if not project.installation_target and project.target_installations:
            project.installation_target = project.target_installations
            changed.append('installation_target')
        if not project.female_target_pct and project.target_female_pct:
            project.female_target_pct = project.target_female_pct
            changed.append('female_target_pct')
        if not project.vulnerable_target_pct and project.target_vulnerable_pct:
            project.vulnerable_target_pct = project.target_vulnerable_pct
            changed.append('vulnerable_target_pct')

        if project.low_income_target_pct == 60 and project.target_low_income_pct:
            project.low_income_target_pct = project.target_low_income_pct
            changed.append('low_income_target_pct')
        elif not project.target_low_income_pct:
            project.target_low_income_pct = project.low_income_target_pct or 60
            changed.append('target_low_income_pct')

        legacy_technology = str(project.technology_type or project.tech_type or '').strip()
        normalized_technology = technology_map.get(legacy_technology.lower(), '')
        if normalized_technology and project.technology_type != normalized_technology:
            project.technology_type = normalized_technology
            changed.append('technology_type')
        if not project.district_zone and project.district:
            project.district_zone = project.district
            changed.append('district_zone')
        if not project.energy_output_target_kwh and project.energy_output:
            project.energy_output_target_kwh = Decimal(str(project.energy_output))
            changed.append('energy_output_target_kwh')

        verification_method = str(project.verification_method or '').strip().lower()
        normalized_verification_method = 'iot' if verification_method == 'iot' else 'manual'
        if project.verification_method != normalized_verification_method:
            project.verification_method = normalized_verification_method
            changed.append('verification_method')

        if project.status == 'Completed':
            project.status = 'completed'
            changed.append('status')

        if changed:
            project.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0023_projectsetup_workspace'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='district_zone',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='project',
            name='energy_output_target_kwh',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name='project',
            name='female_target_pct',
            field=models.PositiveIntegerField(default=50),
        ),
        migrations.AddField(
            model_name='project',
            name='installation_target',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='project',
            name='low_income_target_pct',
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AddField(
            model_name='project',
            name='technology_type',
            field=models.CharField(blank=True, choices=[('SHS', 'SHS'), ('ICS', 'ICS'), ('GMG', 'GMG'), ('SWP', 'SWP'), ('PUE', 'PUE')], default='', max_length=8),
        ),
        migrations.AddField(
            model_name='project',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='vulnerable_target_pct',
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.RunPython(backfill_project_assignment_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='project',
            name='status',
            field=models.CharField(choices=[('setup_pending', 'Setup Pending'), ('active', 'Active'), ('Pre-Qualification', 'Pre-Qualification'), ('Site-Specific Proposal', 'Site-Specific Proposal'), ('Contracting', 'Contracting'), ('Installation', 'Installation'), ('Field Verification', 'Field Verification'), ('Disbursement', 'Disbursement'), ('Halted', 'Halted'), ('completed', 'Completed'), ('Completed', 'Completed (Legacy)')], max_length=32),
        ),
        migrations.AlterField(
            model_name='project',
            name='target_low_income_pct',
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AlterField(
            model_name='project',
            name='verification_method',
            field=models.CharField(choices=[('iot', 'IoT'), ('manual', 'Manual')], default='manual', max_length=16),
        ),
    ]
