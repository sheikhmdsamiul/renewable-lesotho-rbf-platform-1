from django.db import migrations, models


OLD_STATUS = "Clarification Requested"
NEW_STATUS = "Partial (Resubmit)"


def forwards(apps, schema_editor):
    VendorPrequalification = apps.get_model("users", "VendorPrequalification")
    VendorPrequalification.objects.filter(status=OLD_STATUS).update(status=NEW_STATUS)


def backwards(apps, schema_editor):
    VendorPrequalification = apps.get_model("users", "VendorPrequalification")
    VendorPrequalification.objects.filter(status=NEW_STATUS).update(status=OLD_STATUS)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0010_rename_rbf_official_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vendorprequalification",
            name="status",
            field=models.CharField(
                choices=[
                    ("Pending", "Pending"),
                    ("Under Review", "Under Review"),
                    ("Approved", "Approved"),
                    (NEW_STATUS, "Partial (Resubmit)"),
                    ("Rejected", "Rejected"),
                ],
                default="Pending",
                max_length=32,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
