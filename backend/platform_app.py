import hashlib
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory, session
from flask_socketio import SocketIO, join_room, leave_room
from werkzeug.security import check_password_hash

from .records import Records, extract_terms


def create_app(config=None):
    from cryptography.fernet import Fernet

    root = Path(os.environ.get("DATA_DIR", "data"))
    root.mkdir(parents=True, exist_ok=True)

    def key(name, generator):
        value = os.environ.get(name)
        if value:
            return value
        path = root / name.lower()
        if not path.exists():
            path.write_text(generator())
        return path.read_text().strip()

    app = Flask(__name__, static_folder=None)
    app.config.update(
        SECRET_KEY=key("SESSION_SECRET", lambda: secrets.token_hex(32)),
        DATABASE_PATH=root / "medifolio.sqlite",
        RECORD_KEY=key("RECORD_KEY", lambda: Fernet.generate_key().decode()),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if config:
        app.config.update(config)
    store, cipher = (
        Records(app.config["DATABASE_PATH"]),
        Fernet(app.config["RECORD_KEY"].encode()),
    )
    socket = SocketIO(app, async_mode="threading", max_http_buffer_size=64000)
    call_sessions = {}
    app.extensions["records"] = store

    def user(db):
        token = hashlib.sha256(session.get("token", "").encode()).hexdigest()
        row = db.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user WHERE token=? AND expires>?",
            (token, time.time()),
        ).fetchone()
        if not row:
            abort(401, "Please sign in")
        return row

    def access(db, actor, patient, write=False):
        permitted = actor["id"] == patient and actor["role"] == "patient"
        if not write and actor["role"] == "doctor":
            permitted = db.execute(
                "SELECT 1 FROM grants WHERE patient=? AND doctor=?",
                (patient, actor["id"]),
            ).fetchone()
        if not permitted:
            abort(404, "Record or patient not available")

    @app.before_request
    def csrf():
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not session.get("csrf") or not secrets.compare_digest(
                session["csrf"], request.headers.get("X-CSRF-Token", "")
            ):
                abort(403, "Refresh the page before submitting")

    @app.after_request
    def protect(response):
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "same-origin",
                "Permissions-Policy": "camera=(self), microphone=(self)",
            }
        )
        return response

    @app.errorhandler(Exception)
    def errors(exc):
        from werkzeug.exceptions import HTTPException

        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        if isinstance(exc, sqlite3.IntegrityError):
            return jsonify(error="Conflicting or invalid change"), 409
        app.logger.exception("Request failed")
        return jsonify(error="Unable to complete the request"), 500

    @app.get("/health/ready")
    def health():
        with store.connect() as db:
            db.execute("SELECT 1")
        return jsonify(status="ready")

    @app.get("/api/session")
    def current():
        session.setdefault("csrf", secrets.token_urlsafe(24))
        with store.connect() as db:
            try:
                actor = user(db)
                profile = {k: actor[k] for k in ("id", "name", "role")}
            except Exception:
                profile = None
        return jsonify(user=profile, csrf=session["csrf"])

    @app.post("/api/login")
    def login():
        data = request.get_json() or {}
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Persisted attempt budget shared by API threads and retained across restarts.
            bucket = (
                datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
            )
            recent = db.execute(
                "SELECT COUNT(*) FROM audit WHERE action='login_attempt' AND resource=? AND created>=?",
                (request.remote_addr, bucket),
            ).fetchone()[0]
            if recent >= 20:
                abort(429, "Too many sign-in attempts; retry in a minute")
            store.log(db, "anonymous", "login_attempt", resource=request.remote_addr)
            actor = db.execute(
                "SELECT * FROM users WHERE id=?", (str(data.get("username", "")),)
            ).fetchone()
            valid = actor and check_password_hash(
                actor["password"], str(data.get("password", ""))
            )
        if not valid:
            abort(401, "Invalid credentials")
        session.clear()
        session.permanent = True
        session["token"], session["csrf"] = (
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(24),
        )
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (
                    hashlib.sha256(session["token"].encode()).hexdigest(),
                    actor["id"],
                    time.time() + 8 * 3600,
                ),
            )
            store.log(db, actor["id"], "login")
        return jsonify(
            user={k: actor[k] for k in ("id", "name", "role")}, csrf=session["csrf"]
        )

    @app.post("/api/logout")
    def logout():
        with store.connect() as db:
            actor = user(db)
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "DELETE FROM sessions WHERE token=?",
                (hashlib.sha256(session["token"].encode()).hexdigest(),),
            )
            store.log(db, actor["id"], "logout")
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/patients")
    def patients():
        with store.connect() as db:
            actor = user(db)
            if actor["role"] == "patient":
                rows = [actor]
            elif actor["role"] == "doctor":
                rows = db.execute(
                    "SELECT users.* FROM users JOIN grants ON users.id=grants.patient WHERE grants.doctor=?",
                    (actor["id"],),
                ).fetchall()
            else:
                rows = []
        return jsonify(patients=[{k: r[k] for k in ("id", "name")} for r in rows])

    @app.get("/api/doctors")
    def doctors():
        with store.connect() as db:
            user(db)
            rows = db.execute(
                "SELECT id,name FROM users WHERE role='doctor'"
            ).fetchall()
        return jsonify(doctors=[dict(r) for r in rows])

    @app.route("/api/patients/<patient>/grants", methods=["GET", "POST", "DELETE"])
    def grants(patient):
        with store.connect() as db:
            actor = user(db)
            access(db, actor, patient, write=True)
            if request.method != "GET":
                doctor = str((request.get_json() or {}).get("doctor", ""))
                if not db.execute(
                    "SELECT 1 FROM users WHERE id=? AND role='doctor'", (doctor,)
                ).fetchone():
                    abort(400, "Select a doctor")
                db.execute("BEGIN IMMEDIATE")
                if request.method == "POST":
                    db.execute(
                        "INSERT OR IGNORE INTO grants VALUES(?,?)", (patient, doctor)
                    )
                else:
                    db.execute(
                        "DELETE FROM grants WHERE patient=? AND doctor=?",
                        (patient, doctor),
                    )
                store.log(
                    db,
                    actor["id"],
                    "grant" if request.method == "POST" else "revoke",
                    patient,
                    doctor,
                )
            rows = db.execute(
                "SELECT doctor FROM grants WHERE patient=?", (patient,)
            ).fetchall()
        return jsonify(doctors=[r["doctor"] for r in rows])

    def content():
        data = request.get_json() or {}
        title, text = (
            str(data.get("title", "")).strip(),
            str(data.get("text", "")).strip(),
        )
        if not 1 <= len(title) <= 120 or not 1 <= len(text) <= 24000:
            abort(
                400,
                "Provide a title (1–120 characters) and record text (1–24,000 characters)",
            )
        return title, cipher.encrypt(
            json.dumps({"text": text, "index": extract_terms(text)}).encode()
        ).decode()

    @app.route("/api/patients/<patient>/records", methods=["GET", "POST"])
    def records(patient):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = user(db)
            access(db, actor, patient, write=request.method == "POST")
            if request.method == "POST":
                title, body = content()
                rid = secrets.token_urlsafe(16)
                now = datetime.now(timezone.utc).isoformat()
                db.execute("INSERT INTO records VALUES(?,?,?)", (rid, patient, now))
                db.execute(
                    "INSERT INTO versions VALUES(?,?,?,?,?,?)",
                    (rid, 1, title, body, actor["id"], now),
                )
                store.log(db, actor["id"], "record_create", patient, rid)
            else:
                store.log(db, actor["id"], "record_list", patient)
            rows = db.execute(
                "SELECT r.id,v.title,v.version,v.created FROM records r JOIN versions v ON v.record=r.id WHERE r.patient=? AND v.version=(SELECT MAX(version) FROM versions WHERE record=r.id) ORDER BY v.created DESC",
                (patient,),
            ).fetchall()
        return jsonify(records=[dict(r) for r in rows])

    @app.route("/api/records/<rid>", methods=["GET", "POST"])
    def record(rid):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = user(db)
            owner = db.execute(
                "SELECT patient FROM records WHERE id=?", (rid,)
            ).fetchone()
            if not owner:
                abort(404)
            access(db, actor, owner["patient"], write=request.method == "POST")
            latest = db.execute(
                "SELECT MAX(version) FROM versions WHERE record=?", (rid,)
            ).fetchone()[0]
            if request.method == "POST":
                if (request.get_json() or {}).get("expected_version") != latest:
                    abort(409, "Record changed; reload before creating a new version")
                title, body = content()
                db.execute(
                    "INSERT INTO versions VALUES(?,?,?,?,?,?)",
                    (
                        rid,
                        latest + 1,
                        title,
                        body,
                        actor["id"],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                store.log(db, actor["id"], "record_version", owner["patient"], rid)
            else:
                store.log(db, actor["id"], "record_read", owner["patient"], rid)
            rows = db.execute(
                "SELECT * FROM versions WHERE record=? ORDER BY version DESC", (rid,)
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item.update(json.loads(cipher.decrypt(item.pop("body").encode())))
                result.append(item)
        return jsonify(id=rid, patient=owner["patient"], versions=result)

    @app.get("/api/patients/<patient>/audit")
    def audit(patient):
        with store.connect() as db:
            actor = user(db)
            access(db, actor, patient, write=True)
            rows = db.execute(
                "SELECT actor,action,resource,created,hash FROM audit WHERE patient=? ORDER BY id DESC LIMIT 200",
                (patient,),
            ).fetchall()
        return jsonify(events=[dict(r) for r in rows])

    @app.route("/api/appointments", methods=["GET", "POST"])
    def appointments():
        with store.connect() as db:
            actor = user(db)
            if request.method == "POST":
                if actor["role"] != "patient":
                    abort(403, "Patients schedule consultations")
                data = request.get_json() or {}
                doctor = str(data.get("doctor", ""))
                if not db.execute(
                    "SELECT 1 FROM grants WHERE patient=? AND doctor=?",
                    (actor["id"], doctor),
                ).fetchone():
                    abort(400, "Share access with this doctor first")
                try:
                    scheduled = datetime.fromisoformat(
                        str(data.get("scheduled", "")).replace("Z", "+00:00")
                    )
                except ValueError:
                    abort(400, "Choose a valid time")
                if scheduled.tzinfo is None or not datetime.now(
                    timezone.utc
                ) < scheduled < datetime.now(timezone.utc) + timedelta(days=90):
                    abort(400, "Choose a time within the next 90 days")
                scheduled = scheduled.astimezone(timezone.utc).replace(
                    second=0, microsecond=0
                )
                if scheduled.minute % 30:
                    abort(400, "Choose a half-hour slot")
                db.execute("BEGIN IMMEDIATE")
                aid = secrets.token_urlsafe(16)
                db.execute(
                    "INSERT INTO appointments(id,patient,doctor,scheduled) VALUES(?,?,?,?)",
                    (aid, actor["id"], doctor, scheduled.isoformat()),
                )
                store.log(db, actor["id"], "appointment_create", actor["id"], aid)
            rows = db.execute(
                "SELECT * FROM appointments WHERE patient=? OR doctor=? ORDER BY scheduled",
                (actor["id"], actor["id"]),
            ).fetchall()
        return jsonify(appointments=[dict(r) for r in rows])

    def consultation(aid):
        with store.connect() as db:
            actor = user(db)
            room = db.execute(
                "SELECT * FROM appointments WHERE id=?", (aid,)
            ).fetchone()
            if not room or actor["id"] not in (room["patient"], room["doctor"]):
                abort(404)
            if not db.execute(
                "SELECT 1 FROM grants WHERE patient=? AND doctor=?",
                (room["patient"], room["doctor"]),
            ).fetchone():
                abort(403)
            return actor["id"], dict(room)

    @socket.on("connect")
    def connect(auth):
        try:
            with store.connect() as db:
                user(db)
            return bool(
                auth
                and secrets.compare_digest(
                    str(auth.get("csrf", "")), session.get("csrf", "missing")
                )
            )
        except Exception:
            return False

    @socket.on("disconnect")
    def disconnect(reason=None):
        call_sessions.pop(request.sid, None)

    @socket.on("join_consultation")
    def join(data):
        try:
            actor, room = consultation(str(data.get("appointment", "")))
            join_room(room["id"])
            call_sessions[request.sid] = {
                "appointment": room["id"],
                "user": actor,
                "token": hashlib.sha256(session.get("token", "").encode()).hexdigest(),
            }
            socket.emit(
                "peer_ready",
                {"appointment": room["id"], "peer": actor},
                to=room["id"],
                include_self=False,
            )
            return {"ok": True, "initiator": actor == room["patient"]}
        except Exception:
            return {"ok": False, "error": "Consultation unavailable"}

    @socket.on("signal")
    def signal(data):
        try:
            actor, room = consultation(str(data.get("appointment", "")))
            payload = data.get("signal")
            if not isinstance(payload, dict) or len(json.dumps(payload)) > 32000:
                return {"ok": False}
            # Recheck receiving sessions too: a revoked/logged-out socket must not receive signaling.
            with store.connect() as db:
                for sid, peer in list(call_sessions.items()):
                    if (
                        sid == request.sid
                        or peer["appointment"] != room["id"]
                        or peer["user"] == actor
                    ):
                        continue
                    valid = db.execute(
                        "SELECT 1 FROM sessions WHERE token=? AND expires>?",
                        (peer["token"], time.time()),
                    ).fetchone()
                    if valid:
                        socket.emit(
                            "signal",
                            {
                                "appointment": room["id"],
                                "signal": payload,
                                "peer": actor,
                            },
                            to=sid,
                        )
            return {"ok": True}
        except Exception:
            return {"ok": False}

    @socket.on("leave_consultation")
    def leave(data):
        try:
            _, room = consultation(str(data.get("appointment", "")))
            call_sessions.pop(request.sid, None)
            leave_room(room["id"])
            socket.emit("peer_left", {}, to=room["id"])
        except Exception:
            pass

    @app.get("/api/media-config")
    def media():
        with store.connect() as db:
            user(db)
        servers = [{"urls": "stun:stun.l.google.com:19302"}]
        if os.environ.get("TURN_URL"):
            servers.append(
                {
                    "urls": os.environ["TURN_URL"],
                    "username": os.environ.get("TURN_USERNAME", ""),
                    "credential": os.environ.get("TURN_CREDENTIAL", ""),
                }
            )
        return jsonify(iceServers=servers)

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path="index.html"):
        if path.startswith("api/"):
            abort(404)
        return send_from_directory(
            Path(__file__).resolve().parents[1] / "frontend" / "dist", path
        )

    return app
