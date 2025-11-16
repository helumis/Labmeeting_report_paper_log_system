# Lab Reports (FastAPI + SQLModel + Postgres)

## Quick start (Mac M4)
1. copy `.env.example` -> `.env` and set POSTGRES_PASSWORD and SECRET_KEY.
2. build & start:
   docker compose up -d --build

3. open browser:
   http://localhost:8000/

4. logs:
   docker compose logs -f web

## Notes
- This project uses SQLModel (SQLAlchemy), SQLModel.metadata.create_all for simple migration.
- For production, replace create_all with Alembic migrations and use secure auth.
