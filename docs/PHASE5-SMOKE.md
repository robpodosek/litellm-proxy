# Phase 5 smoke test

Phase 5 is complete only after two real consumer applications use the same Free Frontier
endpoint and logical model.

## 1. Start Free Frontier

```bash
uv run free-frontier
```

Verify:

```bash
curl -s http://127.0.0.1:4000/health | python -m json.tool
curl -s http://127.0.0.1:4000/v1/models | python -m json.tool
```

## 2. Hermes

Follow `docs/integrations/HERMES.md`.

Acceptance evidence:

- Hermes is configured only with `http://127.0.0.1:4000/v1` and `free-frontier`
- a normal one-shot succeeds
- a tool-using turn succeeds
- a controlled first-route failure still succeeds through the second route
- Hermes configuration does not change during fallback

## 3. Cline

Follow `docs/integrations/CLINE.md`.

Acceptance evidence:

- API Provider is OpenAI Compatible
- Base URL is `http://127.0.0.1:4000/v1`
- Model ID is `free-frontier`
- a small read-only task succeeds
- a normal Cline tool loop succeeds
- a controlled first-route failure still succeeds through the second route
- Cline configuration does not change during fallback

## 4. Docker

With local `.env` and `free-frontier.toml` already configured:

```bash
docker compose build
docker compose up -d
```

Then:

```bash
curl -s http://127.0.0.1:4000/health | python -m json.tool
docker compose ps
docker compose logs --tail=50 free-frontier
```

Stop it with:

```bash
docker compose down
```

The compose file binds host port 4000 to `127.0.0.1` by default. The process binds to
`0.0.0.0` only inside the container so Docker port forwarding works.

## 5. Final release gate

Run:

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src
git --no-pager diff --check
```

Then complete `docs/RELEASE-CHECKLIST.md`.

## Hardening checks

Model-detail discovery:

```bash
curl -i http://127.0.0.1:4000/v1/models/free-frontier
```

Confirm the response contains `X-Request-ID` and the body names only `free-frontier`.

When testing an exhausted free pool, inspect the final `503` headers:

```bash
curl -i http://127.0.0.1:4000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"free-frontier","messages":[{"role":"user","content":"ping"}]}'
```

If compatible routes are cooling down with known expiry, the response should include
`Retry-After`. The corresponding route logs should all carry the same `request=...` value.
