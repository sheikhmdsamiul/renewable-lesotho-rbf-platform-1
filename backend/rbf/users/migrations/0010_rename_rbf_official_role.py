from django.db import migrations, models


OLD_RBF = "RBF Official"
NEW_RBF = "RBF Management Team"


def forwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role=OLD_RBF).update(role=NEW_RBF)


def backwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role=NEW_RBF).update(role=OLD_RBF)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0009_rename_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    (NEW_RBF, "RBF Management Team"),
                    ("TAC Member", "TAC Member"),
                    ("DoE Officer", "DoE Officer"),
                    ("Field Verifier", "Field Verifier"),
                    ("Vendor", "Vendor"),
                    ("Platform Administrator (Super Admin)", "Platform Administrator (Super Admin)"),
                    ("Project Steering Committee", "Project Steering Committee"),
                    ("Auditor", "Auditor"),
                ],
                default="Vendor",
                max_length=64,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
