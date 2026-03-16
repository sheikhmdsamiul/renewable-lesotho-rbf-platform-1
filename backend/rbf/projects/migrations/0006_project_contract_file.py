from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_project_tender_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='contract_file',
            field=models.FileField(blank=True, null=True, upload_to='project_contracts/'),
        ),
    ]
