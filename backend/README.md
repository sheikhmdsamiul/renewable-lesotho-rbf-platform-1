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

Prospect integration:
- Configure `PROSPECT_BASE_URL`, `PROSPECT_WRITE_TOKEN`, and `PROSPECT_READ_TOKEN` in `backend/.env`
- Prospect write endpoints are limited to: `/v1/in/agents`, `/v1/in/customers`, `/v1/in/installations`, `/v1/in/installations_ts`, `/v1/in/targets`, `/v1/in/reports`
- Prospect read endpoints are limited to: `/v1/out/installations`, `/v1/out/targets`
- Project targets are queued to Prospect after local project creation
- Project target updates are re-queued after local project target changes
- Vendor setup completion queues the Prospect agent sync
- Installation submissions are queued to Prospect after local save
- Field verification re-queues the Prospect installation sync as an update
- On-demand sync panel refreshes can be queued via `POST /api/projects/prospect-sync-logs/refresh-panel/`
- Sync logs are available at `/api/projects/prospect-sync-logs/`
- Retry failed or pending syncs with `python manage.py retry_prospect_syncs`

GIS map setup:
- Install backend dependencies including `shapely` from `requirements.txt`
- Run once on first deploy: `python manage.py setup_lesotho_boundary`
- The command stores the filtered boundary at `backend/public/geojson/lesotho.geojson`
- The frontend map loads the boundary from `GET /api/map/boundary`
- Map data is served from `GET /api/map/installations`

Production hardening notes:
- Set `DJANGO_DEBUG=0`
- Set a strong `SECRET_KEY`
- Set `ALLOWED_HOSTS` to your real hostnames
- Set `CORS_ALLOW_ALL_ORIGINS=0` and define `CORS_ALLOWED_ORIGINS`
- Set `CSRF_TRUSTED_ORIGINS` to your frontend domains
- Set `API_REQUIRE_AUTH=1` to enforce authentication for API writes
