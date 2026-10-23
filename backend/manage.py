import argparse
import getpass

from werkzeug.security import generate_password_hash

from .platform_app import create_app

parser = argparse.ArgumentParser(description="Provision local Medifolio accounts")
parser.add_argument(
    "--demo",
    action="store_true",
    help="Create named synthetic demo accounts with a password you supply",
)
parser.add_argument("--username")
parser.add_argument("--name")
parser.add_argument("--role", choices=["patient", "doctor", "admin"], default="patient")
args = parser.parse_args()
password = getpass.getpass("Choose password (10+ characters): ")
if len(password) < 10:
    raise SystemExit("Use at least 10 characters")
users = (
    [
        ("patient_demo", "Alex Morgan", "patient"),
        ("doctor_demo", "Dr. Taylor", "doctor"),
    ]
    if args.demo
    else [(args.username, args.name, args.role)]
)
if any(not name or not title for name, title, _ in users):
    raise SystemExit("Provide --username and --name or use --demo")
app = create_app()
with app.extensions["records"].connect() as db:
    for username, name, role in users:
        db.execute(
            "INSERT INTO users VALUES(?,?,?,?)",
            (username, name, generate_password_hash(password), role),
        )
        app.extensions["records"].log(db, "operator", "user_create", resource=username)
print("Created accounts: " + ", ".join(row[0] for row in users))
