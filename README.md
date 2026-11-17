# Conquiztador

A three-player quiz game of territorial conquest. Players answer questions to claim territories on a shared map and then battle each other for them.

- `backend/` — Django 5.2 + Django REST Framework, PostgreSQL
- `frontend/` — React + TypeScript + Vite

## Requirements

- Python 3.12+
- Node.js LTS
- PostgreSQL 14+ with a role that has `CREATEDB` (the test runner creates its own database)

## Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env   # then fill in the database credentials
python manage.py check
python manage.py runserver
```

On Linux/macOS use `python3 -m venv .venv`, `source .venv/bin/activate` and `cp`.

The database is configured through `backend/.env` (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`). Example setup in `psql` as a superuser:

```sql
CREATE ROLE conquiztador LOGIN PASSWORD 'change-me' CREATEDB;
CREATE DATABASE conquiztador OWNER conquiztador;
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The development server runs on `http://localhost:5173/`.
