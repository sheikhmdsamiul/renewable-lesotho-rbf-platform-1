"""Authenticity checks for vendor-uploaded smart meter readings.

Each check yields findings {code, severity, message, meter_id, reading_ids}. A batch with
any HIGH finding is FLAGGED: it blocks milestone claims until an RBF Official / Super
Admin verifies or rejects it. MEDIUM / LOW findings are shown to the reviewer only.
"""
import math
from collections import defaultdict
from datetime import timedelta
from statistics import median

from django.utils import timezone

from .models import (
    InstallationStatus,
    MeterDataBatchStatus,
    SmartMeterReading,
    SmartMeterReadingReviewStatus,
)

HIGH = 'high'
MEDIUM = 'medium'
LOW = 'low'

# A meter is fixed to the household; a reading captured this far from the installation
# GPS was not taken at the installation.
GPS_MISMATCH_METERS = 500
FUTURE_TOLERANCE = timedelta(hours=1)
SPIKE_MULTIPLIER = 3.0
SPIKE_MIN_HISTORY = 5
FLATLINE_MIN_READINGS = 5
CLONED_MIN_METERS = 3
# Energy over an interval cannot exceed the reported output power sustained for the
# whole interval; the margin absorbs power that varied during the interval.
ENERGY_POWER_MARGIN = 1.5

CHECK_LABELS = {
    'duplicate_reading': 'Duplicate reading',
    'future_timestamp': 'Future timestamp',
    'before_installation': 'Reading before installation date',
    'gps_mismatch': 'Reading location far from installation',
    'energy_exceeds_power': 'Energy exceeds reported output power',
    'spike': 'Unusual spike versus meter history',
    'flatline': 'Identical values repeated (possible fabricated series)',
    'cloned_values': 'Identical values across several meters',
    'uptime_energy_mismatch': 'Energy reported with 0% uptime',
    'installation_not_verified': 'Installation not yet field-verified',
}


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class _Findings:
    def __init__(self):
        self._by_key: dict[tuple[str, str], dict] = {}

    def add(self, code: str, severity: str, reading: SmartMeterReading, message: str):
        key = (code, reading.meter_id)
        finding = self._by_key.get(key)
        if finding is None:
            finding = self._by_key[key] = {
                'code': code,
                'label': CHECK_LABELS.get(code, code),
                'severity': severity,
                'meter_id': reading.meter_id,
                'message': message,
                'reading_ids': [],
            }
        if reading.id not in finding['reading_ids']:
            finding['reading_ids'].append(reading.id)
        if code not in reading.integrity_flags:
            reading.integrity_flags.append(code)

    def as_list(self) -> list[dict]:
        order = {HIGH: 0, MEDIUM: 1, LOW: 2}
        findings = list(self._by_key.values())
        for finding in findings:
            count = len(finding['reading_ids'])
            if count > 1:
                finding['message'] = f"{finding['message']} ({count} readings affected)"
        return sorted(findings, key=lambda f: (order.get(f['severity'], 9), f['code'], f['meter_id']))


