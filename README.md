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

## Game initialization (M05)

### Interface

```bash
python backend/manage.py start_game <game_id>
```

From code: `games.services.initialize_game(game_id)`. It returns the active `Game`, or raises a `GameError` subclass whose `code` names the reason (the command prints `[code] message`):

| Exception | `code` | Reason |
|---|---|---|
| `NotFoundError` | `game_not_found` | No such game |
| `InvalidStateError` | `game_not_waiting` | Already started or completed (also the second of two concurrent starts) |
| `InvalidStateError` | `wrong_player_count` / `invalid_players` | Not exactly three valid players |
| `InvalidStateError` | `map_already_exists` | The game already has territories or capitals (a partial map is neither completed nor deleted) |
| `InvalidStateError` | `invalid_map_definition` | The definition breaks an M04 rule, including "no valid capital triple" |

Creating a game or adding the third player never starts it automatically.

### What happens in one attempt

One `transaction.atomic()` block:

1. Lock the game row and its player rows (`SELECT … FOR UPDATE`).
2. Check the preconditions above.
3. Bulk-create the 15 territories, then both directions of every edge.
4. Choose the capitals (see below) and set their owners.
5. Create three `Capital`s with health 3.
6. Set the status to `active`.
7. Run full map validation.

Any error, whether a refusal, a database error or failed validation, rolls back everything from the attempt, leaving the previous state intact; a later attempt may succeed. A successful start is never repeated: the second call gets `game_not_waiting`. Rounds, players and other games are never touched.

### Capital selection

All mutually non-adjacent triples are enumerated from the definition (189 for the project map). One is drawn with `random.Random().choice`, and the three players are assigned in `random.sample` order. Every valid assignment is reachable, and the draw can't fail or retry, because only valid triples are candidates. No seed is needed; tests inject their own `rng`.

### Concurrency and composition

- Every state-changing operation on a game takes the game's row lock first: `initialize_game`, `add_player`, `remove_player`, the round services, and the admin player form, whose changes are saved inside the same lock.
- Two simultaneous starts therefore run one after the other, and the second sees `active`.
- Joining or leaving runs either entirely before the start or after it, and after it the request is refused.
- After activation, admin shows players read-only and refuses deletion.
- Database backstops: unique `(game, slug)` blocks a second map. Foreign keys are deferred until commit, so deleting a player who owns territories fails even under a race.
- `test_initialization_concurrency.py` runs these races on real threads with separate connections.

### Database

PostgreSQL 17 (`backend/compose.yaml`) at the default `READ COMMITTED` isolation level. The guarantees rely on its row-level `SELECT … FOR UPDATE` locks, transactional rollback of bulk inserts, and deferred foreign-key checks. SQLite is not supported: it ignores `select_for_update`, and its database-wide write lock would turn these races into "database is locked" errors instead of the documented refusals.

## Rounds (M06)

A `city_capture` round is played with numeric questions. Every player has 10 seconds per question, and the round decides first and second place.

### Operations (`games.services`)

| Operation | Effect |
|---|---|
| `create_city_capture_round(game_id)` | `pending` round for the three players with its first random unused numeric question; the clock does not run yet |
| `start_round(round_id)` | `active`; the first question starts now and ends 10 s later |
| `submit_answer(round_id, player_id, value)` | Accepts one integer per player per question; closes the question when everyone has answered |
| `close_question(round_id)` | Explicit processing without a new answer; refused (`question_still_open`) before the deadline unless everyone has answered |
| `get_round_state(round_id)` | Read-only snapshot for reloading: current question, deadline, remaining time, who answered, ranking, history |

Every operation requires an active game and runs inside the game's row lock. Round numbers are `max + 1`. A game has at most one unfinished round (enforced by a partial unique index). `Game.get_current_round()` is unchanged.

### Rules

