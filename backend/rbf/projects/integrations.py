import json
import urllib.request
from django.conf import settings


def push_project_to_prospect(project) -> tuple[bool, str]:
    """
    Push minimal project metadata to Prospect API if configured.
    Returns (success, message).
    """
    url = getattr(settings, 'PROSPECT_API_URL', '') or ''
    if not url:
        return False, 'Prospect API URL not configured'

    payload = {
        'project_id': str(project.id),
        'project_reference': project.project_reference,
        'tech_type': project.tech_type,
        'region': project.region,
        'district': project.district,
        'target_installations': project.target_installations,
        'target_beneficiaries': project.target_beneficiaries,
        'target_female_pct': project.target_female_pct,
        'target_vulnerable_pct': project.target_vulnerable_pct,
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        return 200 <= status < 300, f'Status {status}'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
