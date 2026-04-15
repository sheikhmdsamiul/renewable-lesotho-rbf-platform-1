from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0027_map_query_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FieldVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("beneficiary_present", models.BooleanField(default=False)),
                ("beneficiary_gender", models.CharField(choices=[("male", "Male"), ("female", "Female"), ("other", "Other"), ("unknown", "Unknown")], default="unknown", max_length=16)),
                ("system_working", models.BooleanField(default=False)),
                ("officer_latitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("officer_longitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("location_match", models.BooleanField(default=False)),
                ("location_distance_meters", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("site_photos", models.JSONField(blank=True, default=list)),
                ("serial_visible", models.BooleanField(default=False)),
                ("observation_notes", models.CharField(blank=True, max_length=500)),
                ("verification_status", models.CharField(choices=[("verified", "Verified"), ("flagged", "Flagged"), ("partial", "Partial")], default="verified", max_length=16)),
                ("flag_reason", models.TextField(blank=True, null=True)),
                ("verified_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("field_officer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="field_verifications", to=settings.AUTH_USER_MODEL)),
                ("installation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="field_verifications", to="projects.installationreport")),
            ],
            options={
                "ordering": ["-verified_at", "-id"],
                "indexes": [
                    models.Index(fields=["installation", "verification_status"], name="projects_fie_install_26a076_idx"),
                    models.Index(fields=["field_officer", "verified_at"], name="projects_fie_field_o_06f9f6_idx"),
                ],
            },
        ),
    ]