def run_integrity_checks(batch, readings: list[SmartMeterReading]) -> list[dict]:
    """Checks `readings` (already saved, all in `batch`), records each reading's
    integrity_flags, and returns the batch findings."""
    findings = _Findings()
    now = timezone.now()
    meter_ids = {reading.meter_id for reading in readings}
    history = list(
        SmartMeterReading.objects.filter(
            project=batch.project,
            meter_id__in=meter_ids,
            review_status=SmartMeterReadingReviewStatus.ACCEPTED,
        )
        .exclude(batch=batch)
        .order_by('recorded_at', 'id')
        .values('meter_id', 'recorded_at', 'kwh')
    )
    history_by_meter: dict[str, list[dict]] = defaultdict(list)
    for row in history:
        history_by_meter[row['meter_id']].append(row)
    existing_timestamps = {(row['meter_id'], row['recorded_at']) for row in history}

    seen_in_file: dict[tuple[str, object], int] = {}
    batch_by_meter: dict[str, list[SmartMeterReading]] = defaultdict(list)
    for reading in sorted(readings, key=lambda r: (r.meter_id, r.recorded_at, r.id)):
        batch_by_meter[reading.meter_id].append(reading)
        key = (reading.meter_id, reading.recorded_at)
        recorded = timezone.localtime(reading.recorded_at).strftime('%Y-%m-%d %H:%M')
        if key in existing_timestamps:
            findings.add('duplicate_reading', HIGH, reading, f'Meter {reading.meter_id} already has a reading at {recorded}; the same interval was submitted again.')
        elif key in seen_in_file:
            findings.add('duplicate_reading', HIGH, reading, f'Meter {reading.meter_id} appears more than once at {recorded} in this file.')
        seen_in_file[key] = reading.id

        if reading.recorded_at > now + FUTURE_TOLERANCE:
            findings.add('future_timestamp', HIGH, reading, f'Meter {reading.meter_id} has a reading dated {recorded}, which is in the future.')

        installation = reading.installation
        if installation is not None:
            if installation.installation_date and timezone.localtime(reading.recorded_at).date() < installation.installation_date:
                findings.add(
                    'before_installation', HIGH, reading,
                    f'Meter {reading.meter_id} reported energy on {recorded}, before the installation date {installation.installation_date:%Y-%m-%d}.',
                )
            if reading.latitude is not None and reading.longitude is not None:
                distance = _haversine_m(
                    float(reading.latitude), float(reading.longitude),
                    float(installation.gps_lat), float(installation.gps_lng),
                )
                if distance > GPS_MISMATCH_METERS:
                    findings.add(
                        'gps_mismatch', HIGH, reading,
                        f'Meter {reading.meter_id} reading was captured {distance / 1000:.1f} km from the installation '
                        f'(limit {GPS_MISMATCH_METERS} m).',
                    )
            if installation.status != InstallationStatus.VERIFIED:
                findings.add(
                    'installation_not_verified', LOW, reading,
                    f'Installation for meter {reading.meter_id} is not field-verified yet, so its readings do not count toward KPIs.',
                )

        if reading.uptime_pct == 0 and reading.kwh > 0:
            findings.add('uptime_energy_mismatch', MEDIUM, reading, f'Meter {reading.meter_id} reported {reading.kwh:.2f} kWh at {recorded} with 0% uptime.')

    for meter_id, batch_readings in batch_by_meter.items():
        prior = history_by_meter.get(meter_id, [])
        prior_kwh = [float(row['kwh']) for row in prior if float(row['kwh']) > 0]
        baseline = median(prior_kwh) if len(prior_kwh) >= SPIKE_MIN_HISTORY else None
        previous_at = prior[-1]['recorded_at'] if prior else None
        for reading in batch_readings:
            if baseline and reading.kwh > baseline * SPIKE_MULTIPLIER:
                findings.add(
                    'spike', MEDIUM, reading,
                    f'Meter {meter_id} reported {reading.kwh:.2f} kWh, over {SPIKE_MULTIPLIER:.0f}x its usual {baseline:.2f} kWh.',
                )
            if reading.output_power_w and previous_at and reading.recorded_at > previous_at:
                hours = (reading.recorded_at - previous_at).total_seconds() / 3600
                max_kwh = reading.output_power_w / 1000 * hours * ENERGY_POWER_MARGIN
                if reading.kwh > max_kwh and reading.kwh > 0.1:
                    findings.add(
                        'energy_exceeds_power', MEDIUM, reading,
                        f'Meter {meter_id} reported {reading.kwh:.2f} kWh over {hours:.1f} h, more than its '
                        f'{reading.output_power_w:.0f} W output power could produce.',
                    )
            previous_at = reading.recorded_at

        series = [float(row['kwh']) for row in prior] + [reading.kwh for reading in batch_readings]
        tail = series[-FLATLINE_MIN_READINGS:]
        if len(tail) == FLATLINE_MIN_READINGS and tail[0] > 0 and all(value == tail[0] for value in tail):
            for reading in batch_readings[-FLATLINE_MIN_READINGS:]:
                findings.add(
                    'flatline', MEDIUM, reading,
                    f'Meter {meter_id} reported exactly {tail[0]:.2f} kWh in its last {FLATLINE_MIN_READINGS} readings.',
                )

    by_value: dict[tuple, list[SmartMeterReading]] = defaultdict(list)
    for reading in readings:
        if reading.kwh > 0:
            by_value[(reading.recorded_at, reading.kwh, reading.uptime_pct)].append(reading)
    for (recorded_at, kwh, _uptime), group in by_value.items():
        if len({reading.meter_id for reading in group}) >= CLONED_MIN_METERS:
            recorded = timezone.localtime(recorded_at).strftime('%Y-%m-%d %H:%M')
            for reading in group:
                findings.add(
                    'cloned_values', MEDIUM, reading,
                    f'{len(group)} different meters reported exactly {kwh:.2f} kWh at {recorded}.',
                )

    for reading in readings:
        SmartMeterReading.objects.filter(pk=reading.pk).update(integrity_flags=reading.integrity_flags)
    return findings.as_list()


def initial_batch_status(findings: list[dict]) -> str:
    if any(finding['severity'] == HIGH for finding in findings):
        return MeterDataBatchStatus.FLAGGED
    return MeterDataBatchStatus.PENDING_REVIEW
