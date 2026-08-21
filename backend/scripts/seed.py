"""Demo verisi: kullanıcılar ve örnek anonim çalışma.

Kullanım: PYTHONPATH=backend python backend/scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User, init_db, make_engine  # noqa: E402

DEMO_USERS = [
    ("admin@pulsar.demo", "admin-demo-1234", "admin"),
    ("hekim@pulsar.demo", "hekim-demo-1234", "hekim"),
    ("radyolog@pulsar.demo", "radyolog-demo-1234", "radyolog"),
    ("asistan@pulsar.demo", "asistan-demo-1234", "asistan"),
]


def main() -> None:
    engine = make_engine(settings.database_url)
    init_db(engine)
    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=engine)()
    for email, password, role in DEMO_USERS:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            print(f"+ {email} ({role})")
    db.commit()
    print("Seed tamam.")


if __name__ == "__main__":
    main()
