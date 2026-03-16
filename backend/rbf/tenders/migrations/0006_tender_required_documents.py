from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0005_tenderbid_versions_and_sites'),
    ]

    operations = [
        migrations.AddField(
            model_name='tender',
            name='trading_license_file',
            field=models.FileField(blank=True, upload_to='tender_documents/'),
        ),
        migrations.AddField(
            model_name='tender',
            name='tax_clearance_file',
            field=models.FileField(blank=True, upload_to='tender_documents/'),
        ),
        migrations.AddField(
            model_name='tender',
            name='company_registration_file',
            field=models.FileField(blank=True, upload_to='tender_documents/'),
        ),
        migrations.AddField(
            model_name='tender',
            name='experience_portfolio_file',
            field=models.FileField(blank=True, upload_to='tender_documents/'),
        ),
    ]
