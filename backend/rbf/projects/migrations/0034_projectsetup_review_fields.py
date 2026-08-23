from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0033_paymentclaim_district'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='projectsetup',
            name='review_status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('submitted', 'Submitted (Awaiting RMT Review)'),
                    ('under_review', 'Under RMT Review'),
                    ('approved', 'Approved'),
                    ('changes_requested', 'Changes Requested'),
                    ('rejected', 'Rejected'),
                ],
                default='draft',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='projectsetup',
            name='submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='projectsetup',
            name='reviewed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='reviewed_project_setups',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='projectsetup',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='projectsetup',
            name='review_notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='projectsetup',
            name='previous_review_notes',
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(
            code=lambda apps, schema_editor: _backfill_review_status(apps, schema_editor),
            reverse_code=lambda apps, schema_editor: None,
        ),
    ]


def _backfill_review_status(apps, schema_editor):
    ProjectSetup = apps.get_model('projects', 'ProjectSetup')
    ProjectSetup.objects.filter(
        setup_completed_at__isnull=False,
    ).update(review_status='approved', submitted_at=models.F('setup_completed_at'), reviewed_at=models.F('setup_completed_at'))