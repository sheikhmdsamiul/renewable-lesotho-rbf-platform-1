from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0018_user_districts'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformconfiguration',
            name='national_main_program_budget',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=16),
        ),
    ]

