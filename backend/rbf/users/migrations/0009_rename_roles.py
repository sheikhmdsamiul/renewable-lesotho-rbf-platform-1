from django.db import migrations, models


OLD_ADMIN = "Digital Admin"
NEW_ADMIN = "Platform Administrator (Super Admin)"
OLD_STEERING = "UNDP & Donors"
NEW_STEERING = "Project Steering Committee"


def forwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role=OLD_ADMIN).update(role=NEW_ADMIN)
    User.objects.filter(role=OLD_STEERING).update(role=NEW_STEERING)


def backwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role=NEW_ADMIN).update(role=OLD_ADMIN)
    User.objects.filter(role=NEW_STEERING).update(role=OLD_STEERING)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0008_blacklist_associated_entities"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("RBF Official", "RBF Official"),
                    ("TAC Member", "TAC Member"),
                    ("DoE Officer", "DoE Officer"),
                    ("Field Verifier", "Field Verifier"),
                    ("Vendor", "Vendor"),
                    (NEW_ADMIN, "Platform Administrator (Super Admin)"),
                    (NEW_STEERING, "Project Steering Committee"),
                    ("Auditor", "Auditor"),
                ],
                default="Vendor",
                max_length=64,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