- **Trusted time:** the arrival moment is `games.clock.now()`, taken when the request is processed and before the deadline check. The same value is stored as `received_at` and used for speed. Answers are accepted only while `now < deadline`; at the deadline or after, they are refused. Client timestamps are never used, and times keep microseconds.
- **Input:** `int`, or a string of an integer such as `" -42 "`. Floats (even `12.0`), booleans, decimals and out-of-range numbers are refused with `invalid_answer`, so nothing is silently truncated. A refused attempt does not use the player's answer. A second accepted answer is refused (`already_answered`) and doesn't replace the first.
- **Ranking:** smaller `|answer − correct|` wins; at equal closeness the earlier arrival wins, on either side of the correct value. The result depends only on these values, not on record order. Players who didn't answer get no place. With a single answer, only first place is awarded.
- **Follow-ups:**
  - A full tie (same closeness and same arrival) for a needed place gets a new numeric question, only for the tied players and only for the tied places. Places already decided stay.
  - No answers at all gets a new question for the same group.
  - A follow-up is activated immediately with its own new 10 seconds, in the same transaction that closes the previous question.
  - At most three questions per round.
- **End:** the round completes when the needed places are decided, when the limit is reached, or when the bank has no suitable unused question.
  - Missing places stay empty, and `Round.unresolved_reason` records why: `question_limit` (takes precedence), `question_bank_exhausted` or `not_enough_answers`.
  - `winner` is first place, or empty with a reason; a database check enforces that a completed round without a winner has a reason.
  - A completed round can't be closed again (`round_completed`).

### Data

- `Round` gains `participants`, `places_needed` (fixed at creation), `started_at` and `unresolved_reason`.
- `RoundQuestion` is one asked question: its round, a sequence of 1–3, its participant group, the places it decides (`first_place`, `place_count`), status, `started_at`, `deadline`, and a **snapshot** of `text` and `correct_answer`.
  - It also stores `game`, so a unique index can forbid asking a bank question twice in one game.
  - Bank questions that were asked are `PROTECT`ed from deletion; edits to them don't affect asked questions.
- `RoundAnswer` (question, player, value, `received_at`), unique per question and player.
- `RoundPlacement` (round, place, player, deciding question), unique per place and per player.

**Chosen design:** one row per asked question, with a content snapshot and its own participants, places and timing. History is append-only: a follow-up never overwrites earlier answers, and `get_round_state()` rebuilds the current question, remaining time and ranking from rows alone.

**Rejected alternative:** a single "current question" foreign key plus answer columns on `Round`. Every follow-up would overwrite the previous question's data, a tie-break group couldn't be expressed, and a later edit in the bank would silently change how a past round is judged.

### Errors

The caller tells the outcomes apart by exception class and `code` (see M03):

- `NotFoundError`: `round_not_found`, `player_not_found`
- `InvalidInputError`: `invalid_answer`, `player_not_participant`
- `InvalidStateError`: `round_not_started`, `deadline_passed`, `already_answered`, `question_still_open`, `round_completed`, `round_in_progress`, `no_question_available`, `game_not_active`

Example from the project:

```python
>>> services.submit_answer(round_.pk, player.pk, "12.5")
games.exceptions.InvalidInputError: Отговорът трябва да е цяло число.   # .code == "invalid_answer"
```

### Demo

```bash
python backend/manage.py demo_round                     # offsets from the correct answer: 3, -3, 40
python backend/manage.py demo_round --offsets 5 -5 5    # equal closeness: the earlier answer wins
```

Each run creates a new game for the users `demo_red`, `demo_green` and `demo_blue`, plays one round and prints the stored ranking.

### Concurrent answers

Two simultaneous answers from one player are serialized by the game row lock. The second sees the first and is refused with `already_answered`. The unique index on `(question, player)` is a database-level backstop. `test_round_concurrency.py` checks this on real threads, plus the case where the last two answers arrive together and close the question exactly once.

## Territory capture and scoring (M07)

### Capture rights

When a `city_capture` round completes, the same transaction awards the win and creates `CaptureRight` rows (round, player, order, allowed, used). The number of free territories `F` is frozen on the round when it is created, and it also decides the places the round needs.

| Free territories `F` | Places needed | First may pick | Second may pick |
|---|---|---|---|
| 3 or more | 2 | 2 | 1 |
| 2 | 1 | 2 | — |
| 1 | 1 | 1 | — |

- With no winner there are no rights.
- If second place stays unresolved, first keeps both picks, and leftover territories wait for the next round.
- Rights are created once, together with completion. A completed round can't be completed again, and unique indexes on `(round, order)` and `(round, player)` back this up.

### Picking (`capture_territory(game_id, player_id, territory_id)`)

