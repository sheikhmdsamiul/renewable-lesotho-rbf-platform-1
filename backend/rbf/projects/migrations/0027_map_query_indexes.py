from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0026_milestone_amount_lsl'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='verificationtask',
            index=models.Index(fields=['status', 'report'], name='projects_ver_status_4d7f98_idx'),
        ),
    ]
