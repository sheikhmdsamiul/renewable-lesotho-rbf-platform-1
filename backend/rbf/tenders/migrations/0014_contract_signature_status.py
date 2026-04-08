from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0013_alter_tendercontract_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='tendercontract',
            name='signature_status',
            field=models.CharField(
                choices=[('awaiting', 'awaiting'), ('uploaded', 'uploaded'), ('approved', 'approved')],
                default='awaiting',
                max_length=16,
            ),
        ),
    ]
