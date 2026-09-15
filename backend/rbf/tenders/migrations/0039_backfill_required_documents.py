# Backfill TenderRequiredDocument rows for existing tenders so they keep the
# document requirements that used to be hardcoded in TenderBidSerializer.validate()
# before those checks became fully tender-configurable. New tenders created after
# this migration start with no required documents until an RBF Admin adds some,
# matching the tender-creation form's existing "leave a stage empty to require no
# documents for it" copy.
from django.db import migrations


# (bid_stage, field_key, display name, expected_type)
EOI_DEFAULTS = [
    ('eoi', 'company_credentials_file', 'Company Credentials', 'PDF/DOCX'),
    ('eoi', 'financial_standing_file', 'Financial Standing', 'PDF/DOCX/XLSX'),
    ('eoi', 'technical_experience_file', 'Technical Experience', 'PDF/DOCX'),
    ('eoi', 'track_record_file', 'Track Record', 'PDF/DOCX'),
]
TECHNICAL_DEFAULTS = [
    ('technical', 'technical_proposal_file', 'Technical Proposal', 'PDF/DOCX'),
    ('technical', 'boq_file', 'Bill of Quantities', 'PDF/DOCX/XLSX'),
    ('technical', 'gender_action_plan_file', 'Gender Action Plan', 'PDF/DOCX/XLSX'),
    ('technical', 'implementation_plan_file', 'Implementation Plan', 'PDF/DOCX/XLSX'),
    ('technical', 'om_plan_file', 'O&M Plan', 'PDF/DOCX/XLSX'),
]
FINANCIAL_DEFAULTS = [
    ('financial', 'financial_proposal_file', 'Financial Proposal', 'PDF/DOCX/XLSX'),
]
COMBINED_DEFAULTS = [
    ('combined', 'technical_proposal_file', 'Technical Proposal', 'PDF/DOCX'),
    ('combined', 'boq_file', 'Bill of Quantities', 'PDF/DOCX/XLSX'),
    ('combined', 'gender_action_plan_file', 'Gender Action Plan', 'PDF/DOCX/XLSX'),
    ('combined', 'implementation_plan_file', 'Implementation Plan', 'PDF/DOCX/XLSX'),
    ('combined', 'om_plan_file', 'O&M Plan', 'PDF/DOCX/XLSX'),
    ('combined', 'financial_proposal_file', 'Financial Proposal', 'PDF/DOCX/XLSX'),
]
ALL_DEFAULTS = EOI_DEFAULTS + TECHNICAL_DEFAULTS + FINANCIAL_DEFAULTS + COMBINED_DEFAULTS


def backfill_required_documents(apps, schema_editor):
    Tender = apps.get_model('tenders', 'Tender')
    TenderRequiredDocument = apps.get_model('tenders', 'TenderRequiredDocument')

    for tender in Tender.objects.all():
        # Only seed the stage groups that actually apply to this tender's workflow:
        # sequential tenders never have a "combined" stage, and combined tenders never
        # have separate "technical"/"financial" stages.
        if getattr(tender, 'procurement_workflow', 'sequential') == 'combined':
            applicable_defaults = EOI_DEFAULTS + COMBINED_DEFAULTS
        else:
            applicable_defaults = EOI_DEFAULTS + TECHNICAL_DEFAULTS + FINANCIAL_DEFAULTS

        existing = TenderRequiredDocument.objects.filter(tender=tender)
        existing_by_stage_field_key = {
            (row['bid_stage'], row['field_key'])
            for row in existing.values('bid_stage', 'field_key')
        }
        next_position_by_stage = {}
        for row in existing.values('bid_stage', 'position'):
            current_max = next_position_by_stage.get(row['bid_stage'], -1)
            next_position_by_stage[row['bid_stage']] = max(current_max, row['position'])

        rows_to_create = []
        for stage, field_key, name, expected_type in applicable_defaults:
            # Skip only if this exact core document is already configured for this
            # tender+stage — any other custom documents on the same stage are left alone.
            if (stage, field_key) in existing_by_stage_field_key:
                continue
            next_position_by_stage[stage] = next_position_by_stage.get(stage, -1) + 1
            rows_to_create.append(TenderRequiredDocument(
                tender=tender,
                name=name,
                expected_type=expected_type,
                bid_stage=stage,
                field_key=field_key,
                position=next_position_by_stage[stage],
            ))
        if rows_to_create:
            TenderRequiredDocument.objects.bulk_create(rows_to_create)


def noop_reverse(apps, schema_editor):
    # Not reversible in a meaningful way — leave any backfilled rows in place.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0038_tenderrequireddocument_field_key'),
    ]

    operations = [
        migrations.RunPython(backfill_required_documents, noop_reverse),
    ]
