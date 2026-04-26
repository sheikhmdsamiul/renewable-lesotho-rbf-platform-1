import json
import math
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.models.expressions import RawSQL

from .models import InstallationReport


class GpsValidator:
    _feature_cache: dict[str, Any] | None = None
    DISTRICT_PROPERTY_KEYS = (
        'district',
        'district_name',
        'name',
        'adm2_en',
        'adm2_name',
        'admin2name',
        'shapeName',
        'adm1_name',
    )

    @classmethod
    def _geojson_path(cls) -> Path:
        configured = str(getattr(settings, 'LESOTHO_BOUNDARY_PATH', '/public/geojson/lesotho.geojson') or '').strip()
        normalized = configured[1:] if configured.startswith('/') else configured
        return settings.BASE_DIR / normalized

    @classmethod
    def _load_feature(cls) -> dict[str, Any]:
        if cls._feature_cache is None:
            with cls._geojson_path().open('r', encoding='utf-8') as handle:
                cls._feature_cache = json.load(handle)
        return cls._feature_cache

    @classmethod
    def _iter_features(cls) -> list[dict[str, Any]]:
        payload = cls._load_feature()
        if payload.get('type') == 'FeatureCollection':
            features = payload.get('features') or []
            return [feature for feature in features if isinstance(feature, dict)]
        return [payload]

    @classmethod
    def _geometry_contains(cls, latitude: float, longitude: float, geometry: dict[str, Any]) -> bool:
        try:
            from shapely.geometry import Point, shape

            return bool(shape(geometry).contains(Point(float(longitude), float(latitude))))
        except Exception:
            coordinates = geometry.get('coordinates') or []
            geometry_type = geometry.get('type')
            polygons = coordinates if geometry_type == 'MultiPolygon' else [coordinates]
            for polygon in polygons:
                if not polygon:
                    continue
                exterior_ring = polygon[0]
                if not cls._point_in_ring(latitude, longitude, exterior_ring):
                    continue
                if any(cls._point_in_ring(latitude, longitude, hole) for hole in polygon[1:]):
                    return False
                return True
            return False

    @classmethod
    def _normalize_district_name(cls, value: str | None) -> str:
        return ' '.join(str(value or '').strip().lower().replace('_', ' ').split())

    @classmethod
    def _extract_district_name(cls, feature: dict[str, Any]) -> str | None:
        properties = feature.get('properties') or {}
        for key in cls.DISTRICT_PROPERTY_KEYS:
            value = properties.get(key)
            normalized = str(value or '').strip()
            if normalized:
                return normalized
        return None

    @classmethod
    def _point_in_ring(cls, latitude: float, longitude: float, ring: list[list[float]]) -> bool:
        inside = False
        point_x = longitude
        point_y = latitude
        total = len(ring)
        if total < 3:
            return False
        j = total - 1
        for i in range(total):
            xi, yi = ring[i]
            xj, yj = ring[j]
            intersects = ((yi > point_y) != (yj > point_y)) and (
                point_x < (xj - xi) * (point_y - yi) / ((yj - yi) or 1e-12) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    @classmethod
    def isInsideLesotho(cls, latitude: float, longitude: float) -> bool:
        for feature in cls._iter_features():
            geometry = feature.get('geometry') or {}
            if cls._geometry_contains(latitude, longitude, geometry):
                return True
        return False

    @classmethod
    def resolveDistrictName(cls, latitude: float, longitude: float) -> str | None:
        matches: list[str] = []
        for feature in cls._iter_features():
            geometry = feature.get('geometry') or {}
            if not cls._geometry_contains(latitude, longitude, geometry):
                continue
            district_name = cls._extract_district_name(feature)
            if district_name:
                matches.append(district_name)
        return matches[0] if matches else None

    @classmethod
    def districtBoundaryConfigured(cls) -> bool:
        return any(cls._extract_district_name(feature) for feature in cls._iter_features())

    @classmethod
    def isInsideProjectDistrict(cls, latitude: float, longitude: float, district_label: str | None) -> bool:
        matched_district = cls.resolveDistrictName(latitude, longitude)
        if not matched_district:
            return False
        allowed = [
            cls._normalize_district_name(part)
            for part in str(district_label or '').split(',')
            if cls._normalize_district_name(part)
        ]
        return cls._normalize_district_name(matched_district) in allowed

    @staticmethod
    def _haversine_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        radius = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lng2 - lng1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @classmethod
    def hasDuplicateNearby(
        cls,
        latitude: float,
        longitude: float,
        project_id: str,
        exclude_id: str | None = None,
    ) -> dict[str, Any]:
        queryset = InstallationReport.objects.filter(project_id=project_id)
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)
        duplicate_radius_meters = float(getattr(settings, 'GPS_DUPLICATE_RADIUS_METERS', 10))

        if connection.vendor == 'sqlite':
            nearest = None
            nearest_distance = None
            for item in queryset.only('id', 'gps_lat', 'gps_lng'):
                distance = cls._haversine_distance_meters(
                    latitude,
                    longitude,
                    float(item.gps_lat),
                    float(item.gps_lng),
                )
                if nearest_distance is None or distance < nearest_distance:
                    nearest = item
                    nearest_distance = distance
            is_duplicate = nearest is not None and nearest_distance is not None and nearest_distance < duplicate_radius_meters
            return {
                'found': bool(is_duplicate),
                'nearest_id': int(nearest.id) if is_duplicate else None,
                'distance_meters': round(float(nearest_distance), 2) if is_duplicate and nearest_distance is not None else None,
            }

        distance_sql = RawSQL(
            """
            (6371000 * acos(
                cos(radians(%s)) * cos(radians(gps_lat)) *
                cos(radians(gps_lng) - radians(%s)) +
                sin(radians(%s)) * sin(radians(gps_lat))
            ))
            """,
            (latitude, longitude, latitude),
        )
        nearest = (
            queryset.annotate(distance_meters=distance_sql)
            .filter(distance_meters__lt=duplicate_radius_meters)
            .order_by('distance_meters')
            .values('id', 'distance_meters')
            .first()
        )
        return {
            'found': bool(nearest),
            'nearest_id': int(nearest['id']) if nearest else None,
            'distance_meters': round(float(nearest['distance_meters']), 2) if nearest else None,
        }

    @classmethod
    def hasDuplicateCoordinate(
        cls,
        latitude: float,
        longitude: float,
        project_id: str,
        exclude_installation_id: str | None = None,
    ) -> dict[str, Any]:
        result = cls.hasDuplicateNearby(latitude, longitude, project_id, exclude_id=exclude_installation_id)
        return {
            'isDuplicate': result['found'],
            'nearestId': str(result['nearest_id']) if result['nearest_id'] is not None else None,
            'distanceMeters': result['distance_meters'],
        }
