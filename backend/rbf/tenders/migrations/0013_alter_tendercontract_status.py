from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0012_tender_award_workflow_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tendercontract',
            name='status',
            field=models.CharField(
                choices=[
                    ('Generated', 'Generated'),
                    ('Submitted', 'Submitted'),
                    ('Signed', 'Signed'),
                    ('Approved', 'Approved'),
                    ('Rejected', 'Rejected'),
                ],
                default='Generated',
                max_length=16,
            ),
        ),
    ]
