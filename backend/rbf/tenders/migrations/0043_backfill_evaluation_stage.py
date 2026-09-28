from django.db import migrations

TAC = 'TAC Member'
RBF_OFFICIAL = 'RBF Management Team'


def backfill_stage(apps, schema_editor):
    TenderBidEvaluation = apps.get_model('tenders', 'TenderBidEvaluation')
    User = apps.get_model('users', 'User')

    evaluator_ids = set(
        TenderBidEvaluation.objects.exclude(evaluator__isnull=True).values_list('evaluator_id', flat=True)
    )
    role_by_evaluator_id = dict(
        User.objects.filter(id__in=evaluator_ids).values_list('id', 'role')
    )

    technical_rows = []
    financial_rows = []
    for ev in TenderBidEvaluation.objects.all():
        role = role_by_evaluator_id.get(ev.evaluator_id)
        if role == TAC:
            stage = 'technical'
        elif role == RBF_OFFICIAL:
            stage = 'financial'
        else:
            # ADMIN-authored (or evaluator deleted) rows carry no role signal — infer
            # from which score fields were actually filled in at the time.
            technical_composite = (
                ev.technical_score + ev.feasibility_score + ev.om_score
                + ev.kpi_score + ev.gender_score + ev.environmental_score
            )
            stage = 'financial' if (ev.financial_score and not technical_composite) else 'technical'
        ev.stage = stage
        (financial_rows if stage == 'financial' else technical_rows).append(ev)

    if technical_rows:
        TenderBidEvaluation.objects.bulk_update(technical_rows, ['stage'])
    if financial_rows:
        TenderBidEvaluation.objects.bulk_update(financial_rows, ['stage'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0042_tenderbidevaluation_financial_score_auto_calculated_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_stage, noop_reverse),
    ]
