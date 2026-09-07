# v0.1 release checklist

## Repository

- [ ] working tree clean
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` passes
- [ ] `uv run python -m compileall src` passes
- [ ] `git --no-pager diff --check` is silent
- [ ] no `.bak`, secret, runtime, or scratch files are staged

## Core behavior

- [ ] `GET /v1/models` exposes `free-frontier`
- [ ] `GET /v1/models/free-frontier` returns model metadata
- [ ] non-streaming completion works
- [ ] streaming ends with `[DONE]`
- [ ] tool/function call works
- [ ] capability-incompatible route is skipped before inference
- [ ] incompatible capability combinations are skipped before inference
- [ ] fallback and cooldown work
- [ ] pre-stream fallback works
- [ ] paid/ineligible routes are never selected

## Observability

- [ ] `/health` reports readiness
- [ ] `/status` reports request/fallback state
- [ ] `/routes` explains route eligibility and recent fallback state
- [ ] responses include `X-Request-ID` and routing logs carry the same ID
- [ ] final all-routes `503` includes `Retry-After` when cooldown timing is known
- [ ] observability output exposes no credential values or credential environment-variable names
- [ ] known removable top-level provider diagnostics are normalized without breaking tool/reasoning compatibility metadata

## Real consumers

- [ ] Hermes uses `http://127.0.0.1:4000/v1` + `free-frontier`
- [ ] Hermes normal request succeeds
- [ ] Hermes tool-using request succeeds
- [ ] Hermes request survives a controlled provider fallback without Hermes reconfiguration
- [ ] Cline uses OpenAI Compatible + `http://127.0.0.1:4000/v1` + `free-frontier`
- [ ] Cline normal task succeeds
- [ ] Cline tool loop succeeds
- [ ] Cline task survives a controlled provider fallback without Cline reconfiguration

## Provider verification

- [ ] Gemini sample route still exists and is currently free-tier eligible
- [ ] Groq sample route still exists and is currently available under Free Plan limits
- [ ] route capability declarations remain conservative and accurate
- [ ] README billing caveat is still accurate

## Packaging

- [ ] local `uv run free-frontier` workflow works from a clean checkout
- [ ] `docker compose build` succeeds
- [ ] `docker compose up -d` succeeds with local config and credentials
- [ ] host can reach `http://127.0.0.1:4000/health`
- [ ] container publishes port 4000 only on host loopback by default
- [ ] `.env` and `free-frontier.toml` are not baked into the image

## Release

- [ ] update version from prerelease to `0.1.0`
- [ ] update roadmap to mark Phase 5 complete
- [ ] create release commit
- [ ] tag `v0.1.0`
- [ ] push branch and tag
- [ ] create GitHub release notes summarizing the stable logical-model contract
