from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenders', '0019_tenderbid_single_final_submission'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='tenderbid',
            name='uniq_tender_vendor_final_bid',
        ),
        migrations.AddConstraint(
            model_name='tenderbid',
            constraint=models.UniqueConstraint(
                condition=~models.Q(status__in=['Draft', 'Revision Required', 'Withdrawn', 'Accepted']),
                fields=('tender', 'vendor_id'),
                name='uniq_tender_vendor_final_bid',
            ),
        ),
    ]
