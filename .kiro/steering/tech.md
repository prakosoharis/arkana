# ARKANA technology and working conventions

- Frontend: Next.js 15, TypeScript, Vitest, ESLint.
- Backend: FastAPI, SQLAlchemy, PostgreSQL in Docker; isolated SQLite for tests.
- Local services: `docker compose up -d --build`; web is port 3000 and research
  is port 8001.
- Use existing modules and contracts before adding abstractions or infrastructure.
- Apply schema/API changes with migrations and regression tests.
- Do not put secrets in source, Markdown, browser code, test output, or git.
- Keep AI provider configuration server-side and provider-agnostic.

Verification before handoff:

1. relevant Python tests in isolated SQLite;
2. frontend tests, lint, and typecheck when web changes;
3. production build for affected frontend changes;
4. report tests that cannot be run honestly.
