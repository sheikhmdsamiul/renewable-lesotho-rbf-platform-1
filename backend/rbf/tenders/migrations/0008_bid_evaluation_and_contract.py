from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0007_rename_tenders_ten_tender__9fe2b6_idx_tenders_ten_tender__ac55cb_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TenderBidEvaluation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('Pending', 'Pending'), ('Scored', 'Scored')], default='Pending', max_length=16)),
                ('technical_score', models.PositiveIntegerField(default=0)),
                ('financial_score', models.PositiveIntegerField(default=0)),
                ('feasibility_score', models.PositiveIntegerField(default=0)),
                ('kpi_score', models.PositiveIntegerField(default=0)),
                ('gender_score', models.PositiveIntegerField(default=0)),
                ('environmental_score', models.PositiveIntegerField(default=0)),
                ('om_score', models.PositiveIntegerField(default=0)),
                ('inclusivity_score', models.PositiveIntegerField(default=0)),
                ('total_score', models.PositiveIntegerField(default=0)),
                ('comments', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bid', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evaluations', to='tenders.tenderbid')),
                ('evaluator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TenderContract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_id', models.CharField(max_length=64)),
                ('vendor_name', models.CharField(max_length=255)),
                ('vendor_email', models.EmailField(blank=True, max_length=254)),
                ('reference_number', models.CharField(max_length=64, unique=True)),
                ('template_name', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[('Generated', 'Generated'), ('Signed', 'Signed'), ('Approved', 'Approved'), ('Rejected', 'Rejected')], default='Generated', max_length=16)),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('signed_file', models.FileField(blank=True, null=True, upload_to='tender_contracts/')),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('approved_by', models.CharField(blank=True, max_length=255)),
                ('rejection_reason', models.TextField(blank=True)),
                ('milestone_plan_id', models.CharField(blank=True, max_length=64)),
                ('project_id', models.CharField(blank=True, max_length=64)),
                ('bid', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='contracts', to='tenders.tenderbid')),
                ('tender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contracts', to='tenders.tender')),
            ],
            options={
                'ordering': ['-generated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='tenderbidevaluation',
            index=models.Index(fields=['status'], name='tenders_ten_status_28d165_idx'),
        ),
        migrations.AddIndex(
            model_name='tenderbidevaluation',
            index=models.Index(fields=['bid'], name='tenders_ten_bid_id_79a08d_idx'),
        ),
        migrations.AddIndex(
            model_name='tendercontract',
            index=models.Index(fields=['status'], name='tenders_ten_status_5686e8_idx'),
        ),
        migrations.AddIndex(
            model_name='tendercontract',
            index=models.Index(fields=['tender', 'vendor_id'], name='tenders_ten_tender__a3a2b2_idx'),
        ),
    ]
