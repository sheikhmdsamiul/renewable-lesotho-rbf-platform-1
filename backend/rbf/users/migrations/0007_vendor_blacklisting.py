from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_vendorprequalification_experience_financial_proof_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=[
                    ('Active', 'Active'),
                    ('Pending', 'Pending'),
                    ('Inactive', 'Inactive'),
                    ('Registered', 'Registered'),
                    ('Suspended', 'Suspended'),
                    ('Blacklisted', 'Blacklisted'),
                ],
                default='Active',
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name='VendorBlacklistCase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(choices=[('Fraudulent Reporting', 'Fraudulent Reporting'), ('Integrity Breach', 'Integrity Breach'), ('Persistent Non-Performance', 'Persistent Non-Performance'), ('External Legal Action', 'External Legal Action')], max_length=64)),
                ('description', models.TextField(blank=True)),
                ('justification_document', models.FileField(blank=True, null=True, upload_to='blacklisting/justifications/')),
                ('status', models.CharField(choices=[('Initiated', 'Initiated'), ('Under Review', 'Under Review'), ('Blacklisted', 'Blacklisted'), ('Rejected', 'Rejected'), ('Expired', 'Expired'), ('Reinstated', 'Reinstated')], default='Initiated', max_length=24)),
                ('initiated_at', models.DateTimeField(auto_now_add=True)),
                ('notice_sent_at', models.DateTimeField(blank=True, null=True)),
                ('cooling_off_until', models.DateTimeField(blank=True, null=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_notes', models.TextField(blank=True)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('final_decision_notes', models.TextField(blank=True)),
                ('is_permanent', models.BooleanField(default=False)),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('reinstated_at', models.DateTimeField(blank=True, null=True)),
                ('confirmed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='confirmed_blacklist_cases', to=settings.AUTH_USER_MODEL)),
                ('initiated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='initiated_blacklist_cases', to=settings.AUTH_USER_MODEL)),
                ('reinstated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reinstated_blacklist_cases', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_blacklist_cases', to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blacklist_cases', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-initiated_at']},
        ),
        migrations.CreateModel(
            name='BlacklistIdentifier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('organization_name', models.CharField(blank=True, max_length=255)),
                ('tax_id', models.CharField(blank=True, max_length=64)),
                ('normalized_organization_name', models.CharField(blank=True, db_index=True, max_length=255)),
                ('normalized_tax_id', models.CharField(blank=True, db_index=True, max_length=64)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('released_at', models.DateTimeField(blank=True, null=True)),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='identifiers', to='users.vendorblacklistcase')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blacklisted_identifiers', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='BlacklistAppeal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rebuttal_text', models.TextField(blank=True)),
                ('rebuttal_document', models.FileField(blank=True, null=True, upload_to='blacklisting/appeals/')),
                ('status', models.CharField(choices=[('Submitted', 'Submitted'), ('Under Review', 'Under Review'), ('Resolved', 'Resolved')], default='Submitted', max_length=24)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('resolution_notes', models.TextField(blank=True)),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='appeals', to='users.vendorblacklistcase')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_blacklist_appeals', to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blacklist_appeals', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-submitted_at']},
        ),
    ]
