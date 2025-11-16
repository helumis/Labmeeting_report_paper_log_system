# run: python scripts/test_db.py
from app.config import settings
from sqlmodel import create_engine, SQLModel, Session, select
from app.models import User

engine = create_engine(settings.DATABASE_URL)

with Session(engine) as session:
    # try create tables if not exist
    SQLModel.metadata.create_all(engine)
    users = session.exec(select(User)).all()
    print("Users:", users)
