from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_project_setup(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    ProjectSetup = apps.get_model('projects', 'ProjectSetup')
    User = apps.get_model('users', 'User')

    for project in Project.objects.all().iterator():
        vendor_identifier = str(project.vendor_id or '').strip()
        if not vendor_identifier:
            continue
        vendor = User.objects.filter(id=vendor_identifier).first()
        if vendor is None:
            vendor = User.objects.filter(username=vendor_identifier).first()
        if vendor is None and project.vendor_name:
            vendor = User.objects.filter(username=project.vendor_name).first()
        if vendor is None:
            continue
        site_status_raw = str(project.deployment_site_status or '').strip().lower()
        if site_status_raw in {'ready', 'completed', 'complete'}:
            site_status = 'ready'
        elif site_status_raw in {'in progress', 'in_progress', 'ongoing'}:
            site_status = 'in_progress'
        else:
            site_status = 'not_started'
        ProjectSetup.objects.update_or_create(
            project_id=project.id,
            defaults={
                'vendor_id': vendor.id,
                'site_status': site_status,
                'device_model': project.device_model or '',
                'device_brand': project.device_brand or '',
                'tech_tier': int(project.device_tech_tier) if str(project.device_tech_tier or '').isdigit() else None,
                'manual_verification_confirmed': bool(project.verification_method_confirmed),
                'setup_completed_at': project.setup_completed_at,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('projects', '0022_project_contract_creator_and_milestone_states'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectSetup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_roster_file', models.FileField(blank=True, null=True, upload_to='project_setup/team_rosters/')),
                ('equipment_plan_file', models.FileField(blank=True, null=True, upload_to='project_setup/equipment_plans/')),
                ('site_status', models.CharField(choices=[('ready', 'Ready'), ('in_progress', 'In Progress'), ('not_started', 'Not Started')], default='not_started', max_length=24)),
                ('work_schedule_start', models.DateField(blank=True, null=True)),
                ('work_schedule_end', models.DateField(blank=True, null=True)),
                ('compliance_docs_file', models.FileField(blank=True, null=True, upload_to='project_setup/compliance_docs/')),
                ('insurance_certificate_file', models.FileField(blank=True, null=True, upload_to='project_setup/insurance/')),
                ('device_model', models.CharField(blank=True, max_length=255)),
                ('device_brand', models.CharField(blank=True, max_length=255)),
                ('tech_tier', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('meter_api_endpoint', models.URLField(blank=True)),
                ('meter_api_token_encrypted', models.TextField(blank=True)),
                ('manual_verification_confirmed', models.BooleanField(default=False)),
                ('checklist_team_ready', models.BooleanField(default=False)),
                ('checklist_equipment_ready', models.BooleanField(default=False)),
                ('checklist_site_ready', models.BooleanField(default=False)),
                ('checklist_safety_ready', models.BooleanField(default=False)),
                ('checklist_logistics_ready', models.BooleanField(default=False)),
                ('setup_completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='project_setup', to='projects.project')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_setups', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.RunPython(backfill_project_setup, migrations.RunPython.noop),
    ]
