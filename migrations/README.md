# Migration Note

The v0.3.5 Docker demonstration does **not** run schema changes under the API runtime role.

`app.migrate` is a short-lived migration container that receives only the PostgreSQL admin secret and applies the idempotent `postgres/schema.sql` hardening script. The API starts only after that service completes successfully.

The Alembic revision files in `migrations/versions/` are retained as version-history/reference artifacts; they are not the active Docker bootstrap mechanism for v0.3.5.
