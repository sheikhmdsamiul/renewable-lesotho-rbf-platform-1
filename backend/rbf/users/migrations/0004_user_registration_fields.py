from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_vendorprequalification'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='mobile_number',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='user',
            name='national_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='user',
            name='address',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='user',
            name='registration_certificate_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='user',
            name='tax_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='user',
            name='device_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='user',
            name='tier_assignment',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='user',
            name='verification_zone',
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
