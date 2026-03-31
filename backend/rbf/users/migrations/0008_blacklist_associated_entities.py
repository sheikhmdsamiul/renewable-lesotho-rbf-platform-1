from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_vendor_blacklisting'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='associated_entities',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='blacklistidentifier',
            name='associated_entities',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='blacklistidentifier',
            name='national_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='blacklistidentifier',
            name='normalized_associated_entities',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='blacklistidentifier',
            name='normalized_national_id',
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
    ]
