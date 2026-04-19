from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0014_user_bank_details'),
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('type', models.CharField(choices=[('Government', 'Government'), ('International', 'International'), ('NGO', 'NGO')], max_length=32)),
                ('contact_person', models.CharField(blank=True, max_length=255)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=32)),
                ('address', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='PlatformConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform_name', models.CharField(default='Renewable Lesotho RBF PLATFORM', max_length=255)),
                ('country_code', models.CharField(default='LS', max_length=8)),
                ('country_name', models.CharField(default='Lesotho', max_length=64)),
                ('default_currency', models.CharField(default='LSL', max_length=8)),
                ('timezone', models.CharField(default='Africa/Maseru', max_length=64)),
                ('female_target_minimum', models.PositiveIntegerField(default=50)),
                ('vulnerable_target_minimum', models.PositiveIntegerField(default=30)),
                ('low_income_target_minimum', models.PositiveIntegerField(default=60)),
                ('uptime_target', models.PositiveIntegerField(default=99)),
                ('anomaly_deviation_threshold', models.PositiveIntegerField(default=5)),
                ('gps_duplicate_radius_m', models.PositiveIntegerField(default=10)),
                ('gps_verification_max_distance_m', models.PositiveIntegerField(default=50)),
                ('m2_verification_required_pct', models.PositiveIntegerField(default=80)),
                ('m3_verification_required_pct', models.PositiveIntegerField(default=100)),
                ('email_notifications_enabled', models.BooleanField(default=True)),
                ('sms_notifications_enabled', models.BooleanField(default=False)),
                ('max_file_size_mb', models.PositiveIntegerField(default=10)),
                ('allowed_file_types', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Platform Configuration',
                'verbose_name_plural': 'Platform Configuration',
            },
        ),
    ]
