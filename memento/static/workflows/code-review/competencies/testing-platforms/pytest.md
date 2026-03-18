# pytest Platform Rules

## pytest + Django/FastAPI

- Tests don't touch dev database; use test DB or `--reuse-db`
- Use fixtures and `@pytest.mark.parametrize` for readability and DRY
- Async tests marked with `@pytest.mark.asyncio`; no sync I/O blocking event loop
- External calls mocked/stubbed (LLM providers, object storage, third-party HTTP)

### Django specifics

- Prefer `pytest` fixtures over `TestCase.setUp`; use `@pytest.mark.django_db`
- Use `override_settings` for config-dependent tests
- Use factory_boy or model_bakery for test data, not raw `Model.objects.create`

### FastAPI specifics

- Use `TestClient` for sync endpoints, `httpx.AsyncClient` for async
- Override dependencies via `app.dependency_overrides`
- Test Pydantic validation with invalid inputs

### Celery/background tasks

- Verify task idempotency and side effects
- No time-based sleeps in task tests; use `CELERY_ALWAYS_EAGER` or mock
