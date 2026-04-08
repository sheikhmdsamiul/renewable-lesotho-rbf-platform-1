from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_rename_prequalification_status'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel(
                    old_name='BlacklistIdentifier',
                    new_name='BlacklistedIdentifier',
                ),
            ],
            database_operations=[],
        ),
    ]
