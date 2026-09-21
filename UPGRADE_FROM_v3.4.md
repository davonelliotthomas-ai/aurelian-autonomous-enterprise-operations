# Upgrade from v0.3.4 to v0.3.5

v0.3.5 changes PostgreSQL roles, migration ownership, Docker secrets and network topology. A clean synthetic volume reset is required.

From the project directory:

```bash
# Preserve current local secrets
cp .env ~/.aurelian-demo-env-v34-backup

# Add the new audit-writer secret if absent
grep -q '^POSTGRES_AUDIT_PASSWORD=' .env || echo "POSTGRES_AUDIT_PASSWORD=$(openssl rand -hex 32)" >> .env
chmod 600 .env

# Verify all required variables exist without printing their values
for n in JWT_SECRET AUDIT_SIGNING_KEY INTERNAL_SERVICE_TOKEN POSTGRES_ADMIN_PASSWORD POSTGRES_APP_PASSWORD POSTGRES_AUDIT_PASSWORD; do
  grep -q "^${n}=" .env || { echo "missing $n"; exit 1; }
done

# Clean synthetic state and rebuild the new trust topology
docker compose down -v
docker compose up --build -d

docker compose ps
./scripts/verify_v35.sh
```

Then use the UI to run Behavioral Checks and the adversarial demo sequence in `DEMO_SCRIPT.md`.
