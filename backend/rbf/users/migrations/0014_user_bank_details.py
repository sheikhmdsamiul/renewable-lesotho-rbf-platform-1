from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_alter_blacklistedidentifier_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='bank_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='user',
            name='bank_branch',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='user',
            name='bank_swift_code',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='user',
            name='bank_sort_code',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
