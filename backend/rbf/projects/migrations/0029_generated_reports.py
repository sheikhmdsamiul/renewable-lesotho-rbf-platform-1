from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0028_fieldverification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GeneratedReport",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("report_type", models.CharField(max_length=128)),
                ("format", models.CharField(choices=[("csv", "CSV"), ("pdf", "PDF"), ("excel", "Excel")], max_length=16)),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("scope_label", models.CharField(blank=True, max_length=255)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                ("file", models.FileField(upload_to="generated-reports/%Y/%m/%d/")),
                ("generated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generated_reports", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generated_reports", to="projects.project")),
            ],
            options={
                "ordering": ["-generated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="generatedreport",
            index=models.Index(fields=["report_type", "generated_at"], name="projects_ge_report__4b2ff2_idx"),
        ),
        migrations.AddIndex(
            model_name="generatedreport",
            index=models.Index(fields=["generated_by", "generated_at"], name="projects_ge_generat_2bb9b3_idx"),
        ),
    ]

