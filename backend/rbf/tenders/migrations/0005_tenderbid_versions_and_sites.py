from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0004_tenderbid_alter_tender_options_tender_closed_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenderbid',
            name='version_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='tenderbid',
            name='status',
            field=models.CharField(choices=[('Draft', 'Draft'), ('Submitted', 'Submitted'), ('Under Review', 'Under Review'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected'), ('Withdrawn', 'Withdrawn')], default='Draft', max_length=32),
        ),
        migrations.AlterUniqueTogether(
            name='tenderbid',
            unique_together={('tender', 'vendor_id', 'version_number')},
        ),
        migrations.AddIndex(
            model_name='tenderbid',
            index=models.Index(fields=['tender', 'vendor_id', 'version_number'], name='tenders_ten_tender__9fe2b6_idx'),
        ),
        migrations.CreateModel(
            name='TenderBidSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('site_name', models.CharField(max_length=255)),
                ('district', models.CharField(blank=True, max_length=128)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('system_configuration', models.JSONField(blank=True, default=dict)),
                ('boq_items', models.JSONField(blank=True, default=list)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('bid', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sites', to='tenders.tenderbid')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.AddIndex(
            model_name='tenderbidsite',
            index=models.Index(fields=['bid'], name='tenders_ten_bid_9b8a74_idx'),
        ),
    ]
