<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Renewable Lesotho RBF Platform

This repository contains:
- Frontend: React + Vite (`src/`)
- Backend: Django + DRF (`backend/`)

## Local Run

Backend (Docker):
1. `cp backend/.env.example backend/.env`
2. `docker compose up --build -d`
3. Backend health: `http://localhost:8000/api/health/`

Frontend:
1. `npm install`
2. `npm run dev`
3. Open `http://127.0.0.1:5173`

By default frontend API calls target:
- `VITE_API_URL` if set
- `http://localhost:8000` in dev
- same-origin `/api` in production builds
