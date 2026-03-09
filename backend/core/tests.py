from rest_framework import status
from rest_framework.test import APITestCase


class HealthApiTests(APITestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")
        self.assertTrue(response.data["checks"]["database"]["ok"])
