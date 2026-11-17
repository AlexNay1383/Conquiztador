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

## Territories and map (M04)

### Map

All games use one map with 15 territories and 25 undirected edges, defined in `backend/games/map_definition.py`:

```text
skali ------- dunavia ---- zhitno-pole --- madara -------- kaliakra
  |       \      |              |             |      \         |
sredets ---- balkania ------ leventa ----- pelikania --- zlaten-grozd
  |              |              |      \      |                |
pirina ------- ezera ----- rozova-dolina -- chuden-krai ---- tsarevo
```

| Slug | Name | Neighbours |
|---|---|---|
| `skali` | Скали | `balkania`, `dunavia`, `sredets` |
| `dunavia` | Дунавия | `balkania`, `skali`, `zhitno-pole` |
| `zhitno-pole` | Житно поле | `dunavia`, `leventa`, `madara` |
| `madara` | Мадара | `kaliakra`, `pelikania`, `zhitno-pole`, `zlaten-grozd` |
| `kaliakra` | Калиакра | `madara`, `zlaten-grozd` |
| `sredets` | Средец | `balkania`, `pirina`, `skali` |
| `balkania` | Балкания | `dunavia`, `ezera`, `leventa`, `skali`, `sredets` |
| `leventa` | Левента | `balkania`, `chuden-krai`, `pelikania`, `rozova-dolina`, `zhitno-pole` |
| `pelikania` | Пеликания | `chuden-krai`, `leventa`, `madara`, `zlaten-grozd` |
| `zlaten-grozd` | Златен грозд | `kaliakra`, `madara`, `pelikania`, `tsarevo` |
| `pirina` | Пирина | `ezera`, `sredets` |
| `ezera` | Езера | `balkania`, `pirina`, `rozova-dolina` |
| `rozova-dolina` | Розова долина | `chuden-krai`, `ezera`, `leventa` |
| `chuden-krai` | Чуден край | `leventa`, `pelikania`, `rozova-dolina`, `tsarevo` |
| `tsarevo` | Царево | `chuden-krai`, `zlaten-grozd` |

One valid capital triple is `skali`, `kaliakra`, `rozova-dolina`: no two of them share an edge. The map has 189 such triples.

### Representation

- **Definition:** a frozen `MapDefinition`: a tuple of `TerritoryDefinition(slug, name)` and a tuple of edges, each logical edge listed once as a pair of slugs. It is plain Python data, not database rows, so it can't be changed at runtime and needs no fixture.
- **Per-game records:** each game gets its own records. `Territory` (game, name, slug, owner, score) has a symmetric self-referencing `neighbors` many-to-many. Django stores both directions of every edge in the through table, and validation treats them as one logical edge. `Capital` (territory, player, health 0–3) reaches its game through the territory and has no separate game field.
- **Validation (`games/maps.py`):**
  - `check_definition()` / `validate_definition()` check a definition.
  - `check_game_map()` / `validate_game_map()` compare a game's records with the definition: names, slugs, every logical edge, symmetry, no cross-game links, owners and capitals.
  - The `check_*` functions return a list of problems; the `validate_*` functions raise `MapValidationError`. None of them writes to the database. An empty map of a `waiting` game is a valid game state, but `check_game_map()` reports it as incomplete.
- **Access:** `get_game_territories(game)`, `get_player_territories(player)` and `get_player_capital(player)`. The last returns `None` when the player has no capital and never creates one.

### Integrity

- **Normalization:** names are trimmed and internal whitespace collapsed to single spaces, then compared case-insensitively. Slugs are trimmed, lower-cased and must match `^[a-z0-9]+(-[a-z0-9]+)*$`. The definition must already be in normalized form. `Territory.full_clean()` normalizes before validating.
- **Database constraints:**
  - unique `(game, slug)` and unique `(game, lower(name))`;
  - slug and name format checks;
  - `score >= 0`;
  - capital `health` between 0 and 3;
  - one capital per territory and one per player (one-to-one fields).
- **Application rules:**
  - The owner belongs to the territory's game.
  - A territory can't move to another game.
  - A capital's territory is owned by the capital's player, and both are in one game; its owner can't change.
  - The `m2m_changed` guard refuses self-links and cross-game neighbour links.
  - Full-map validation covers everything above.
- **Entry points:** territories, edges and capitals are created only by game initialization (M05). Gameplay services (M07, M08) change only owners and scores. Admin is read-only. Direct ORM or SQL access is not a public interface.
- **Deletion:**
  - Deleting a `Game` removes its players, territories, edges and capitals together.
  - Deleting a player (or their user) who owns territories is refused (`RESTRICT`).
  - Deleting a capital's territory is refused.
  - Health 0 marks a destroyed capital but keeps the record, owner and player.
- **Admin:** territories (game, name, slug, owner, score, neighbours; search by name/slug; filter by game/owner) and capitals (player, territory, health; search by player/territory; filter by game) are view-only. Adding, editing and deleting are disabled, so score and health aren't editable either.
