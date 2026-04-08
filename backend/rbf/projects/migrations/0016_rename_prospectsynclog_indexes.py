from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0015_prospect_sync_tracking'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='prospectsynclog',
            old_name='projects_pro_method__8b7102_idx',
            new_name='projects_pr_method__2741b0_idx',
        ),
        migrations.RenameIndex(
            model_name='prospectsynclog',
            old_name='projects_pro_status_7c9c56_idx',
            new_name='projects_pr_status_00264d_idx',
        ),
    ]
