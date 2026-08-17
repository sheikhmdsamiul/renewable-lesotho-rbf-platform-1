from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0022_password_reset_request_add_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformconfiguration',
            name='contact_email',
            field=models.EmailField(blank=True, default='rbf@energy.gov.ls', max_length=255),
        ),
        migrations.AddField(
            model_name='platformconfiguration',
            name='contact_phone',
            field=models.CharField(blank=True, default='+266 2231 0000', max_length=64),
        ),
        migrations.AddField(
            model_name='platformconfiguration',
            name='contact_address',
            field=models.TextField(blank=True, default='Corner Constitution & Parliament Road, Maseru 100, Lesotho'),
        ),
        migrations.AddField(
            model_name='platformconfiguration',
            name='contact_office_hours',
            field=models.CharField(blank=True, default='Mon-Fri, 08:00-17:00 SAST', max_length=128),
        ),
        migrations.AddField(
            model_name='platformconfiguration',
            name='contact_organisation_name',
            field=models.CharField(blank=True, default='RBF Management Team, Ministry of Energy', max_length=255),
        ),
    ]