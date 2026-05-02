# Expedition Service

Small FastAPI backend service for managing expeditions.

The service supports:

- JWT-protected REST API.
- Passwordless demo authentication for the test task.
- Users with `chief` and `member` roles.
- Expedition lifecycle: `draft -> ready -> active -> finished`.
- Member invitations and participation confirmation.
- Real-time expedition events through WebSocket.
- Local SQLite database through SQLAlchemy Async.

## Tech Stack

- Python 3.13
- FastAPI
- SQLAlchemy Async
- SQLite with `aiosqlite`
- JWT with `python-jose`
- Pytest integration tests
- Docker runtime image

## Authentication

Registration requires:

- `email`
- `name`
- `role`

Login requires `email`.

There are no passwords intentionally. This is a test-task shortcut to keep the sample focused on the expedition domain
instead of password fields, hashing, and password validation flows.

REST endpoints require a JWT bearer token, except `/auth/register` and `/auth/login`.

WebSocket authorization is passed through the `token` query parameter:

```text
ws://localhost:8080/ws/expeditions?token=<access_token>
```

## Local Run

Install dependencies and run the service:

```powershell
uv run python run_local.py
```

Default local URL:

```text
http://127.0.0.1:8080
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8080/docs
```

The local database is created automatically as:

```text
expedition_service.db
```

The port can be changed with `SERVICE_PORT`:

```powershell
$env:SERVICE_PORT = "9000"
uv run python run_local.py
```

## Docker Run

Build the image:

```powershell
docker build -f docker/Dockerfile -t expedition-service .
```

Run the container:

```powershell
docker run --rm -p 8080:8080 expedition-service
```

The container runs:

```text
uvicorn run_local:app --host 0.0.0.0 --port 8080
```

## Tests

Run integration tests:

```powershell
uv run --group dev pytest tests
```

The tests use FastAPI `TestClient`, so the service does not need to be hosted separately.
Each test creates its own temporary SQLite database.

## Performance Tests

Run the local domain-load scenario:

```powershell
uv run --group dev pytest performance_tests -s
```

The test starts a local `uvicorn` server and runs expedition teams concurrently.
The default scenario runs 40 teams. Each team creates:

- 1 chief user
- 1 expedition
- 20 invited member users
- 15 confirmed members
- full lifecycle: `draft -> ready -> active -> finished`

The output includes total HTTP requests, elapsed time, RPS, p95 request latency, p95 team latency, status codes, and error count.

Default load settings can be changed with environment variables:

```powershell
$env:LOAD_TEAM_COUNT = "40"
$env:LOAD_INVITED_MEMBERS_PER_TEAM = "20"
$env:LOAD_CONFIRMED_MEMBERS_PER_TEAM = "15"
uv run --group dev pytest performance_tests -s
```
