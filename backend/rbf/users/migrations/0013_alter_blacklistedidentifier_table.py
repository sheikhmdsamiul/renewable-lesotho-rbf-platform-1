from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_rename_blacklistidentifier_model'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterModelTable(
                    name='blacklistedidentifier',
                    table='users_blacklistidentifier',
                ),
            ],
            database_operations=[],
        ),
    ]
