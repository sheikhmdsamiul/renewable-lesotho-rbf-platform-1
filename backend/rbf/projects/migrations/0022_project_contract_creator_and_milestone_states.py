from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenders", "0014_contract_signature_status"),
        ("projects", "0021_project_setup_detail_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="contract",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="projects", to="tenders.tendercontract"),
        ),
        migrations.AddField(
            model_name="project",
            name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_projects", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="milestone",
            name="disbursement_pct",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="milestone",
            name="milestone_number",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="milestone",
            name="unlocked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="project",
            name="status",
            field=models.CharField(
                choices=[
                    ("setup_pending", "Setup Pending"),
                    ("active", "Active"),
                    ("Pre-Qualification", "Pre-Qualification"),
                    ("Site-Specific Proposal", "Site-Specific Proposal"),
                    ("Contracting", "Contracting"),
                    ("Installation", "Installation"),
                    ("Field Verification", "Field Verification"),
                    ("Disbursement", "Disbursement"),
                    ("Halted", "Halted"),
                    ("Completed", "Completed"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="milestone",
            name="status",
            field=models.CharField(
                choices=[
                    ("locked", "Locked"),
                    ("claimable", "Claimable"),
                    ("claimed", "Claimed"),
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                    ("Pending", "Pending (Legacy)"),
                    ("Submitted", "Submitted (Legacy)"),
                    ("Verified", "Verified (Legacy)"),
                    ("Paid", "Paid (Legacy)"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
