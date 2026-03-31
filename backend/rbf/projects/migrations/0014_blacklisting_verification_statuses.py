from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0013_blacklisting_statuses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='installationreport',
            name='status',
            field=models.CharField(
                choices=[
                    ('Submitted', 'Submitted'),
                    ('Paused', 'Paused'),
                    ('Verified', 'Verified'),
                    ('Flagged', 'Flagged'),
                    ('Terminated', 'Terminated'),
                ],
                default='Submitted',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='verificationtask',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pending', 'Pending'),
                    ('Paused', 'Paused'),
                    ('Verified', 'Verified'),
                    ('Flagged', 'Flagged'),
                    ('Terminated', 'Terminated'),
                ],
                default='Pending',
                max_length=16,
            ),
        ),
    ]
