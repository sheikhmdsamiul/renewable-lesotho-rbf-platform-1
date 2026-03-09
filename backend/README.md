Backend (Django) for Lesotho RBF Platform

Quick start (Docker):
1. Copy environment file:
   - `cp backend/.env.example backend/.env`
2. Start services:
   - `docker compose up --build -d`
3. Check health:
   - `http://localhost:8000/api/health/`

Services:
- API: http://localhost:8000
- Swagger: http://localhost:8000/api/docs/
- Mailhog: http://localhost:8025
- Postgres: localhost:5432 (rbf / rbf_user / rbf_pass)

Apps and endpoints:
- Users: /api/users/
- Auth token: /api/users/auth/token/
- Auth refresh: /api/users/auth/token/refresh/
- Current user: /api/users/auth/me/
- Tenders: /api/tenders/
- Projects: /api/projects/
- Notifications: /api/notifications/
- Health: /api/health/

Production hardening notes:
- Set `DJANGO_DEBUG=0`
- Set a strong `SECRET_KEY`
- Set `ALLOWED_HOSTS` to your real hostnames
- Set `CORS_ALLOW_ALL_ORIGINS=0` and define `CORS_ALLOWED_ORIGINS`
- Set `CSRF_TRUSTED_ORIGINS` to your frontend domains
- Set `API_REQUIRE_AUTH=1` to enforce authentication for API writes
