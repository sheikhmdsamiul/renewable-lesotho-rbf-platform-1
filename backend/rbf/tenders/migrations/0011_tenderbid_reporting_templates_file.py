from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0010_contract_generation_and_annexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenderbid',
            name='reporting_templates_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_bids/'),
        ),
    ]
