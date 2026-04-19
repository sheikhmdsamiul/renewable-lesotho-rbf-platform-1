from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_organization_platformconfiguration'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprequalification',
            name='bank_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='vendorprequalification',
            name='bank_branch',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='vendorprequalification',
            name='bank_swift_code',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='vendorprequalification',
            name='bank_sort_code',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
