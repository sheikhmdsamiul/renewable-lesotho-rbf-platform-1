from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_add_last_viewed_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='districts',
            field=models.JSONField(blank=True, default=list),
        ),
    ]