One atomic operation under the game lock. It requires an active game, and the player must hold the first unused right; the other cases are refused with `not_your_turn` or `no_capture_right`. The target must be free (`territory_not_free`), in the same game (`territory_not_in_game`) and adjacent to a territory the player owns, the capital included (`territory_not_adjacent`).

- **Exception:** if the player has no free neighbour at all, any free territory may be picked.
- **Recomputed after every pick:** the winner's second pick may border the territory just taken, and second place picks from what is left.
- `get_capture_options(game_id, player_id)` lists the currently allowed targets.

In one transaction the pick sets the owner, raises `Territory.score`, awards the capture points and uses one right. A refused or failed pick changes nothing and doesn't use a right.

### Phase

- **Blocked:** a new `city_capture` waits while any round is unfinished or any right is unused (`capture_rights_pending`).
- **Refused:** once no territory is free (`no_free_territories`). A full map does not end the game.
- **No winner:** the round distributes nothing.
- **No question:** a missing question blocks creation without changes, and the creation can be retried once the bank grows.

### Scoring

| | System A — flat | System B — territory value (**chosen**) |
|---|---|---|
| Round win | +150 | +100 |
| Territory score on capture | +100 | +100 (`T → T + 100`) |
| Capture points | always +100 | the territory's value **after** the increase, `T + 100` |

Both systems applied to the first two rounds of the demo run below:

| Event | A: green / blue / red | B: green / blue / red |
|---|---|---|
| Round 1 won by green | 150 / 0 / 0 | 100 / 0 / 0 |
| green takes 2, blue takes 1 | 350 / 100 / 0 | 300 / 100 / 0 |
| Round 2 won by blue | 350 / 250 / 0 | 300 / 200 / 0 |
| blue takes 2, red takes 1 | 350 / 450 / 100 | 300 / 400 / 100 |
| *(M08)* blue later conquers a territory worth 100 | +150 win +100 = +250 | +100 win +200 = +300 |

**Why B:**
- **First vs. second:** first earns the win bonus plus up to two captures (up to 300). Second earns only its single capture (100); third earns nothing.
- **Value of a capture:** in A every capture is worth the same. In B a territory's points grow each time it changes hands (100, 200, 300, …), so contested land is worth more.
- **No extra pay for tie-breaks:** follow-up questions pay nothing; the win is paid once per round and each capture once per territory per round, both enforced by partial unique indexes on `ScoreEvent`.
- Scores only grow, and other players' scores are never reduced.

Every change of `Player.score` is a `ScoreEvent` row. It records:

- player, round and territory;
- points;
- player score before and after (a check constraint enforces `after = before + points`);
- territory score before and after;
- the formula used.

### Example with local records

`python backend/manage.py demo_conquest --seed 7` plays rounds until the map is full and prints every `ScoreEvent`. An excerpt from a real run:

```text
Round 1 (12 free, 2 place(s) needed)
  questions: 1, ranking: 1. demo_green, 2. demo_blue
  demo_green победа в рунд: 0 -> 100 (победа = 100)
  demo_green завземане на територия zlaten-grozd: 100 -> 200 (… = 0 + 100 = 100)
  demo_green завземане на територия pelikania: 200 -> 300 (… = 0 + 100 = 100)
  demo_blue завземане на територия kaliakra: 0 -> 100 (… = 0 + 100 = 100)
Round 2 (9 free, 2 place(s) needed)
  questions: 1, ranking: 1. demo_blue, 2. demo_red
  demo_blue победа в рунд: 100 -> 200 (победа = 100)
  demo_blue завземане на територия zhitno-pole: 200 -> 300 (… = 0 + 100 = 100)
  demo_blue завземане на територия dunavia: 300 -> 400 (… = 0 + 100 = 100)
  demo_red завземане на територия sredets: 0 -> 100 (… = 0 + 100 = 100)
...
Round 4 (3 free, 2 place(s) needed)
  demo_blue завземане на територия pirina: 500 -> 600 (… = 0 + 100 = 100)   # no free neighbour: exception applied
```

### Concurrent picks

Picks are serialized by the game row lock. Two simultaneous picks of one free territory end with one success and one `territory_not_free`. Two simultaneous picks with only one right left end with one success and one `no_capture_right`. Both races are covered in `test_capture_concurrency.py`.
