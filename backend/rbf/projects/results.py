"""Actual values for results-framework indicators, measured from platform records.

Each measure returns two values for a set of projects: the cumulative value up to the end of
the reporting period ("to date") and the value within the period itself. Shares are
percentages of verified installations.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db.models import Avg, Q, Sum
from django.utils import timezone

from . import claim_status
from .models import InstallationReport, InstallationStatus, PaymentClaim, ProjectStatus, ResultsMeasure as M, SmartMeterReading


def _bounds(date_from, date_to):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz) if date_from else None
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz) if date_to else None
    return start, end


def _window(qs, field, start, end):
    if start:
        qs = qs.filter(**{f'{field}__gte': start})
    if end:
        qs = qs.filter(**{f'{field}__lt': end})
    return qs


def _upto(qs, field, end):
    return qs.filter(**{f'{field}__lt': end}) if end else qs


def _share(qs, contains: str):
    total = qs.count()
    return round(qs.filter(household_type__icontains=contains).count() / total * 100.0, 1) if total else None


def measure(measure: str, projects, date_from=None, date_to=None, technology: str = ''):
    """Return (to_date, in_period) for one measure, or (None, None) when it cannot be measured."""
    if technology:
        projects = projects.filter(tech_type__iexact=technology)
    start, end = _bounds(date_from, date_to)
    verified = InstallationReport.objects.filter(project__in=projects, status=InstallationStatus.VERIFIED)
    paid_claims = PaymentClaim.objects.filter(project__in=projects, status__in=claim_status.PAID)
    readings = SmartMeterReading.objects.filter(project__in=projects)

    if measure == M.VERIFIED_INSTALLATIONS:
        return _upto(verified, 'submitted_at', end).count(), _window(verified, 'submitted_at', start, end).count()
    if measure in {M.FEMALE_HEADED_SHARE, M.VULNERABLE_SHARE, M.LOW_INCOME_SHARE}:
        key = {M.FEMALE_HEADED_SHARE: 'female', M.VULNERABLE_SHARE: 'vulnerable', M.LOW_INCOME_SHARE: 'low'}[measure]
        return _share(_upto(verified, 'submitted_at', end), key), _share(_window(verified, 'submitted_at', start, end), key)
    if measure in {M.BENEFICIARIES, M.FEMALE_BENEFICIARIES}:
        field = 'actual_beneficiaries' if measure == M.BENEFICIARIES else 'actual_female_beneficiaries'
        to_date = _upto(paid_claims, 'paid_at', end).aggregate(n=Sum(field))['n'] or 0
        in_period = _window(paid_claims, 'paid_at', start, end).aggregate(n=Sum(field))['n'] or 0
        return to_date, in_period
    if measure == M.ENERGY_KWH:
        to_date = _upto(readings, 'recorded_at', end).aggregate(n=Sum('kwh'))['n'] or 0
        in_period = _window(readings, 'recorded_at', start, end).aggregate(n=Sum('kwh'))['n'] or 0
        return round(to_date, 1), round(in_period, 1)
    if measure == M.AVERAGE_UPTIME:
        to_date = _upto(readings, 'recorded_at', end).aggregate(v=Avg('uptime_pct'))['v']
        in_period = _window(readings, 'recorded_at', start, end).aggregate(v=Avg('uptime_pct'))['v']
        return (round(to_date, 1) if to_date is not None else None), (round(in_period, 1) if in_period is not None else None)
    if measure == M.AMOUNT_DISBURSED:
        to_date = _upto(paid_claims, 'paid_at', end).aggregate(n=Sum('claim_amount'))['n'] or 0
        in_period = _window(paid_claims, 'paid_at', start, end).aggregate(n=Sum('claim_amount'))['n'] or 0
        return float(to_date), float(in_period)
    if measure == M.PROJECTS_COMPLETED:
        done = projects.filter(status__in=[ProjectStatus.COMPLETED, ProjectStatus.LEGACY_COMPLETED])
        to_date = _upto(done.filter(archived_at__isnull=False), 'archived_at', end).count() + done.filter(archived_at__isnull=True).count()
        in_period = _window(done.filter(archived_at__isnull=False), 'archived_at', start, end).count()
        return to_date, in_period
    return None, None
