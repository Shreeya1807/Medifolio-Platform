import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from backend.platform_app import create_app
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-session-only",
            "RECORD_KEY": Fernet.generate_key().decode(),
            "DATABASE_PATH": tmp_path / "records.sqlite",
        }
    )
    with app.extensions["records"].connect() as db:
        for uid, role in [
            ("alice", "patient"),
            ("bobby", "patient"),
            ("doctor", "doctor"),
            ("admin", "admin"),
        ]:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,?)",
                (uid, uid, generate_password_hash("test-password-long"), role),
            )
    return app


def login(app, name):
    client = app.test_client()
    token = client.get("/api/session").json["csrf"]
    result = client.post(
        "/api/login",
        json={"username": name, "password": "test-password-long"},
        headers={"X-CSRF-Token": token},
    )
    assert result.status_code == 200
    return client, {"X-CSRF-Token": result.json["csrf"]}


def create(client, headers):
    result = client.post(
        "/api/patients/alice/records",
        json={
            "title": "Synthetic visit",
            "text": "Synthetic confidential record. Allergy reviewed. Follow-up 2026-11-01.",
        },
        headers=headers,
    )
    assert result.status_code == 200
    return result.json["records"][0]["id"]


def test_role_access_and_revocation(app):
    alice, ah = login(app, "alice")
    doctor, dh = login(app, "doctor")
    bob, bh = login(app, "bobby")
    admin, mh = login(app, "admin")
    rid = create(alice, ah)
    for client in [doctor, bob, admin]:
        assert client.get("/api/records/" + rid).status_code == 404
    assert (
        alice.post(
            "/api/patients/alice/grants", json={"doctor": "doctor"}, headers=ah
        ).status_code
        == 200
    )
    assert doctor.get("/api/records/" + rid).status_code == 200
    assert (
        doctor.post(
            "/api/records/" + rid,
            json={"title": "Edit", "text": "not allowed", "expected_version": 1},
            headers=dh,
        ).status_code
        == 404
    )
    alice.delete("/api/patients/alice/grants", json={"doctor": "doctor"}, headers=ah)
    assert doctor.get("/api/records/" + rid).status_code == 404
    events = alice.get("/api/patients/alice/audit").json["events"]
    assert any(e["actor"] == "doctor" and e["action"] == "record_read" for e in events)
    assert any(e["action"] == "revoke" for e in events)


def test_versions_encryption_and_optimistic_concurrency(app):
    alice, ah = login(app, "alice")
    rid = create(alice, ah)
    update = {
        "title": "Updated visit",
        "text": "Second synthetic version",
        "expected_version": 1,
    }
    assert alice.post("/api/records/" + rid, json=update, headers=ah).status_code == 200
    assert alice.post("/api/records/" + rid, json=update, headers=ah).status_code == 409
    versions = alice.get("/api/records/" + rid).json["versions"]
    assert len(versions) == 2 and "confidential" in versions[1]["text"]
    with app.extensions["records"].connect() as db:
        encrypted = db.execute(
            "SELECT body FROM versions WHERE record=?", (rid,)
        ).fetchone()[0]
        assert "confidential" not in encrypted
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE versions SET title=? WHERE record=?", ("Tamper", rid))


def test_audit_chain_and_immutability(app):
    import hashlib
    import json

    alice, ah = login(app, "alice")
    create(alice, ah)
    with app.extensions["records"].connect() as db:
        previous = "0" * 64
        for row in db.execute("SELECT * FROM audit ORDER BY id"):
            assert row["previous_hash"] == previous
            digest = hashlib.sha256(
                json.dumps(
                    [
                        row[k]
                        for k in [
                            "actor",
                            "action",
                            "patient",
                            "resource",
                            "created",
                            "previous_hash",
                        ]
                    ],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            assert digest == row["hash"]
            previous = digest
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM audit")


def test_csrf_logout_and_consultation_isolation(app):
    alice, ah = login(app, "alice")
    doctor, dh = login(app, "doctor")
    bob, bh = login(app, "bobby")
    assert (
        alice.post("/api/patients/alice/grants", json={"doctor": "doctor"}).status_code
        == 403
    )
    alice.post("/api/patients/alice/grants", json={"doctor": "doctor"}, headers=ah)
    scheduled = (
        (datetime.now(timezone.utc) + timedelta(days=1))
        .replace(minute=0, second=0, microsecond=0)
        .isoformat()
    )
    result = alice.post(
        "/api/appointments",
        json={"doctor": "doctor", "scheduled": scheduled},
        headers=ah,
    )
    assert result.status_code == 200
    aid = result.json["appointments"][0]["id"]
    assert (
        alice.post(
            "/api/appointments",
            json={"doctor": "doctor", "scheduled": scheduled},
            headers=ah,
        ).status_code
        == 409
    )
    socket = app.extensions["socketio"]
    outsider = socket.test_client(
        app, flask_test_client=bob, auth={"csrf": bh["X-CSRF-Token"]}
    )
    peer = socket.test_client(
        app, flask_test_client=doctor, auth={"csrf": dh["X-CSRF-Token"]}
    )
    assert (
        outsider.emit("join_consultation", {"appointment": aid}, callback=True)["ok"]
        is False
    )
    assert peer.emit("join_consultation", {"appointment": aid}, callback=True)["ok"]
    alice.delete("/api/patients/alice/grants", json={"doctor": "doctor"}, headers=ah)
    assert (
        peer.emit(
            "signal", {"appointment": aid, "signal": {"candidate": {}}}, callback=True
        )["ok"]
        is False
    )
    alice.post("/api/logout", json={}, headers=ah)
    assert alice.get("/api/patients").status_code == 401
