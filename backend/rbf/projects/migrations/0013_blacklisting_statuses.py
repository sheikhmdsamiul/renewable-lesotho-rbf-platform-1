from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0012_milestone_tracking_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pre-Qualification', 'Pre-Qualification'),
                    ('Site-Specific Proposal', 'Site-Specific Proposal'),
                    ('Contracting', 'Contracting'),
                    ('Installation', 'Installation'),
                    ('Field Verification', 'Field Verification'),
                    ('Disbursement', 'Disbursement'),
                    ('Halted', 'Halted'),
                    ('Completed', 'Completed'),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='paymentclaim',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pending', 'Pending'),
                    ('Verified', 'Verified'),
                    ('Approved', 'Approved'),
                    ('Held/Audit', 'Held/Audit'),
                    ('Paid', 'Paid'),
                    ('Rejected', 'Rejected'),
                ],
                default='Pending',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='disbursement',
            name='status',
            field=models.CharField(
                choices=[
                    ('Initiated', 'Initiated'),
                    ('Held/Audit', 'Held/Audit'),
                    ('Completed', 'Completed'),
                    ('Failed', 'Failed'),
                ],
                default='Initiated',
                max_length=16,
            ),
        ),
    ]
