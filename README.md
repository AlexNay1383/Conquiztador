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

## Question bank (M02)

The `questions` app holds `Category`, the abstract `BaseQuestion` and its two concrete models `ChoiceQuestion` (with four `AnswerOption`s, exactly one correct) and `NumericQuestion` (integer `correct_answer`). Categories with questions are protected from deletion; deleting a choice question deletes its options.

Load the initial bank (6 categories, 12 choice questions with 48 options, 12 numeric questions, in Bulgarian):

```bash
python backend/manage.py loaddata questions/question_bank.json
```

The "four options, one correct" rule spans several rows, so it is enforced in application code rather than by the database:

- `ChoiceQuestion.clean()` validates the saved options.
- The admin inline accepts exactly four options and requires exactly one to be correct.
- `ChoiceQuestion.objects.playable()` returns only questions that satisfy the rule; gameplay draws questions only from it.

## Games and rounds (M03)

The `games` app models a game (`Game`), the three participants (`Player`: user, color, score) and the rounds (`Round`: number, type, status, winner).

- **Game lifecycle:** `waiting` → `active` → `completed`. A game starts with exactly three players; a completed game accepts no players or rounds.
- **Round lifecycle:** `pending` → `active` → `completed`. Numbers are `1, 2, …` per game. A new round waits until the previous one is completed. `Game.get_current_round()` returns the round with the highest number.

### Service layer

State changes go through `games.services`. Every operation runs in a transaction and starts by locking the game row (`SELECT … FOR UPDATE`), so concurrent operations on one game are serialized.

| Operation | Purpose |
|---|---|
| `create_game()` | New `waiting` game |
| `add_player(game_id, user_id, color=None)` / `remove_player(player_id)` | Only while `waiting`; at most three players |
| `start_game(game_id)` | `waiting` → `active` |
| `complete_game(game_id)` | `active` → `completed` when no round is unfinished |
| `create_round(game_id, type)` / `start_round(round_id)` / `complete_round(round_id, winner_id)` | Round lifecycle |

Refusals raise a subclass of `games.exceptions.GameError` with a stable `code` and a Bulgarian `message`:

- `NotFoundError` — a referenced record is missing (`game_not_found`, `round_not_found`, …)
- `InvalidInputError` — bad arguments (`color_taken`, `winner_not_in_game`, …)
- `InvalidStateError` — not allowed right now (`game_not_waiting`, `game_full`, `round_in_progress`, …)

```python
try:
    services.add_player(game.pk, user.pk, "red")
except InvalidInputError as error:
    error.code  # "color_taken"
```

### Integrity

- **Database constraints:** unique user and unique color per game; non-negative score; valid choice values; unique round number per game; at most one `active` round per game; `completed_at` set exactly when a round is `completed`; no winner before completion.
- **Application rules:** the winner belongs to the same game; at most three players; changes only while `waiting`.
- **Admin:** shows game status and rounds read-only, because lifecycle changes go through services. Players can be added, edited or removed only while their game is `waiting`.
