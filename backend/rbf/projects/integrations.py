import hashlib
import json
import logging
import time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone as dt_timezone
from typing import Any
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import InstallationReport, InstallationStatus, Project, ProspectSyncLog, ProspectSyncStatus, SmartMeterReading
from rbf.users.models import User


logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='prospect-sync')


class ProspectServiceError(Exception):
    pass


class ProspectAuthException(ProspectServiceError):
    pass


class ProspectClientException(ProspectServiceError):
    pass


class ProspectServerException(ProspectServiceError):
    pass


class ProspectConnectionException(ProspectServiceError):
    pass


def _hash_value(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def normalize_prospect_gender(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in {'male', 'm'}:
        return 'M'
    if normalized in {'female', 'f'}:
        return 'F'
    if normalized in {'other', 'o', 'non-binary', 'nonbinary'}:
        return 'O'
    return ''


def derive_installation_gender(household_type: Any) -> str:
    return 'F' if str(household_type or '').strip().lower() == 'female_headed' else 'M'


def normalize_project_technology(value: Any) -> str:
    raw = str(value or '').strip().upper()
    normalized = ' '.join(raw.replace('_', ' ').replace('/', ' ').split())
    mapping = {
        'SOLAR HOME SYSTEM': 'SHS',
        'IMPROVED COOKSTOVE': 'ICS',
        'MINI-GRID': 'GMG',
        'MINI GRID': 'GMG',
        'SOLAR MINI-GRID': 'GMG',
        'SOLAR MINI GRID': 'GMG',
        'SOLAR WATER PUMP': 'SWP',
        'PRODUCTIVE USE': 'PUE',
    }
    return mapping.get(normalized, raw)


def build_project_target_payload(project: Project) -> dict[str, Any]:
    reporting_phase = f'PRJ-{project.id}'
    effective_date = project.start_date or timezone.localdate()
    program_end_date = project.end_date or (effective_date + timedelta(days=365))
    base_fields = {
        'country': 'LS',
        'reporting_phase': reporting_phase,
        'program': 'RBF Lesotho',
        'effective_date': effective_date.isoformat(),
        'program_end_date': program_end_date.isoformat(),
    }
    return {
        'data': [
            {
                **base_fields,
                'metric': 'installation_target',
                'target_value': int(project.installation_target),
                'unit_of_measurement': 'number',
            },
            {
                **base_fields,
                'metric': 'female_beneficiary_target',
                'target_value': int(project.female_target_pct or 50),
                'unit_of_measurement': 'percentage',
            },
            {
                **base_fields,
                'metric': 'monthly_energy_output_kwh',
                'target_value': float(project.energy_output_target_kwh),
                'unit_of_measurement': 'kWh',
            },
        ]
    }


class ProspectService:
    DEVICE_CATEGORY_MAP = {
        'SHS': 'solar_home_system',
        'ICS': 'electric_stove',
        'GMG': 'meter',
        'SWP': 'water_pump',
        'PUE': 'other_production_use',
    }
    WRITE_ENDPOINTS = {
        'pushAgent': '/v1/in/agents',
        'pushCustomer': '/v1/in/customers',
        'pushInstallation': '/v1/in/installations',
        'pushInstallationTimeSeries': '/v1/in/installations_ts',
        'pushTarget': '/v1/in/targets',
        'pushReport': '/v1/in/reports',
    }
    READ_ENDPOINTS = {
        'getInstallations': '/v1/out/installations',
        'getTargets': '/v1/out/targets',
    }
    READ_TOKENS = {
        'getInstallations': 'PROSPECT_TOKEN_OUT_INSTALLATIONS',
        'getTargets': 'PROSPECT_TOKEN_OUT_TARGETS',
    }
    WRITE_TOKENS = {
        'pushAgent': 'PROSPECT_TOKEN_IN_AGENTS',
        'pushCustomer': 'PROSPECT_TOKEN_IN_CUSTOMERS',
        'pushInstallation': 'PROSPECT_TOKEN_IN_INSTALLATIONS',
        'pushInstallationTimeSeries': 'PROSPECT_TOKEN_IN_INSTALLATIONS_TS',
        'pushTarget': 'PROSPECT_TOKEN_IN_TARGETS',
        'pushReport': 'PROSPECT_TOKEN_IN_REPORTS',
    }

    def __init__(
        self,
        *,
        base_url: str,
        read_token: str,
        write_token: str,
        write_tokens: dict[str, str] | None = None,
        read_tokens: dict[str, str] | None = None,
        timeout: int = 30,
        batch_size: int = 10000,
    ):
        self.base_url = base_url.rstrip('/')
        self.read_token = str(read_token or '').strip()
        self.write_token = str(write_token or '').strip()
        self.write_tokens = {
            method_name: str(token or '').strip()
            for method_name, token in (write_tokens or {}).items()
        }
        self.read_tokens = {
            method_name: str(token or '').strip()
            for method_name, token in (read_tokens or {}).items()
        }
        self.timeout = timeout
        self.batch_size = batch_size

    @classmethod
    def from_settings(cls) -> 'ProspectService':
        return cls(
            base_url=getattr(settings, 'PROSPECT_BASE_URL', ''),
            read_token=getattr(settings, 'PROSPECT_READ_TOKEN', ''),
            write_token=getattr(settings, 'PROSPECT_WRITE_TOKEN', ''),
            write_tokens={
                method_name: getattr(settings, setting_name, '')
                for method_name, setting_name in cls.WRITE_TOKENS.items()
            },
            read_tokens={
                method_name: getattr(settings, setting_name, '')
                for method_name, setting_name in cls.READ_TOKENS.items()
            },
            timeout=getattr(settings, 'PROSPECT_TIMEOUT_SECONDS', 30),
            batch_size=getattr(settings, 'PROSPECT_BATCH_SIZE', 10000),
        )

    def _headers(self, token: str) -> dict[str, str]:
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

    def _ensure_configured(self):
        if not self.base_url:
            raise ProspectServiceError('Prospect integration is not configured.')

    def _token_for_write(self, method_name: str) -> str:
        token = self.write_tokens.get(method_name) or self.write_token
        if not token:
            setting_name = self.WRITE_TOKENS.get(method_name, 'PROSPECT_WRITE_TOKEN')
            raise ProspectServiceError(
                f'Prospect write token is not configured for {method_name}. '
                f'Expected {setting_name} or PROSPECT_WRITE_TOKEN.'
            )
        return token

    def _token_for_read(self, method_name: str) -> str:
        token = self.read_tokens.get(method_name) or self.read_token
        if not token:
            setting_name = self.READ_TOKENS.get(method_name, 'PROSPECT_READ_TOKEN')
            raise ProspectServiceError(
                f'Prospect read token is not configured for {method_name}. '
                f'Expected {setting_name} or PROSPECT_READ_TOKEN.'
            )
        return token

    def _request(self, method: str, endpoint: str, *, payload: dict[str, Any] | None = None, query: dict[str, Any] | None = None, token: str) -> dict[str, Any]:
        self._ensure_configured()
        url = f'{self.base_url}{endpoint}'
        if query:
            url = f'{url}?{urlencode(query)}'
        sanitized_payload = sanitize_for_json(payload)
        data = None if sanitized_payload is None else json.dumps(sanitized_payload).encode('utf-8')
        request = Request(url, data=data, headers=self._headers(token), method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode('utf-8').strip()
                parsed = json.loads(raw) if raw else {}
                parsed['_status_code'] = response.status
                return parsed
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='ignore').strip()
            detail = body or exc.reason
            if exc.code == 401:
                logger.error('Prospect auth failed: %s %s -> %s', method, endpoint, detail)
                raise ProspectAuthException(detail) from exc
            if 400 <= exc.code < 500:
                logger.error('Prospect 4xx: %s %s payload=%s response=%s', method, endpoint, payload, detail)
                raise ProspectClientException(detail) from exc
            logger.error('Prospect 5xx: %s %s payload=%s response=%s', method, endpoint, payload, detail)
            raise ProspectServerException(detail) from exc
        except (URLError, SocketTimeout, TimeoutError) as exc:
            logger.error('Prospect network error: %s %s payload=%s error=%s', method, endpoint, payload, exc)
            raise ProspectConnectionException(f'Prospect network error: {exc}') from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception('Unexpected Prospect error: %s %s payload=%s', method, endpoint, payload)
            raise ProspectConnectionException(str(exc)) from exc

    def _post_records(self, method_name: str, endpoint: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        self._ensure_configured()
        token = self._token_for_write(method_name)
        responses: list[dict[str, Any]] = []
        for start in range(0, len(records), self.batch_size):
            batch = records[start:start + self.batch_size]
            response = self._request(
                'POST',
                endpoint,
                payload={'data': batch},
                token=token,
            )
            status_code = response.get('_status_code')
            if status_code not in {201, 202}:
                raise ProspectServiceError(f'Unexpected Prospect status {status_code} for {endpoint}')
            responses.append(response)
        return {'responses': responses}

    def _get_records(self, method_name: str, endpoint: str, *, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self._ensure_configured()
        token = self._token_for_read(method_name)
        response = self._request(
            'GET',
            endpoint,
            query=query,
            token=token,
        )
        if isinstance(response.get('data'), list):
            return response['data']
        if isinstance(response.get('results'), list):
            return response['results']
        return []

    def pushAgent(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post_records('pushAgent', self.WRITE_ENDPOINTS['pushAgent'], data)

    def pushCustomer(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post_records('pushCustomer', self.WRITE_ENDPOINTS['pushCustomer'], data)

    def pushInstallation(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post_records('pushInstallation', self.WRITE_ENDPOINTS['pushInstallation'], data)

    def pushInstallationTimeSeries(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post_records('pushInstallationTimeSeries', self.WRITE_ENDPOINTS['pushInstallationTimeSeries'], data)

    def pushTarget(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post_records('pushTarget', self.WRITE_ENDPOINTS['pushTarget'], data)

    def pushReport(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post_records('pushReport', self.WRITE_ENDPOINTS['pushReport'], data)

    def getInstallations(self, size: int = 100, page: int = 1, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query = {'size': size, 'page': page}
        if filters:
            query.update(filters)
        return self._get_records('getInstallations', self.READ_ENDPOINTS['getInstallations'], query=query)

    def getTargets(self, size: int = 100, page: int = 1, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query = {'size': size, 'page': page}
        if filters:
            query.update(filters)
        return self._get_records('getTargets', self.READ_ENDPOINTS['getTargets'], query=query)


def sanitize_for_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_for_json(v) for v in data]
    if isinstance(data, Decimal):
        return float(data)
    return data


class SyncToProspectJob:
    MAX_ATTEMPTS = 3
    RETRY_DELAYS_SECONDS = (60, 300, 900)
    ALLOWED_METHODS = {
        'pushAgent',
        'pushCustomer',
        'pushInstallation',
        'pushInstallationTimeSeries',
        'pushTarget',
        'pushReport',
        'getInstallations',
        'getTargets',
    }

    def __init__(self, method_name: str, data: Any, record_id: int | None = None, record_type: str = '', *, log_id: int | None = None):
        self.method_name = method_name
        self.data = data
        self.record_id = record_id
        self.record_type = str(record_type or '')
        self.log_id = log_id

    def run(self) -> ProspectSyncLog:
        if self.method_name not in self.ALLOWED_METHODS:
            raise ValueError(f'Unsupported Prospect sync method: {self.method_name}')
        service = ProspectService.from_settings()
        log = ProspectSyncLog.objects.filter(id=self.log_id).first() if self.log_id else None
        sanitized_data = sanitize_for_json(self.data)
        if log is None:
            log = ProspectSyncLog.objects.create(
                method_name=self.method_name,
                payload=sanitized_data,
                status=ProspectSyncStatus.PENDING,
                attempts=0,
                record_id=self.record_id,
                record_type=self.record_type,
            )
        else:
            log.method_name = self.method_name
            log.payload = sanitized_data
            log.record_id = self.record_id
            log.record_type = self.record_type
            log.status = ProspectSyncStatus.PENDING
            log.save(update_fields=['method_name', 'payload', 'record_id', 'record_type', 'status', 'updated_at'])
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            log.attempts = attempt
            log.save(update_fields=['attempts', 'updated_at'])
            try:
                method = getattr(service, self.method_name)
                if self.method_name in {'getInstallations', 'getTargets'}:
                    filters = dict(self.data) if isinstance(self.data, dict) else {}
                    method(
                        size=int(filters.pop('size', 100)),
                        page=int(filters.pop('page', 1)),
                        filters=filters,
                    )
                else:
                    if isinstance(self.data, dict) and isinstance(self.data.get('data'), list):
                        method(self.data['data'])
                    else:
                        method(self.data if isinstance(self.data, list) else [self.data])
                log.status = ProspectSyncStatus.SUCCESS
                log.error_message = ''
                log.save(update_fields=['status', 'error_message', 'updated_at'])
                return log
            except Exception as exc:  # noqa: BLE001
                log.error_message = str(exc)
                next_attempt = attempt + 1
                if attempt >= self.MAX_ATTEMPTS:
                    log.status = ProspectSyncStatus.FAILED
                    log.save(update_fields=['error_message', 'status', 'updated_at'])
                    logger.warning('Prospect sync attempt %s/%s failed permanently for %s: %s', attempt, self.MAX_ATTEMPTS, self.method_name, exc)
                    return log
                log.status = ProspectSyncStatus.PENDING
                log.save(update_fields=['error_message', 'status', 'updated_at'])
                logger.warning('Prospect sync attempt %s/%s failed for %s: %s', attempt, self.MAX_ATTEMPTS, self.method_name, exc)
                self.dispatch_async(
                    self.method_name,
                    self.data,
                    record_id=self.record_id,
                    record_type=self.record_type,
                    log_id=log.id,
                    delay_seconds=self.RETRY_DELAYS_SECONDS[attempt - 1],
                )
                return log
        return log

    @classmethod
    def dispatch_async(
        cls,
        method_name: str,
        data: Any,
        *,
        record_id: int | None = None,
        record_type: str = '',
        log_id: int | None = None,
        delay_seconds: int = 0,
        run_immediately: bool = False,
    ):
        def _enqueue():
            if run_immediately and delay_seconds <= 0:
                cls(method_name, data, record_id, record_type, log_id=log_id).run()
                return
            if delay_seconds <= 0:
                _executor.submit(cls(method_name, data, record_id, record_type, log_id=log_id).run)
                return

            def _delayed_run():
                time.sleep(delay_seconds)
                cls(method_name, data, record_id, record_type, log_id=log_id).run()

            _executor.submit(_delayed_run)

        transaction.on_commit(_enqueue)


def queue_project_targets_sync(project_id: str, *, run_immediately: bool = False, record_type: str = 'target'):
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return
    payload = build_project_target_payload(project)
    SyncToProspectJob.dispatch_async(
        'pushTarget',
        payload,
        record_id=int(project.id),
        record_type=record_type,
        run_immediately=run_immediately,
    )


def queue_project_agent_sync(project_id: str):
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return
    vendor = User.objects.filter(id=project.vendor_id).first()
    if vendor is None:
        vendor = User.objects.filter(username=project.vendor_id).first()
    if vendor is None:
        return
    location_area_1 = (
        getattr(vendor, 'district', '') or ''
    ) or (
        getattr(vendor, 'verification_zone', '') or ''
    ) or project.district_zone or project.district or project.region or ''
    payload = {
        'data': [{
            'external_id': str(vendor.id),
            'agent_type': 'sales_agent',
            'gender': normalize_prospect_gender(getattr(vendor, 'gender', '') or ''),
            'country': 'LS',
            'location_area_1': location_area_1,
            'company': getattr(vendor, 'org_name', '') or '',
        }]
    }
    SyncToProspectJob.dispatch_async('pushAgent', payload, record_id=int(vendor.id), record_type='user')


def _build_installation_sync_payload(report: InstallationReport) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    project_setup = getattr(report.project, 'project_setup', None)
    district = report.project.district or report.project.district_zone or report.project.region or ''
    project_technology = normalize_project_technology(report.project.tech_type or report.project.technology_type)
    device_category = ProspectService.DEVICE_CATEGORY_MAP.get(project_technology, '')
    customer_payload = {
        'data': [{
            'external_id': str(report.id),
            'gender': derive_installation_gender(report.household_type),
            'identification_type': 'National ID',
            'identification_number': _hash_value(report.beneficiary_id),
            'phone': _hash_value(getattr(report, 'beneficiary_phone', '')),
            'country': 'LS',
            'latitude': float(report.gps_lat),
            'longitude': float(report.gps_lng),
            'location_area_1': district,
        }]
    }
    installation_payload = {
        'data': [{
            'customer_external_id': str(report.id),
            'installer_agent_external_id': str(report.vendor_id),
            'device_category': device_category,
            'manufacturer': getattr(project_setup, 'device_brand', '') or report.project.device_brand or '',
            'model': getattr(project_setup, 'device_model', '') or report.project.device_model or '',
            'serial_number': report.serial_number,
            'installation_date': report.installation_date.isoformat() if report.installation_date else None,
            'latitude': float(report.gps_lat),
            'longitude': float(report.gps_lng),
            'country': 'LS',
            'location_area_1': district,
            'usage_category': 'household',
            'usage_sub_category': report.household_type or '',
            'rated_power_w': float(getattr(project_setup, 'rated_power_w', 0)) if project_setup and getattr(project_setup, 'rated_power_w', None) else None,
            'is_test': False,
        }]
    }
    return customer_payload, installation_payload


def queue_installation_sync(report_id: str, *, include_customer: bool = True, include_installation: bool = True):
    report = InstallationReport.objects.select_related('project', 'project__project_setup').filter(id=report_id).first()
    if not report:
        return
    customer_payload, installation_payload = _build_installation_sync_payload(report)
    if include_customer:
        SyncToProspectJob.dispatch_async('pushCustomer', customer_payload, record_id=int(report.id), record_type='installation')
    if include_installation:
        SyncToProspectJob.dispatch_async('pushInstallation', installation_payload, record_id=int(report.id), record_type='installation')


def queue_project_completion_report_sync(project_id: str):
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return

    verified_installations = InstallationReport.objects.filter(
        project=project,
        status=InstallationStatus.VERIFIED,
    ).count()
    total_installations = InstallationReport.objects.filter(project=project).count()
    paid_claims = project.payment_claims.filter(status='Paid').count()
    payload = {
        'data': [{
            'external_id': f'report_{project.id}_{timezone.now().year}_{timezone.now().month:02d}',
            'country': 'LS',
            'reporting_phase': f'PRJ-{project.id}',
        }]
    }
    SyncToProspectJob.dispatch_async('pushReport', payload, record_id=int(project.id), record_type='project')


def build_project_timeseries_payload(project: Project) -> dict[str, Any]:
    readings = SmartMeterReading.objects.filter(project=project).select_related('installation').order_by('meter_id', 'recorded_at')
    if not readings:
        return {}

    cumulative_data = {}
    for reading in readings:
        meter_id = reading.meter_id
        if meter_id not in cumulative_data:
            cumulative_data[meter_id] = []
        cumulative_data[meter_id].append(reading)

    payload_data = []
    for meter_id, meter_readings in cumulative_data.items():
        cumulative_wh = 0
        for reading in meter_readings:
            cumulative_wh += float(reading.kwh) * 1000
            installation = reading.installation
            project_setup = getattr(installation.project if installation else project, 'project_setup', None)
            manufacturer = getattr(project_setup, 'device_brand', '') if project_setup else ''
            payload_data.append({
                'metered_at': reading.recorded_at.astimezone(dt_timezone.utc).isoformat(timespec='milliseconds'),
                'interval_seconds': 3600,
                'serial_number': meter_id,
                'manufacturer': manufacturer,
                'output_energy_interval_wh': round(float(reading.kwh) * 1000, 2),
                'output_energy_cumulative_wh': round(cumulative_wh, 2),
                'output_power_w': None,
            })

    return {'data': payload_data}


def queue_project_timeseries_sync(project_id: str) -> int:
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return 0
    payload = build_project_timeseries_payload(project)
    if not payload:
        return 0
    SyncToProspectJob.dispatch_async(
        'pushInstallationTimeSeries',
        payload,
        record_id=int(project.id),
        record_type='project',
    )
    return len(payload.get('data', []))
