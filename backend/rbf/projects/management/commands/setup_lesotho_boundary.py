import json
from urllib.request import urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


SOURCE_URL = 'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson'


class Command(BaseCommand):
    help = 'Download, validate, and store the Lesotho boundary GeoJSON.'

    def handle(self, *args, **options):
        configured = str(getattr(settings, 'LESOTHO_BOUNDARY_PATH', '/public/geojson/lesotho.geojson') or '').strip()
        normalized = configured[1:] if configured.startswith('/') else configured
        target_path = settings.BASE_DIR / normalized
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with urlopen(SOURCE_URL, timeout=30) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f'Failed to download GeoJSON: {exc}') from exc

        features = payload.get('features') or []
        feature = next(
            (
                item for item in features
                if (item.get('properties') or {}).get('ISO_A2') == 'LS'
            ),
            None,
        )
        if feature is None:
            raise CommandError('Could not find the Lesotho feature in the downloaded dataset.')

        geometry = feature.get('geometry') or {}
        if geometry.get('type') not in {'Polygon', 'MultiPolygon'} or not geometry.get('coordinates'):
            raise CommandError('Downloaded feature is not valid GeoJSON for a country boundary.')

        with target_path.open('w', encoding='utf-8') as handle:
            json.dump(feature, handle)

        try:
            with target_path.open('r', encoding='utf-8') as handle:
                saved_payload = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f'Saved file is not valid JSON: {exc}') from exc

        saved_geometry = saved_payload.get('geometry') or {}
        if saved_geometry.get('type') not in {'Polygon', 'MultiPolygon'} or not saved_geometry.get('coordinates'):
            raise CommandError('Saved file is not valid GeoJSON.')

        self.stdout.write(self.style.SUCCESS('Lesotho boundary file saved'))
