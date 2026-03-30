from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0009_rename_tenders_ten_status_28d165_idx_tenders_ten_status_dbc4a8_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='tendercontract',
            name='annex_a_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_contracts/annexes/'),
        ),
        migrations.AddField(
            model_name='tendercontract',
            name='annex_b_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_contracts/annexes/'),
        ),
        migrations.AddField(
            model_name='tendercontract',
            name='annex_c_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_contracts/annexes/'),
        ),
        migrations.AddField(
            model_name='tendercontract',
            name='annex_d_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_contracts/annexes/'),
        ),
        migrations.AddField(
            model_name='tendercontract',
            name='annex_e_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_contracts/annexes/'),
        ),
        migrations.AddField(
            model_name='tendercontract',
            name='generated_file',
            field=models.FileField(blank=True, null=True, upload_to='tender_contracts/generated/'),
        ),
        migrations.AlterField(
            model_name='tenderbid',
            name='status',
            field=models.CharField(choices=[('Draft', 'Draft'), ('Submitted', 'Submitted'), ('Under Review', 'Under Review'), ('Awarded', 'Awarded'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected'), ('Withdrawn', 'Withdrawn')], default='Draft', max_length=32),
        ),
    ]
