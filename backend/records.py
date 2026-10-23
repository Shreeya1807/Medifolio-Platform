import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Records:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('patient','doctor','admin')));
            CREATE TABLE IF NOT EXISTS grants(patient TEXT NOT NULL REFERENCES users(id), doctor TEXT NOT NULL REFERENCES users(id), PRIMARY KEY(patient,doctor));
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, patient TEXT NOT NULL REFERENCES users(id), created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions(record TEXT NOT NULL REFERENCES records(id), version INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, author TEXT NOT NULL REFERENCES users(id), created TEXT NOT NULL, PRIMARY KEY(record,version));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL, patient TEXT, resource TEXT, created TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS appointments(id TEXT PRIMARY KEY, patient TEXT NOT NULL REFERENCES users(id), doctor TEXT NOT NULL REFERENCES users(id), scheduled TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled', UNIQUE(doctor,scheduled));
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_version_update BEFORE UPDATE ON versions BEGIN SELECT RAISE(ABORT,'Versions are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_version_delete BEFORE DELETE ON versions BEGIN SELECT RAISE(ABORT,'Versions are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'Audit is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'Audit is append-only'); END;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def log(db, actor, action, patient=None, resource=None):
        from datetime import datetime, timezone

        created = datetime.now(timezone.utc).isoformat()
        previous = db.execute(
            "SELECT hash FROM audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous = previous["hash"] if previous else "0" * 64
        values = [actor, action, patient, resource, created, previous]
        digest = hashlib.sha256(
            json.dumps(values, separators=(",", ":")).encode()
        ).hexdigest()
        db.execute(
            "INSERT INTO audit(actor,action,patient,resource,created,previous_hash,hash) VALUES(?,?,?,?,?,?,?)",
            (*values, digest),
        )


def extract_terms(text):
    """Rule-based indexing, never a diagnosis or prescribing recommendation."""
    terms = sorted(
        set(
            re.findall(
                r"\b(?:allergy|allergies|diabetes|asthma|hypertension|follow.up|vaccination|prescription|blood pressure)\b",
                text,
                re.I,
            )
        )
    )
    dates = sorted(set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)))
    doses = re.findall(
        r"\b([A-Za-z][A-Za-z -]{1,30}?)\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|ml))\b", text, re.I
    )
    return {
        "keywords": terms,
        "dates": dates,
        "dose_mentions": [" ".join(d) for d in doses],
        "notice": "Search aids extracted from your text. Review against the original record; no diagnosis or treatment advice.",
    }
