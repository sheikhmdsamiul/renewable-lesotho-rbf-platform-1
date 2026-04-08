from django.db import migrations, models


def normalize_legacy_duplicate_bids(apps, schema_editor):
    TenderBid = apps.get_model('tenders', 'TenderBid')

    active_statuses = ['Submitted', 'Under Review', 'Accepted', 'Awarded', 'Rejected']
    grouped_pairs = (
        TenderBid.objects.exclude(status__in=['Draft', 'Revision Required', 'Withdrawn'])
        .values('tender_id', 'vendor_id')
        .annotate(bid_count=models.Count('id'))
        .filter(bid_count__gt=1)
    )

    status_priority = {
        'Awarded': 0,
        'Accepted': 1,
        'Under Review': 2,
        'Submitted': 3,
        'Rejected': 4,
    }

    for pair in grouped_pairs.iterator():
        bids = list(
            TenderBid.objects.filter(
                tender_id=pair['tender_id'],
                vendor_id=pair['vendor_id'],
                status__in=active_statuses,
            ).order_by('-reviewed_at', '-updated_at', '-submitted_at', '-created_at', '-id')
        )
        if len(bids) < 2:
            continue

        bids.sort(
            key=lambda bid: (
                status_priority.get(bid.status, 99),
                -(bid.reviewed_at.timestamp() if bid.reviewed_at else 0),
                -(bid.updated_at.timestamp() if bid.updated_at else 0),
                -(bid.submitted_at.timestamp() if bid.submitted_at else 0),
                -(bid.created_at.timestamp() if bid.created_at else 0),
                -bid.id,
            )
        )
        keeper = bids[0]
        extras = bids[1:]

        for duplicate in extras:
            note = 'Auto-withdrawn during migration 0019 because a newer or more authoritative bid exists for this tender/vendor.'
            duplicate.status = 'Withdrawn'
            duplicate.rejection_reason = f'{duplicate.rejection_reason}\n\n{note}'.strip()
            duplicate.save(update_fields=['status', 'rejection_reason', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0018_tenderbid_om_plan_file'),
    ]

    operations = [
        migrations.RunPython(normalize_legacy_duplicate_bids, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='tenderbid',
            constraint=models.UniqueConstraint(
                condition=~models.Q(status__in=['Draft', 'Revision Required', 'Withdrawn', 'Accepted']),
                fields=('tender', 'vendor_id'),
                name='uniq_tender_vendor_final_bid',
            ),
        ),
    ]
