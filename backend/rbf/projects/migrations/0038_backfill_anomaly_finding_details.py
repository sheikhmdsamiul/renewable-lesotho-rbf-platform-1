from django.db import migrations


def backfill_meter_findings(apps, schema_editor):
    AnomalyFlag = apps.get_model('projects', 'AnomalyFlag')
    SmartMeterReading = apps.get_model('projects', 'SmartMeterReading')

    for flag in AnomalyFlag.objects.filter(flag_type__in={'zero_uptime', 'no_data'}):
        readings = list(
            SmartMeterReading.objects
            .filter(installation_id=flag.installation_id, created_at__lte=flag.created_at)
            .order_by('-recorded_at', '-id')[:1]
        )
        reading = readings[0] if readings else None
        meter_id = reading.meter_id if reading else 'unknown meter'
        if flag.flag_type == 'zero_uptime' and reading:
            flag.description = (
                f'Meter {meter_id} reported 0.0% uptime (zero-uptime threshold: 0%). '
                f'Reading: {float(reading.kwh):.2f} kWh, recorded {reading.recorded_at:%Y-%m-%d %H:%M %Z}, '
                f'uploaded {reading.created_at:%Y-%m-%d %H:%M %Z}. '
                f'The meter produced no usable uptime during this reporting interval.'
            )
        elif flag.flag_type == 'no_data':
            checked_at = flag.created_at
            if reading:
                hours_missing = max(0, (checked_at - reading.recorded_at).total_seconds() / 3600)
                flag.description = (
                    f'No meter reading has been received for meter {meter_id} within the 48-hour rule. '
                    f'Last reading: {float(reading.kwh):.2f} kWh, recorded {reading.recorded_at:%Y-%m-%d %H:%M %Z}, '
                    f'uploaded {reading.created_at:%Y-%m-%d %H:%M %Z}. '
                    f'At the check time {checked_at:%Y-%m-%d %H:%M %Z}, the last reading was {hours_missing:.1f} hours old.'
                )
            else:
                flag.description = (
                    f'No meter reading has been received for meter {meter_id}. '
                    f'There was no uploaded reading at the {checked_at:%Y-%m-%d %H:%M %Z} check time; '
                    f'the expected reporting window is 48 hours.'
                )
        else:
            continue
        flag.save(update_fields=['description'])


class Migration(migrations.Migration):
    dependencies = [
        ('projects', '0037_backfill_output_deviation_details'),
    ]

    operations = [
        migrations.RunPython(backfill_meter_findings, migrations.RunPython.noop),
    ]
