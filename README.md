# Conquiztador

A three-player quiz game of territorial conquest. Players answer questions to claim territories on a shared map and then battle each other for them.

- `backend/` — Django 5.2 + Django REST Framework, PostgreSQL 17
- `frontend/` — React + TypeScript + Vite

## Requirements

- Python 3.12+
- Node.js LTS
- Docker (for the bundled PostgreSQL), or any PostgreSQL 14+ server

## Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env      # then set DJANGO_SECRET_KEY and DB_PASSWORD
docker compose up -d --wait # PostgreSQL on 127.0.0.1:5433
python manage.py migrate
python manage.py runserver
```

On Linux/macOS use `python3 -m venv .venv`, `source .venv/bin/activate` and `cp`.

### Database

Configuration is read from `backend/.env` (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`). `backend/compose.yaml` starts a PostgreSQL 17 container that uses the same values, so `.env` is the single source of truth.

To use an existing server instead, point `.env` at it. The role needs `CREATEDB`, because the test runner creates its own `test_<name>` database:

```sql
CREATE ROLE conquiztador LOGIN PASSWORD 'change-me' CREATEDB;
CREATE DATABASE conquiztador OWNER conquiztador;
```

### Tests

```bash
cd backend
python manage.py test
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The development server runs on `http://localhost:5173/` and proxies `/api` to `http://127.0.0.1:8000`. If Django runs elsewhere, start Vite with `API_PROXY_TARGET`, e.g. `API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev`. Because the browser only talks to the Vite origin, session and CSRF cookies work without CORS.

## Authentication (M01)

Session authentication with CSRF protection. All errors share one shape: `{"errors": {"<field>": ["message", ...]}}`; general errors use `non_field_errors` or `detail`.

| Method | Endpoint | Access | Success |
|---|---|---|---|
| `GET` | `/api/auth/csrf/` | Public | `204`, sets the `csrftoken` cookie |
| `POST` | `/api/auth/register/` | Public | `201`, creates `User` + `Profile` and logs in |
| `POST` | `/api/auth/login/` | Public | `200` |
| `POST` | `/api/auth/logout/` | Authenticated | `204` |
| `GET` | `/api/auth/me/` | Authenticated | `200` |
| `PATCH` | `/api/auth/me/` | Authenticated | `200`, only `nickname` and `avatar_key` |

- Unsafe requests need the `X-CSRFToken` header, including anonymous login and registration.
- Missing authentication returns `401`; a failed CSRF check returns `403`.
- Usernames, emails and nicknames are unique case-insensitively; nickname whitespace is collapsed.
- `PATCH /api/auth/me/` rejects any field other than `nickname` and `avatar_key` with `400`.

The UI has registration, login and profile screens; the profile route is protected and the session survives a page refresh.
