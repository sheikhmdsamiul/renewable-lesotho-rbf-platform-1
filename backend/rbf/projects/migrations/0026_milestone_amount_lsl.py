from django.db import migrations, models


def backfill_amount_lsl(apps, schema_editor):
    Milestone = apps.get_model('projects', 'Milestone')
    for milestone in Milestone.objects.all().iterator():
        if milestone.amount and not milestone.amount_lsl:
            milestone.amount_lsl = milestone.amount
            milestone.save(update_fields=['amount_lsl'])


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0025_step0_foundation_logs'),
    ]

    operations = [
        migrations.AddField(
            model_name='milestone',
            name='amount_lsl',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.RunPython(backfill_amount_lsl, migrations.RunPython.noop),
    ]
