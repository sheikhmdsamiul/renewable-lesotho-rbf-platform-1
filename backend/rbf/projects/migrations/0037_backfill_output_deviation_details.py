from django.db import migrations


def backfill_output_deviation_details(apps, schema_editor):
    AnomalyFlag = apps.get_model('projects', 'AnomalyFlag')
    SmartMeterReading = apps.get_model('projects', 'SmartMeterReading')

    for flag in AnomalyFlag.objects.filter(flag_type='output_deviation'):
        readings = list(
            SmartMeterReading.objects
            .filter(installation_id=flag.installation_id, created_at__lte=flag.created_at)
            .order_by('-recorded_at', '-id')[:2]
        )
        if len(readings) < 2:
            continue
        current, previous = readings[0], readings[1]
        if not previous.kwh:
            continue
        signed_change = (float(current.kwh) - float(previous.kwh)) / float(previous.kwh) * 100.0
        flag.description = (
            f'Meter {current.meter_id} changed by {signed_change:+.1f}% (review threshold: >5%). '
            f'Current reading: {float(current.kwh):.2f} kWh, recorded {current.recorded_at:%Y-%m-%d %H:%M %Z}, '
            f'uploaded {current.created_at:%Y-%m-%d %H:%M %Z}. '
            f'Compared with: {float(previous.kwh):.2f} kWh, recorded {previous.recorded_at:%Y-%m-%d %H:%M %Z}, '
            f'uploaded {previous.created_at:%Y-%m-%d %H:%M %Z}.'
        )
        flag.save(update_fields=['description'])


class Migration(migrations.Migration):
    dependencies = [
        ('projects', '0036_anomaly_review_workflow'),
    ]

    operations = [
        migrations.RunPython(backfill_output_deviation_details, migrations.RunPython.noop),
    ]
