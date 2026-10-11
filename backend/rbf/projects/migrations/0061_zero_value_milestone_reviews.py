from django.db import migrations
from django.utils import timezone

ADVANCED_STATUSES = {'claimable', 'claimed', 'paid', 'Paid', 'Submitted', 'Verified'}
NOTE = (
    'Recorded automatically: this 0% milestone was skipped under the earlier rules and the '
    'project had already moved on to the next milestone.'
)


def record_proceed_for_skipped_milestones(apps, schema_editor):
    """0% milestones used to be skipped without an RMT decision. They now need a
    'proceed' decision like any other milestone, so record one wherever the project has
    already moved past such a milestone — otherwise those projects would lock up."""
    Milestone = apps.get_model('projects', 'Milestone')
    MilestoneCompletionReview = apps.get_model('projects', 'MilestoneCompletionReview')
    PaymentClaim = apps.get_model('projects', 'PaymentClaim')

    for milestone in Milestone.objects.select_related('project').exclude(status='cancelled'):
        zero_value = not (milestone.disbursement_pct or 0) or (
            not (milestone.amount or 0) and not (milestone.amount_lsl or 0)
        )
        if not zero_value or MilestoneCompletionReview.objects.filter(milestone=milestone).exists():
            continue
        later = Milestone.objects.filter(project_id=milestone.project_id, milestone_number__gt=milestone.milestone_number)
        moved_on = later.filter(status__in=ADVANCED_STATUSES).exists() or PaymentClaim.objects.filter(milestone__in=later).exists()
        if not moved_on:
            continue
        project = milestone.project
        MilestoneCompletionReview.objects.create(
            milestone=milestone,
            project=project,
            status='decided',
            decision='proceed',
            verification_notes=NOTE,
            vendor_id=project.vendor_id or '',
            vendor_name=project.vendor_name or '',
            reviewed_at=timezone.now(),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0060_findings_hold_payments'),
    ]

    operations = [
        migrations.RunPython(record_proceed_for_skipped_milestones, migrations.RunPython.noop),
    ]
