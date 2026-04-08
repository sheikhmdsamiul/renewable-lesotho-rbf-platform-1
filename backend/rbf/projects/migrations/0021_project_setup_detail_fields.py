from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0020_project_kpi_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="deployment_site_status",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="project",
            name="deployment_permits_status",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="project",
            name="device_brand",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="project",
            name="device_model",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="project",
            name="device_tech_tier",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="project",
            name="verification_method_confirmed",
            field=models.BooleanField(default=False),
        ),
    ]
