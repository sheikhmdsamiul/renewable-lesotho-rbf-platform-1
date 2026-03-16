from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0004_auditlog_paymentclaim_disbursement'),
        ('tenders', '0007_rename_tenders_ten_tender__9fe2b6_idx_tenders_ten_tender__ac55cb_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='tender',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='projects', to='tenders.tender'),
        ),
        migrations.AddField(
            model_name='project',
            name='project_reference',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='project',
            name='milestone_plan_id',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
