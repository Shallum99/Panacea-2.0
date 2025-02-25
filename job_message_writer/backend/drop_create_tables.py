# Create a file at backend/drop_create_tables.py
from app.db.database import engine
from app.db.models import Base

def recreate_tables():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Database tables dropped and recreated successfully!")

if __name__ == "__main__":
    recreate_tables()