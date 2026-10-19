# -*- coding: utf-8 -*-
"""
TaskHive — Plan • Study • Achieve
All-in-one student productivity app with Friends, Chat, Group Chat,
and Premium (Admin Approval) system.
Run:  python3 taskhive.py   then open http://localhost:5000
Admin login:  admin@taskhive.com / admin123
"""
import os
import json
import uuid
import hashlib
import datetime
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as pg_errors

from flask import (Flask, render_template_string, request, jsonify, session,
                   redirect, url_for, send_from_directory)
from werkzeug.utils import secure_filename

# ==================== CONFIG ====================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "taskhive-dev-secret-change-me")
# NEON.TECH PostgreSQL connection string.
# Kunin mo ito sa Neon dashboard: Dashboard → your database → Connection string
#   (example: postgresql://user:pass@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require)
# I-set bilang environment variable:  export DATABASE_URL="postgresql://..."
DATABASE_URL = os.environ.get("DATABASE_URL", "")
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB

PREMIUM_PRICE = 50.00
PREMIUM_DAYS = 30
GCASH_NUMBER = "0970-456-XXXX"   # palitan ng tunay na number
GCASH_NAME = "TaskHive Premium"
FREE_FRIEND_LIMIT = 10
ONLINE_WINDOW = 120  # seconds

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ==================== DB HELPERS (PostgreSQL / Neon) ====================
class DBConn:
    """Lightweight wrapper so the rest of the code can keep using conn.execute(..., params)
    with '?' placeholders (auto-converted to psycopg2 '%s'). Rows come back as dict-like."""
    def __init__(self, conn):
        self._conn = conn
    def execute(self, query, params=()):
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query.replace("?", "%s"), params)
        return cur
    def commit(self):
        self._conn.commit()
    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass


def get_db():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL not set! I-set mo ang Neon connection string: "
            "export DATABASE_URL='postgresql://user:pass@host/dbname?sslmode=require'"
        )
    conn = psycopg2.connect(DATABASE_URL)
    return DBConn(conn)


def now_ph():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def fmt(dt=None):
    if dt is None:
        dt = now_ph()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def init_db():
    conn = get_db()
    tables = [
        """CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            student_id TEXT,
            course_year TEXT,
            password_hash TEXT NOT NULL,
            join_date TEXT NOT NULL,
            is_premium INTEGER DEFAULT 0,
            premium_start TEXT,
            premium_expiry TEXT,
            theme TEXT DEFAULT 'light',
            is_admin INTEGER DEFAULT 0,
            last_seen TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            subject TEXT,
            description TEXT,
            due_date TEXT NOT NULL,
            due_time TEXT DEFAULT '23:59',
            priority TEXT DEFAULT 'medium',
            completed INTEGER DEFAULT 0,
            reminder_set INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS schedule (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            day TEXT NOT NULL,
            time_start TEXT NOT NULL,
            time_end TEXT NOT NULL,
            room TEXT,
            color TEXT DEFAULT '#6366F1'
        )""",
        """CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            folder_name TEXT DEFAULT 'General',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            members TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'Ongoing',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS grades (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            score REAL NOT NULL,
            units REAL DEFAULT 3,
            semester TEXT,
            recorded_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS budget (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            recorded_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS planner (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            goal TEXT NOT NULL,
            target_date TEXT,
            progress INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            amount REAL NOT NULL,
            reference_id TEXT UNIQUE NOT NULL,
            gcash_ref TEXT,
            screenshot TEXT,
            status TEXT DEFAULT 'pending',
            submitted_at TEXT,
            reviewed_at TEXT,
            reject_reason TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS friend_requests (
            id SERIAL PRIMARY KEY,
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            UNIQUE(from_user, to_user)
        )""",
        """CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            sender_id TEXT NOT NULL,
            receiver_id TEXT NOT NULL,
            content TEXT NOT NULL,
            sent_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS groups (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS group_members (
            group_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (group_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS group_messages (
            id SERIAL PRIMARY KEY,
            group_id INTEGER NOT NULL,
            sender_id TEXT NOT NULL,
            content TEXT NOT NULL,
            sent_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS typing (
            user_id TEXT NOT NULL,
            conv TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, conv)
        )""",
    ]
    for sql in tables:
        conn.execute(sql)
    # seed admin (Postgres ON CONFLICT)
    conn.execute("""INSERT INTO users
        (user_id, full_name, email, student_id, course_year, password_hash, join_date, is_admin)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT (email) DO NOTHING""",
        ("admin001", "Administrator", "admin@taskhive.com", "ADMIN-001",
         "TaskHive Admin", hash_pw("admin123"), fmt()))
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        touch_last_seen(session["user_id"])
        return f(*a, **kw)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        u = get_user(session["user_id"])
        if not u or not u.get("is_admin"):
            return jsonify({"error": "Forbidden"}), 403
        return f(*a, **kw)
    return wrap


def touch_last_seen(uid):
    try:
        conn = get_db()
        conn.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (fmt(), uid))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_user(uid):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def check_premium(uid):
    u = get_user(uid)
    if not u or not u.get("is_premium") or not u.get("premium_expiry"):
        return False
    try:
        exp = datetime.datetime.strptime(u["premium_expiry"], "%Y-%m-%d %H:%M:%S")
        now = now_ph().replace(tzinfo=None)
        if now > exp:
            conn = get_db()
            conn.execute("UPDATE users SET is_premium=0, premium_start=NULL, premium_expiry=NULL WHERE user_id=?", (uid,))
            conn.commit()
            conn.close()
            return False
    except Exception:
        return False
    return True


def is_online(u):
    if not u or not u.get("last_seen"):
        return False
    try:
        ls = datetime.datetime.strptime(u["last_seen"], "%Y-%m-%d %H:%M:%S")
        return (now_ph().replace(tzinfo=None) - ls).total_seconds() < ONLINE_WINDOW
    except Exception:
        return False


def are_friends(a, b):
    conn = get_db()
    row = conn.execute("""SELECT id FROM friend_requests
        WHERE status='accepted' AND
        ((from_user=? AND to_user=?) OR (from_user=? AND to_user=?))""",
        (a, b, b, a)).fetchone()
    conn.close()
    return row is not None


def friend_count(uid):
    conn = get_db()
    n = conn.execute("""SELECT COUNT(*) AS c FROM friend_requests
        WHERE status='accepted' AND (from_user=? OR to_user=?)""", (uid, uid)).fetchone()["c"]
    conn.close()
    return n


# ==================== ROUTES ====================
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("app_page"))
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    return render_template_string(FRONTEND)


@app.route("/app")
def app_page():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template_string(FRONTEND)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------- AUTH ----------
@app.route("/api/register", methods=["POST"])
def register():
    d = request.get_json(silent=True) or {}
    required = ["full_name", "email", "student_id", "course_year", "password"]
    for f in required:
        if not d.get(f, "").strip():
            return jsonify({"success": False, "error": "All fields are required"})
    if d["password"] != d.get("confirm_password", ""):
        return jsonify({"success": False, "error": "Passwords do not match"})
    if len(d["password"]) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"})
    conn = get_db()
    try:
        uid = str(uuid.uuid4())[:8]
        conn.execute("""INSERT INTO users
            (user_id, full_name, email, student_id, course_year, password_hash, join_date)
            VALUES (?,?,?,?,?,?,?)""",
            (uid, d["full_name"].strip(), d["email"].strip().lower(),
             d["student_id"].strip(), d["course_year"].strip(),
             hash_pw(d["password"]), fmt()))
        conn.commit()
        return jsonify({"success": True})
    except pg_errors.UniqueViolation:
        conn.rollback()
        return jsonify({"success": False, "error": "Email already registered"})
    finally:
        conn.close()


@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    remember = bool(d.get("remember"))
    u = get_user_by_email(email)
    if not u or u["password_hash"] != hash_pw(pw):
        return jsonify({"success": False, "error": "Invalid email or password"})
    session["user_id"] = u["user_id"]
    session.permanent = remember
    touch_last_seen(u["user_id"])
    return jsonify({"success": True, "user_id": u["user_id"], "name": u["full_name"]})


def get_user_by_email(email):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


@app.route("/api/user", methods=["GET"])
@login_required
def api_user():
    u = get_user(session["user_id"])
    if not u:
        return jsonify({"error": "User not found"}), 404
    is_prem = check_premium(u["user_id"])
    return jsonify({
        "full_name": u["full_name"], "email": u["email"],
        "student_id": u["student_id"], "course_year": u["course_year"],
        "join_date": u["join_date"], "is_premium": is_prem,
        "premium_expiry": u.get("premium_expiry") if is_prem else None,
        "theme": u.get("theme", "light"), "is_admin": bool(u.get("is_admin")),
        "friend_limit": None if is_prem else FREE_FRIEND_LIMIT,
        "friend_count": friend_count(u["user_id"]),
    })


@app.route("/api/user/theme", methods=["POST"])
@login_required
def set_theme():
    theme = (request.get_json(silent=True) or {}).get("theme", "light")
    conn = get_db()
    conn.execute("UPDATE users SET theme=? WHERE user_id=?", (theme, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ---------- GENERIC CRUD helper ----------
def crud(table, fields, order_by=None, premium=False):
    def view():
        uid = session["user_id"]
        if premium and not check_premium(uid):
            return jsonify({"error": "Premium required", "premium_required": True}), 403
        conn = get_db()
        if request.method == "GET":
            q = f"SELECT * FROM {table} WHERE user_id=?"
            if order_by:
                q += f" ORDER BY {order_by}"
            rows = conn.execute(q, (uid,)).fetchall()
            conn.close()
            return jsonify([dict(r) for r in rows])
        elif request.method == "POST":
            d = request.get_json(silent=True) or {}
            cols = ", ".join(fields)
            ph = ", ".join(["?"] * (len(fields) + 1))
            vals = [uid] + [d.get(f, "") for f in fields]
            if "created_at" in fields:
                vals[fields.index("created_at") + 1] = fmt()
            if "recorded_at" in fields:
                vals[fields.index("recorded_at") + 1] = fmt()
            cur = conn.execute(f"INSERT INTO {table} (user_id, {cols}) VALUES ({ph}) RETURNING id", vals)
            new_id = cur.fetchone()["id"]
            conn.commit()
            conn.close()
            return jsonify({"success": True, "id": new_id})
        elif request.method == "PUT":
            d = request.get_json(silent=True) or {}
            sets = []
            vals = []
            for k, v in d.items():
                if k != "id":
                    sets.append(f"{k}=?")
                    vals.append(v)
            vals += [d.get("id"), uid]
            conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id=? AND user_id=?", vals)
            conn.commit()
            conn.close()
            return jsonify({"success": True})
        elif request.method == "DELETE":
            rid = request.args.get("id")
            conn.execute(f"DELETE FROM {table} WHERE id=? AND user_id=?", (rid, uid))
            conn.commit()
            conn.close()
            return jsonify({"success": True})
    view.__name__ = "view_" + table
    return login_required(view)


app.add_url_rule("/api/tasks", view_func=crud("tasks",
    ["title", "subject", "description", "due_date", "due_time", "priority", "reminder_set", "created_at"],
    order_by="due_date ASC, priority DESC"), methods=["GET", "POST", "PUT", "DELETE"])
app.add_url_rule("/api/schedule", view_func=crud("schedule",
    ["subject", "day", "time_start", "time_end", "room", "color"],
    order_by="time_start"), methods=["GET", "POST", "PUT", "DELETE"])
app.add_url_rule("/api/notes", view_func=crud("notes",
    ["title", "content", "folder_name", "created_at", "updated_at"],
    order_by="updated_at DESC"), methods=["GET", "POST", "PUT", "DELETE"])
app.add_url_rule("/api/projects", view_func=crud("projects",
    ["name", "members", "deadline", "status", "created_at"],
    order_by="created_at DESC"), methods=["GET", "POST", "PUT", "DELETE"])
app.add_url_rule("/api/grades", view_func=crud("grades",
    ["subject", "score", "units", "semester", "recorded_at"],
    order_by="recorded_at DESC"), methods=["GET", "POST", "PUT", "DELETE"])
app.add_url_rule("/api/budget", view_func=crud("budget",
    ["type", "category", "amount", "description", "recorded_at"],
    order_by="recorded_at DESC", premium=True), methods=["GET", "POST", "PUT", "DELETE"])
app.add_url_rule("/api/planner", view_func=crud("planner",
    ["goal", "target_date", "progress", "created_at"],
    order_by="created_at DESC"), methods=["GET", "POST", "PUT", "DELETE"])


# ---------- PREMIUM / PAYMENT (Admin Approval) ----------
@app.route("/api/premium/request", methods=["POST"])
@login_required
def premium_request():
    uid = session["user_id"]
    conn = get_db()
    row = conn.execute("""SELECT reference_id FROM payments
        WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1""", (uid,)).fetchone()
    if row:
        ref = row["reference_id"]
    else:
        ref = f"TH-{uid}-{str(uuid.uuid4())[:6].upper()}"
        conn.execute("""INSERT INTO payments (user_id, amount, reference_id, status)
            VALUES (?,?,?,'pending')""", (uid, PREMIUM_PRICE, ref))
        conn.commit()
    conn.close()
    return jsonify({"success": True, "reference_id": ref, "amount": PREMIUM_PRICE,
                    "gcash_number": GCASH_NUMBER, "gcash_name": GCASH_NAME})


@app.route("/api/premium/submit", methods=["POST"])
@login_required
def premium_submit():
    uid = session["user_id"]
    ref = (request.form.get("reference_id") or "").strip()
    gcash_ref = (request.form.get("gcash_ref") or "").strip()
    if not ref:
        return jsonify({"success": False, "error": "Reference ID required"})
    if not gcash_ref:
        return jsonify({"success": False, "error": "GCash reference number required"})
    screenshot = None
    f = request.files.get("screenshot")
    if f and f.filename and allowed_file(f.filename):
        ext = f.filename.rsplit(".", 1)[1].lower()
        fn = f"{uuid.uuid4().hex}.{ext}"
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
        screenshot = fn
    conn = get_db()
    row = conn.execute("SELECT id, status FROM payments WHERE reference_id=? AND user_id=?", (ref, uid)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Reference ID not found"})
    if row["status"] == "approved":
        conn.close()
        return jsonify({"success": False, "error": "Already approved"})
    conn.execute("""UPDATE payments SET gcash_ref=?, screenshot=?, status='pending', submitted_at=?
        WHERE id=?""", (gcash_ref, screenshot, fmt(), row["id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Submitted! Waiting for admin approval."})


@app.route("/api/premium/status", methods=["GET"])
@login_required
def premium_status():
    uid = session["user_id"]
    is_prem = check_premium(uid)
    u = get_user(uid)
    days_left = 0
    if is_prem and u.get("premium_expiry"):
        try:
            exp = datetime.datetime.strptime(u["premium_expiry"], "%Y-%m-%d %H:%M:%S")
            days_left = max(0, (exp - now_ph().replace(tzinfo=None)).days)
        except Exception:
            pass
    conn = get_db()
    rows = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 3", (uid,)).fetchall()
    conn.close()
    return jsonify({
        "is_premium": is_prem, "days_left": days_left,
        "expiry_date": u.get("premium_expiry") if is_prem else None,
        "payments": [dict(r) for r in rows], "price": PREMIUM_PRICE,
    })


# ---------- ADMIN ----------
@app.route("/api/admin/pending", methods=["GET"])
@admin_required
def admin_pending():
    conn = get_db()
    rows = conn.execute("""SELECT p.*, u.full_name, u.email, u.student_id
        FROM payments p JOIN users u ON p.user_id = u.user_id
        WHERE p.status='pending' AND p.submitted_at IS NOT NULL
        ORDER BY p.submitted_at ASC""").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/all-payments", methods=["GET"])
@admin_required
def admin_all_payments():
    conn = get_db()
    rows = conn.execute("""SELECT p.*, u.full_name FROM payments p
        JOIN users u ON p.user_id=u.user_id ORDER BY p.id DESC LIMIT 200""").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/approve", methods=["POST"])
@admin_required
def admin_approve():
    pid = (request.get_json(silent=True) or {}).get("payment_id")
    conn = get_db()
    row = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Not found"}), 404
    now = now_ph().replace(tzinfo=None)
    u = get_user(row["user_id"])
    start = now
    if u and u.get("premium_expiry"):
        try:
            old = datetime.datetime.strptime(u["premium_expiry"], "%Y-%m-%d %H:%M:%S")
            if old > now:
                start = old
        except Exception:
            pass
    exp = start + datetime.timedelta(days=PREMIUM_DAYS)
    conn.execute("UPDATE users SET is_premium=1, premium_start=COALESCE(premium_start,?), premium_expiry=? WHERE user_id=?",
                 (fmt(now), fmt(exp), row["user_id"]))
    conn.execute("UPDATE payments SET status='approved', reviewed_at=? WHERE id=?", (fmt(), pid))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Premium activated", "expiry": fmt(exp)})


@app.route("/api/admin/reject", methods=["POST"])
@admin_required
def admin_reject():
    d = request.get_json(silent=True) or {}
    pid = d.get("payment_id")
    reason = (d.get("reason") or "Payment could not be verified.").strip()
    conn = get_db()
    conn.execute("UPDATE payments SET status='rejected', reviewed_at=?, reject_reason=? WHERE id=?",
                 (fmt(), reason, pid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_users():
    conn = get_db()
    rows = conn.execute("""SELECT user_id, full_name, email, student_id, course_year,
        is_premium, premium_expiry, join_date, last_seen FROM users WHERE is_admin=0
        ORDER BY join_date DESC""").fetchall()
    conn.close()
    out = []
    for r in rows:
        r = dict(r)
        r["is_premium"] = bool(r["is_premium"]) and check_premium(r["user_id"])
        out.append(r)
    return jsonify(out)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------- EXPORT (Premium) ----------
@app.route("/api/export")
@login_required
def export_csv():
    if not check_premium(session["user_id"]):
        return jsonify({"error": "Premium required"}), 403
    uid = session["user_id"]
    conn = get_db()
    tasks = conn.execute("SELECT * FROM tasks WHERE user_id=? ORDER BY due_date", (uid,)).fetchall()
    conn.close()
    lines = ["Title,Subject,Due Date,Due Time,Priority,Completed"]
    for t in tasks:
        lines.append(f'"{t["title"]}","{t["subject"] or ""}",{t["due_date"]},{t["due_time"]},{t["priority"]},{t["completed"]}')
    csv = "\n".join(lines)
    from flask import Response
    return Response(csv, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=taskhive_tasks.csv"})


# ---------- FRIENDS ----------
@app.route("/api/users/search")
@login_required
def search_users():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    uid = session["user_id"]
    conn = get_db()
    rows = conn.execute("""SELECT user_id, full_name, student_id, course_year, last_seen
        FROM users WHERE is_admin=0 AND user_id != ? AND
        (full_name LIKE ? OR student_id LIKE ? OR email LIKE ?) LIMIT 20""",
        (uid, f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    conn.close()
    out = []
    for r in rows:
        r = dict(r)
        r["online"] = is_online(r)
        r["are_friends"] = are_friends(uid, r["user_id"])
        out.append(r)
    return jsonify(out)


@app.route("/api/friends/requests", methods=["GET", "POST"])
@login_required
def friend_requests_api():
    uid = session["user_id"]
    conn = get_db()
    if request.method == "GET":
        rows = conn.execute("""SELECT fr.*, u.full_name, u.student_id, u.course_year, u.last_seen
            FROM friend_requests fr JOIN users u ON fr.from_user = u.user_id
            WHERE fr.to_user=? AND fr.status='pending' ORDER BY fr.created_at DESC""", (uid,)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    d = request.get_json(silent=True) or {}
    target = (d.get("to_user") or "").strip()
    if target == uid:
        conn.close()
        return jsonify({"success": False, "error": "Cannot add yourself"})
    if not check_premium(uid) and friend_count(uid) >= FREE_FRIEND_LIMIT:
        conn.close()
        return jsonify({"success": False, "error": f"Free plan limited to {FREE_FRIEND_LIMIT} friends. Upgrade to Premium for unlimited!", "premium_required": True})
    if are_friends(uid, target):
        conn.close()
        return jsonify({"success": False, "error": "Already friends"})
    existing = conn.execute("""SELECT id FROM friend_requests
        WHERE ((from_user=? AND to_user=?) OR (from_user=? AND to_user=?)) AND status='pending'""",
        (uid, target, target, uid)).fetchone()
    if existing:
        conn.close()
        return jsonify({"success": False, "error": "Request already pending"})
    conn.execute("INSERT INTO friend_requests (from_user, to_user, status, created_at) VALUES (?,?,'pending',?)",
                 (uid, target, fmt()))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/friends/respond", methods=["POST"])
@login_required
def friend_respond():
    uid = session["user_id"]
    d = request.get_json(silent=True) or {}
    rid = d.get("request_id")
    action = d.get("action")  # accept | decline
    conn = get_db()
    row = conn.execute("SELECT * FROM friend_requests WHERE id=? AND to_user=?", (rid, uid)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Not found"})
    if action == "accept":
        if not check_premium(uid) and friend_count(uid) >= FREE_FRIEND_LIMIT:
            conn.close()
            return jsonify({"success": False, "error": f"Free plan limited to {FREE_FRIEND_LIMIT} friends.", "premium_required": True})
        conn.execute("UPDATE friend_requests SET status='accepted' WHERE id=?", (rid,))
    else:
        conn.execute("UPDATE friend_requests SET status='declined' WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/friends")
@login_required
def friends_list():
    uid = session["user_id"]
    conn = get_db()
    rows = conn.execute("""SELECT u.user_id, u.full_name, u.student_id, u.course_year, u.last_seen
        FROM friend_requests fr JOIN users u ON
        (u.user_id = CASE WHEN fr.from_user=? THEN fr.to_user ELSE fr.from_user END)
        WHERE fr.status='accepted' AND (fr.from_user=? OR fr.to_user=?)
        ORDER BY u.full_name""", (uid, uid, uid)).fetchall()
    conn.close()
    out = []
    for r in rows:
        r = dict(r)
        r["online"] = is_online(r)
        out.append(r)
    return jsonify(out)


# ---------- DIRECT CHAT ----------
@app.route("/api/chat/<friend_id>", methods=["GET", "POST"])
@login_required
def direct_chat(friend_id):
    uid = session["user_id"]
    if not are_friends(uid, friend_id):
        return jsonify({"error": "Not friends"}), 403
    conn = get_db()
    if request.method == "GET":
        after = int(request.args.get("after_id", 0))
        rows = conn.execute("""SELECT * FROM messages WHERE id>? AND
            ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?))
            ORDER BY id ASC LIMIT 200""", (after, uid, friend_id, friend_id, uid)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    d = request.get_json(silent=True) or {}
    content = (d.get("content") or "").strip()
    if not content:
        conn.close()
        return jsonify({"success": False, "error": "Empty message"})
    conn.execute("INSERT INTO messages (sender_id, receiver_id, content, sent_at) VALUES (?,?,?,?)",
                 (uid, friend_id, content, fmt()))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ---------- GROUPS (Premium to create) ----------
@app.route("/api/groups", methods=["GET", "POST"])
@login_required
def groups_api():
    uid = session["user_id"]
    conn = get_db()
    if request.method == "GET":
        rows = conn.execute("""SELECT g.* FROM groups g JOIN group_members gm
            ON g.id = gm.group_id WHERE gm.user_id=? ORDER BY g.created_at DESC""", (uid,)).fetchall()
        out = []
        for r in rows:
            r = dict(r)
            mems = conn.execute("""SELECT u.user_id, u.full_name FROM group_members gm
                JOIN users u ON gm.user_id=u.user_id WHERE gm.group_id=?""", (r["id"],)).fetchall()
            r["members"] = [dict(m) for m in mems]
            out.append(r)
        conn.close()
        return jsonify(out)
    if not check_premium(uid):
        conn.close()
        return jsonify({"error": "Premium required to create groups", "premium_required": True}), 403
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    members = d.get("members") or []
    if not name:
        conn.close()
        return jsonify({"success": False, "error": "Group name required"})
    cur = conn.execute("INSERT INTO groups (name, created_by, created_at) VALUES (?,?,?) RETURNING id", (name, uid, fmt()))
    gid = cur.fetchone()["id"]
    conn.execute("INSERT INTO group_members (group_id, user_id, joined_at) VALUES (?,?,?)", (gid, uid, fmt()))
    for m in members:
        if are_friends(uid, m):
            try:
                conn.execute("INSERT INTO group_members (group_id, user_id, joined_at) VALUES (?,?,?)", (gid, m, fmt()))
            except pg_errors.UniqueViolation:
                conn.rollback()
                pass
    conn.commit()
    conn.close()
    return jsonify({"success": True, "group_id": gid})


@app.route("/api/groups/<int:gid>/add", methods=["POST"])
@login_required
def group_add_member(gid):
    uid = session["user_id"]
    conn = get_db()
    mem = conn.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=?", (gid, uid)).fetchone()
    if not mem:
        conn.close()
        return jsonify({"error": "Not a member"}), 403
    d = request.get_json(silent=True) or {}
    new_uid = d.get("user_id")
    if not are_friends(uid, new_uid):
        conn.close()
        return jsonify({"success": False, "error": "Can only add friends"})
    try:
        conn.execute("INSERT INTO group_members (group_id, user_id, joined_at) VALUES (?,?,?)", (gid, new_uid, fmt()))
        conn.commit()
    except pg_errors.UniqueViolation:
        conn.rollback()
        pass
    conn.close()
    return jsonify({"success": True})


@app.route("/api/groups/<int:gid>/messages", methods=["GET", "POST"])
@login_required
def group_messages(gid):
    uid = session["user_id"]
    conn = get_db()
    mem = conn.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=?", (gid, uid)).fetchone()
    if not mem:
        conn.close()
        return jsonify({"error": "Not a member"}), 403
    if request.method == "GET":
        after = int(request.args.get("after_id", 0))
        rows = conn.execute("""SELECT gm.*, u.full_name FROM group_messages gm
            JOIN users u ON gm.sender_id = u.user_id
            WHERE gm.id>? AND gm.group_id=? ORDER BY gm.id ASC LIMIT 200""", (after, gid)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    d = request.get_json(silent=True) or {}
    content = (d.get("content") or "").strip()
    if not content:
        conn.close()
        return jsonify({"success": False, "error": "Empty"})
    conn.execute("INSERT INTO group_messages (group_id, sender_id, content, sent_at) VALUES (?,?,?,?)",
                 (gid, uid, content, fmt()))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ---------- TYPING INDICATOR ----------
@app.route("/api/typing", methods=["POST", "GET"])
@login_required
def typing_api():
    uid = session["user_id"]
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        conv = (d.get("conv") or "").strip()
        if conv:
            conn = get_db()
            conn.execute("""INSERT INTO typing (user_id, conv, updated_at) VALUES (?,?,?)
                ON CONFLICT(user_id, conv) DO UPDATE SET updated_at=excluded.updated_at""",
                (uid, conv, fmt()))
            conn.commit()
            conn.close()
        return jsonify({"success": True})
    conv = (request.args.get("conv") or "").strip()
    cutoff = fmt(now_ph() - datetime.timedelta(seconds=5))
    conn = get_db()
    rows = conn.execute("""SELECT u.full_name FROM typing t JOIN users u ON t.user_id=u.user_id
        WHERE t.conv=? AND t.user_id!=? AND t.updated_at>?""", (conv, uid, cutoff)).fetchall()
    conn.close()
    return jsonify([r["full_name"] for r in rows])


# ==================== FRONTEND ====================
FRONTEND = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TaskHive — Plan • Study • Achieve</title>
<style>
:root{
  --bg:#f1f5f9;--card:#fff;--text:#0f172a;--muted:#64748b;
  --primary:#6366f1;--secondary:#3b82f6;--accent:#8b5cf6;
  --success:#10b981;--warning:#f59e0b;--danger:#ef4444;
  --border:#e2e8f0;--shadow:0 2px 10px rgba(99,102,241,.08);
  --grad:linear-gradient(135deg,#6366f1,#3b82f6);
}
.dark{--bg:#0f172a;--card:#1e293b;--text:#f1f5f9;--muted:#94a3b8;--border:#334155;--shadow:0 2px 10px rgba(0,0,0,.3);}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',Roboto,sans-serif;}
body{background:var(--bg);color:var(--text);min-height:100vh;transition:background .3s;}
a{color:var(--primary);text-decoration:none;}
/* layout */
.layout{display:flex;min-height:100vh;}
.sidebar{width:260px;background:var(--card);border-right:1px solid var(--border);padding:20px 0;position:fixed;top:0;bottom:0;left:0;overflow-y:auto;z-index:100;transform:translateX(-100%);transition:transform .3s;}
.sidebar.show{transform:translateX(0);}
.sidebar .logo{padding:0 20px 20px;font-size:22px;font-weight:700;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.side-item{display:flex;align-items:center;gap:12px;padding:12px 20px;cursor:pointer;font-size:15px;color:var(--text);}
.side-item:hover,.side-item.active{background:rgba(99,102,241,.1);color:var(--primary);}
.side-item.locked{opacity:.5;}
.side-item .lock{margin-left:auto;font-size:13px;}
.main{flex:1;margin-left:0;padding:20px;padding-bottom:90px;max-width:100%;}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;}
.topbar h1{font-size:22px;}
.menu-btn{background:none;border:none;font-size:24px;color:var(--text);cursor:pointer;display:block;}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:90;display:none;}
.overlay.show{display:block;}
.card{background:var(--card);border-radius:14px;padding:18px;margin-bottom:16px;box-shadow:var(--shadow);}
.card h3{font-size:15px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;}
.card h3 span{font-size:12px;color:var(--primary);cursor:pointer;}
.btn{padding:10px 18px;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:opacity .2s;}
.btn:hover{opacity:.9;}
.btn-primary{background:var(--grad);color:#fff;}
.btn-outline{background:transparent;border:1px solid var(--primary);color:var(--primary);}
.btn-success{background:var(--success);color:#fff;}
.btn-danger{background:var(--danger);color:#fff;}
.btn-sm{padding:6px 12px;font-size:12px;}
input,select,textarea{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:10px;font-size:14px;background:transparent;color:var(--text);margin-bottom:10px;}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--primary);}
label{font-size:13px;font-weight:500;display:block;margin-bottom:4px;color:var(--text);}
.page{display:none;animation:fade .3s;}
.page.active{display:block;}
@keyframes fade{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}
.grid-2{display:grid;grid-template-columns:1fr;gap:16px;}
.grid-4{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;}
.quick-btn{display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 6px;background:var(--card);border-radius:12px;border:none;cursor:pointer;color:var(--text);font-size:12px;box-shadow:var(--shadow);}
.quick-btn span{font-size:22px;}
.quick-btn.locked{opacity:.5;position:relative;}
.quick-btn.locked::after{content:"🔒";position:absolute;top:4px;right:6px;font-size:11px;}
.task-item{padding:10px 0;border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:flex-start;}
.task-item:last-child{border-bottom:none;}
.prio-dot{width:10px;height:10px;border-radius:50%;margin-top:5px;flex-shrink:0;}
.p-high{background:var(--danger);}.p-medium{background:var(--warning);}.p-low{background:var(--success);}
.task-text{flex:1;}
.task-title{font-size:14px;font-weight:500;}
.task-title.done{text-decoration:line-through;color:var(--muted);}
.task-meta{font-size:12px;color:var(--muted);margin-top:2px;}
.badge{font-size:11px;padding:2px 8px;border-radius:10px;margin-left:6px;}
.b-today{background:rgba(245,158,11,.15);color:var(--warning);}
.b-over{background:rgba(239,68,68,.1);color:var(--danger);}
.b-later{background:rgba(16,185,129,.1);color:var(--success);}
.stat{text-align:center;}
.stat-circle{width:56px;height:56px;border-radius:50%;margin:0 auto 6px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;border:3px solid var(--border);}
.stat-label{font-size:11px;color:var(--muted);}
.bottom-nav{position:fixed;bottom:0;left:0;right:0;background:var(--card);display:flex;justify-content:space-around;padding:8px 0;box-shadow:0 -2px 10px rgba(0,0,0,.06);z-index:80;}
.nav-item{display:flex;flex-direction:column;align-items:center;gap:2px;font-size:11px;color:var(--muted);cursor:pointer;background:none;border:none;}
.nav-item.active{color:var(--primary);}
.nav-item span{font-size:20px;}
.fab{width:46px;height:46px;border-radius:50%;background:var(--grad);border:none;color:#fff;font-size:22px;cursor:pointer;margin-top:-18px;box-shadow:0 4px 12px rgba(99,102,241,.4);}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;align-items:center;justify-content:center;z-index:200;padding:16px;}
.modal.show{display:flex;}
.modal-box{background:var(--card);border-radius:16px;padding:22px;width:100%;max-width:420px;max-height:90vh;overflow-y:auto;}
.modal-box h2{font-size:18px;margin-bottom:14px;text-align:center;}
.modal-actions{display:flex;gap:10px;margin-top:14px;}
.modal-actions .btn{flex:1;}
.empty{text-align:center;padding:30px 10px;color:var(--muted);}
.empty span{font-size:40px;display:block;margin-bottom:8px;opacity:.5;}
.online-dot{width:8px;height:8px;border-radius:50%;background:var(--success);display:inline-block;margin-right:6px;}
.offline-dot{width:8px;height:8px;border-radius:50%;background:var(--muted);display:inline-block;margin-right:6px;}
.chat-box{height:380px;overflow-y:auto;padding:10px;background:var(--bg);border-radius:10px;margin-bottom:10px;display:flex;flex-direction:column;gap:8px;}
.msg{max-width:75%;padding:8px 12px;border-radius:14px;font-size:13px;word-wrap:break-word;}
.msg.me{align-self:flex-end;background:var(--primary);color:#fff;border-bottom-right-radius:4px;}
.msg.them{align-self:flex-start;background:var(--card);border:1px solid var(--border);border-bottom-left-radius:4px;}
.msg .sender{font-size:10px;opacity:.7;margin-bottom:2px;}
.typing{font-size:12px;color:var(--muted);font-style:italic;height:16px;margin-bottom:4px;}
.prem-badge{display:inline-block;background:linear-gradient(135deg,#f59e0b,#d97706);color:#fff;font-size:11px;padding:3px 10px;border-radius:12px;font-weight:600;}
.countdown{background:linear-gradient(135deg,#f59e0b,#d97706);color:#fff;padding:12px;border-radius:10px;text-align:center;font-weight:600;margin:10px 0;}
.auth-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background:var(--grad);}
.auth-card{background:var(--card);padding:30px 24px;border-radius:18px;width:100%;max-width:400px;box-shadow:0 10px 40px rgba(0,0,0,.2);}
.auth-logo{text-align:center;margin-bottom:20px;}
.auth-logo h1{font-size:28px;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.auth-logo p{color:var(--muted);font-size:13px;margin-top:4px;}
.err{color:var(--danger);font-size:13px;margin:8px 0;display:none;}
.err.show{display:block;}
.ok{color:var(--success);font-size:13px;margin:8px 0;display:none;}
.ok.show{display:block;}
.progress-bar{height:8px;background:var(--border);border-radius:4px;overflow:hidden;margin:8px 0;}
.progress-fill{height:100%;background:var(--grad);transition:width .3s;}
table{width:100%;border-collapse:collapse;font-size:13px;}
th,td{padding:8px;text-align:left;border-bottom:1px solid var(--border);}
th{color:var(--muted);font-weight:600;font-size:12px;}
@media(min-width:768px){
  .sidebar{transform:translateX(0);}
  .menu-btn{display:none;}
  .main{margin-left:260px;max-width:1100px;padding:30px;}
  .bottom-nav{display:none;}
  .grid-2{grid-template-columns:1fr 1fr;}
  .grid-4{grid-template-columns:repeat(4,1fr);}
  .topbar h1{font-size:26px;}
}
</style>
</head>
<body>
<!-- AUTH -->
<div id="authWrap" class="auth-wrap" style="display:none;">
  <div class="auth-card">
    <div class="auth-logo"><h1>🐝 TaskHive</h1><p>Plan • Study • Achieve</p></div>
    <div id="loginFormBox">
      <label>Email</label><input type="email" id="loginEmail" placeholder="you@email.com">
      <label>Password</label><input type="password" id="loginPass" placeholder="Enter password">
      <label style="display:flex;align-items:center;gap:6px;font-weight:400;"><input type="checkbox" id="rememberMe" style="width:auto;margin:0;"> Remember me</label>
      <div class="err" id="loginErr"></div>
      <div class="ok" id="loginOk"></div>
      <button class="btn btn-primary" style="width:100%;" onclick="doLogin()">Log In</button>
      <p style="text-align:center;margin-top:14px;font-size:13px;color:var(--muted);">No account? <a href="#" onclick="showRegister();return false;">Sign Up</a></p>
      <p style="text-align:center;margin-top:6px;font-size:11px;color:var(--muted);">Admin: admin@taskhive.com / admin123</p>
    </div>
    <div id="regFormBox" style="display:none;">
      <label>Full Name</label><input type="text" id="regName" placeholder="Juan Dela Cruz">
      <label>Email</label><input type="email" id="regEmail" placeholder="you@email.com">
      <label>Student ID</label><input type="text" id="regSid" placeholder="2023-12345">
      <label>Course & Year</label><input type="text" id="regCourse" placeholder="BSCS - 2nd Year">
      <label>Password</label><input type="password" id="regPass" placeholder="At least 6 chars">
      <label>Confirm Password</label><input type="password" id="regPass2" placeholder="Re-enter">
      <div class="err" id="regErr"></div>
      <button class="btn btn-primary" style="width:100%;" onclick="doRegister()">Create Account</button>
      <p style="text-align:center;margin-top:14px;font-size:13px;color:var(--muted);">Have an account? <a href="#" onclick="showLogin();return false;">Log In</a></p>
    </div>
  </div>
</div>

<!-- MAIN APP -->
<div id="appWrap" style="display:none;">
<div class="layout">
  <div class="overlay" id="overlay" onclick="toggleSidebar()"></div>
  <aside class="sidebar" id="sidebar">
    <div class="logo">🐝 TaskHive</div>
    <div style="padding:0 20px 14px;">
      <div style="font-weight:600;font-size:15px;" id="sideName">User</div>
      <div style="font-size:12px;color:var(--muted);" id="sideCourse">--</div>
      <div id="sidePrem" class="prem-badge" style="display:none;margin-top:6px;">👑 Premium</div>
    </div>
    <div class="side-item active" data-page="dashboard" onclick="go('dashboard')">🏠 Dashboard</div>
    <div class="side-item" data-page="tasks" onclick="go('tasks')">✅ Tasks</div>
    <div class="side-item" data-page="schedule" onclick="go('schedule')">📅 Schedule</div>
    <div class="side-item" data-page="notes" onclick="go('notes')">📝 Notes</div>
    <div class="side-item" data-page="projects" onclick="go('projects')">👥 Projects</div>
    <div class="side-item" data-page="grades" onclick="go('grades')">📊 Grades</div>
    <div class="side-item" data-page="planner" onclick="go('planner')">🎯 Planner</div>
    <div class="side-item locked" id="sideBudget" onclick="premLock('budget')">💰 Budget <span class="lock">🔒</span></div>
    <div class="side-item" data-page="friends" onclick="go('friends')">🤝 Friends</div>
    <div class="side-item locked" id="sideGroups" onclick="premLock('groups')">💬 Group Chats <span class="lock">🔒</span></div>
    <div class="side-item" data-page="premium" onclick="go('premium')">✨ Premium</div>
    <div class="side-item" id="sideAdmin" style="display:none;" data-page="admin" onclick="go('admin')">🛡️ Admin Panel</div>
    <div class="side-item" data-page="settings" onclick="go('settings')">⚙️ Settings</div>
    <div class="side-item" style="color:var(--danger);" onclick="logout()">🚪 Log Out</div>
  </aside>
  <main class="main">
    <div class="topbar">
      <button class="menu-btn" onclick="toggleSidebar()">☰</button>
      <h1 id="pageTitle">Dashboard</h1>
      <span></span>
    </div>

    <!-- DASHBOARD -->
    <div class="page active" id="page-dashboard">
      <h2 style="font-size:20px;margin-bottom:4px;" id="greeting">Hi!</h2>
      <p style="font-size:13px;color:var(--muted);font-style:italic;margin-bottom:18px;" id="quote"></p>
      <div class="grid-2">
        <div class="card"><h3>📅 Today's Schedule</h3><div id="todaySched"></div></div>
        <div class="card"><h3>⏰ Upcoming Deadlines</h3><div id="upcomingTasks"></div></div>
      </div>
      <div class="card">
        <h3>📊 Quick Stats</h3>
        <div class="grid-4">
          <div class="stat"><div class="stat-circle" id="statPct" style="border-color:var(--primary);">0%</div><div class="stat-label">Complete</div></div>
          <div class="stat"><div class="stat-circle" style="border-color:var(--success);" id="statDone">0</div><div class="stat-label">Done</div></div>
          <div class="stat"><div class="stat-circle" style="border-color:var(--warning);" id="statPending">0</div><div class="stat-label">Pending</div></div>
          <div class="stat"><div class="stat-circle" style="border-color:var(--danger);" id="statOver">0</div><div class="stat-label">Overdue</div></div>
        </div>
      </div>
      <div class="card">
        <h3>⚡ Quick Actions</h3>
        <div class="grid-4">
          <button class="quick-btn" onclick="openModal('taskModal')"><span>➕</span>Add Task</button>
          <button class="quick-btn" onclick="go('schedule')"><span>📆</span>Schedule</button>
          <button class="quick-btn" onclick="go('planner')"><span>🎯</span>Planner</button>
          <button class="quick-btn locked" onclick="premLock()"><span>⏱️</span>Focus</button>
          <button class="quick-btn locked" onclick="premLock()"><span>🤖</span>AI Help</button>
          <button class="quick-btn locked" onclick="premLock()"><span>🔔</span>Remind</button>
          <button class="quick-btn locked" onclick="premLock()"><span>♻️</span>Recover</button>
          <button class="quick-btn locked" onclick="doExport()"><span>📄</span>Export</button>
        </div>
      </div>
    </div>

    <!-- TASKS -->
    <div class="page" id="page-tasks">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>✅ My Tasks</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('taskModal')">+ Add Task</button>
      </div>
      <input type="text" id="taskSearch" placeholder="🔍 Search tasks..." oninput="renderTasks()">
      <div id="taskList"></div>
    </div>

    <!-- SCHEDULE -->
    <div class="page" id="page-schedule">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>📅 Class Schedule</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('schedModal')">+ Add</button>
      </div>
      <div id="schedList"></div>
    </div>

    <!-- NOTES -->
    <div class="page" id="page-notes">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>📝 Notes</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('noteModal')">+ Note</button>
      </div>
      <div id="noteList"></div>
    </div>

    <!-- PROJECTS -->
    <div class="page" id="page-projects">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>👥 Group Projects</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('projModal')">+ Project</button>
      </div>
      <div id="projList"></div>
    </div>

    <!-- GRADES -->
    <div class="page" id="page-grades">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>📊 Grades & GPA</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('gradeModal')">+ Grade</button>
      </div>
      <div class="card" style="text-align:center;"><h3>📈 GPA</h3><div style="font-size:40px;font-weight:700;color:var(--primary);" id="gpaVal">--</div></div>
      <div id="gradeList"></div>
    </div>

    <!-- PLANNER -->
    <div class="page" id="page-planner">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>🎯 Study Planner</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('goalModal')">+ Goal</button>
      </div>
      <div id="goalList"></div>
    </div>

    <!-- BUDGET (premium) -->
    <div class="page" id="page-budget">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>💰 Budget Tracker</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('budgModal')">+ Entry</button>
      </div>
      <div class="card">
        <div style="text-align:center;font-size:28px;font-weight:700;" id="budgBal">₱0.00</div>
        <div style="display:flex;justify-content:space-around;margin-top:10px;">
          <div style="text-align:center;"><div style="color:var(--success);font-weight:600;" id="budgIn">+₱0</div><div style="font-size:11px;color:var(--muted);">Income</div></div>
          <div style="text-align:center;"><div style="color:var(--danger);font-weight:600;" id="budgOut">-₱0</div><div style="font-size:11px;color:var(--muted);">Expense</div></div>
        </div>
      </div>
      <div id="budgList"></div>
    </div>

    <!-- FRIENDS -->
    <div class="page" id="page-friends">
      <h2 style="margin-bottom:14px;">🤝 Friends</h2>
      <div class="card">
        <h3>🔍 Find Friends</h3>
        <input type="text" id="friendSearch" placeholder="Search by name or Student ID (min 2 chars)..." oninput="searchFriends()">
        <div id="friendSearchResults"></div>
      </div>
      <div class="card">
        <h3>📨 Friend Requests <span id="reqCount" style="background:var(--danger);color:#fff;border-radius:10px;padding:1px 8px;font-size:11px;display:none;">0</span></h3>
        <div id="friendRequests"></div>
      </div>
      <div class="card">
        <h3>👥 My Friends <span id="friendCountLabel" style="font-size:12px;color:var(--muted);"></span></h3>
        <div id="friendList"></div>
      </div>
    </div>

    <!-- CHAT (dm) -->
    <div class="page" id="page-chat">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
        <button class="btn btn-outline btn-sm" onclick="go('friends')">← Back</button>
        <h2 id="chatTitle">Chat</h2>
      </div>
      <div class="typing" id="dmTyping"></div>
      <div class="chat-box" id="dmChatBox"></div>
      <div style="display:flex;gap:8px;">
        <input type="text" id="dmInput" placeholder="Type a message..." onkeydown="if(event.key==='Enter')sendDm()" oninput="typingDm()">
        <button class="btn btn-primary" onclick="sendDm()">Send</button>
      </div>
    </div>

    <!-- GROUPS -->
    <div class="page" id="page-groups">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h2>💬 Group Chats</h2>
        <button class="btn btn-primary btn-sm" onclick="openModal('groupModal')">+ New Group</button>
      </div>
      <div id="groupList"></div>
    </div>

    <!-- GROUP CHAT -->
    <div class="page" id="page-gchat">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
        <button class="btn btn-outline btn-sm" onclick="go('groups')">← Back</button>
        <h2 id="gchatTitle">Group</h2>
      </div>
      <div class="typing" id="gTyping"></div>
      <div class="chat-box" id="gChatBox"></div>
      <div style="display:flex;gap:8px;">
        <input type="text" id="gInput" placeholder="Type a message..." onkeydown="if(event.key==='Enter')sendG()" oninput="typingG()">
        <button class="btn btn-primary" onclick="sendG()">Send</button>
      </div>
    </div>

    <!-- PREMIUM -->
    <div class="page" id="page-premium">
      <div style="text-align:center;padding:10px 0 18px;">
        <h2 style="font-size:24px;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">👑 Unlock Premium</h2>
        <p style="color:var(--muted);margin-top:4px;">₱50.00 for 30 days — all features unlocked</p>
      </div>
      <div class="card" id="premStatusCard"></div>
      <div class="card" id="payCard">
        <h3>💳 Pay via GCash</h3>
        <div style="text-align:center;padding:14px;background:var(--bg);border-radius:10px;margin-bottom:12px;">
          <div style="font-size:30px;font-weight:700;color:var(--success);">₱50.00</div>
          <div style="font-size:12px;color:var(--muted);">Send to: <strong id="gcNum">--</strong> · <span id="gcName">--</span></div>
        </div>
        <label>Your Reference ID (auto-generated)</label>
        <input type="text" id="refId" readonly style="background:var(--bg);">
        <label>GCash Reference Number *</label>
        <input type="text" id="gcashRef" placeholder="e.g. 123456789012">
        <label>Screenshot of Receipt (optional but recommended)</label>
        <input type="file" id="screenshot" accept="image/*">
        <div class="err" id="payErr"></div>
        <button class="btn btn-success" style="width:100%;" onclick="submitPayment()">✅ Submit Payment for Approval</button>
        <p style="text-align:center;margin-top:10px;font-size:12px;color:var(--muted);">After submitting, wait for admin approval. You'll be notified here.</p>
      </div>
      <div class="card">
        <h3>✨ Premium Features</h3>
        <div style="font-size:13px;line-height:2;">
          ✅ Budget Tracker &nbsp; ✅ Deadline Reminders &nbsp; ✅ Missed Task Recovery<br>
          ✅ Export Reports (CSV) &nbsp; ✅ Time Estimator &nbsp; ✅ AI Study Assistant<br>
          ✅ Exam Countdown &nbsp; ✅ Focus Mode &nbsp; ✅ Unlimited Friends & Group Chat
        </div>
      </div>
    </div>

    <!-- ADMIN -->
    <div class="page" id="page-admin">
      <h2 style="margin-bottom:14px;">🛡️ Admin Panel</h2>
      <div class="card">
        <h3>⏳ Pending Payment Approvals</h3>
        <div id="adminPending"></div>
      </div>
      <div class="card">
        <h3>👥 All Users</h3>
        <div style="overflow-x:auto;"><table><thead><tr><th>Name</th><th>Student ID</th><th>Course</th><th>Premium</th><th>Expiry</th></tr></thead><tbody id="adminUsers"></tbody></table></div>
      </div>
      <div class="card">
        <h3>📜 Recent Payments</h3>
        <div style="overflow-x:auto;"><table><thead><tr><th>User</th><th>Ref</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead><tbody id="adminPayments"></tbody></table></div>
      </div>
    </div>

    <!-- SETTINGS -->
    <div class="page" id="page-settings">
      <h2 style="margin-bottom:14px;">⚙️ Settings</h2>
      <div class="card">
        <h3>🎨 Theme</h3>
        <label style="display:flex;align-items:center;gap:8px;font-weight:400;"><input type="checkbox" id="darkToggle" onchange="toggleTheme()" style="width:auto;margin:0;"> Dark Mode</label>
      </div>
      <div class="card">
        <h3>👤 Account</h3>
        <p style="font-size:14px;line-height:2;"><strong>Name:</strong> <span id="setName">--</span><br>
        <strong>Email:</strong> <span id="setEmail">--</span><br>
        <strong>Student ID:</strong> <span id="setSid">--</span><br>
        <strong>Course:</strong> <span id="setCourse">--</span><br>
        <strong>Member since:</strong> <span id="setJoin">--</span></p>
      </div>
      <div class="card">
        <h3>💎 Subscription</h3>
        <p><strong>Plan:</strong> <span id="setPlan">Free</span></p>
        <p><strong>Status:</strong> <span id="setStatus">Inactive</span></p>
        <button class="btn btn-primary btn-sm" style="margin-top:10px;" onclick="go('premium')">Upgrade to Premium</button>
      </div>
    </div>
  </main>
</div>

<!-- bottom nav mobile -->
<div class="bottom-nav">
  <button class="nav-item active" data-page="dashboard" onclick="go('dashboard')"><span>🏠</span>Home</button>
  <button class="nav-item" data-page="tasks" onclick="go('tasks')"><span>✅</span>Tasks</button>
  <button class="fab" onclick="openModal('quickModal')">+</button>
  <button class="nav-item" data-page="friends" onclick="go('friends')"><span>🤝</span>Friends</button>
  <button class="nav-item" data-page="settings" onclick="go('settings')"><span>👤</span>Profile</button>
</div>
</div>

<!-- MODALS -->
<div class="modal" id="taskModal"><div class="modal-box">
  <h2>➕ Add Task</h2>
  <label>Title *</label><input type="text" id="tTitle">
  <label>Subject</label><input type="text" id="tSubject">
  <label>Description</label><textarea id="tDesc" rows="2"></textarea>
  <label>Due Date *</label><input type="date" id="tDate">
  <label>Due Time</label><input type="time" id="tTime" value="23:59">
  <label>Priority</label><select id="tPrio"><option value="high">🔴 High</option><option value="medium" selected>🟡 Medium</option><option value="low">🟢 Low</option></select>
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('taskModal')">Cancel</button><button class="btn btn-primary" onclick="saveTask()">Save</button></div>
</div></div>

<div class="modal" id="schedModal"><div class="modal-box">
  <h2>📅 Add Class</h2>
  <label>Subject *</label><input type="text" id="sSubject">
  <label>Day *</label><select id="sDay"><option>Monday</option><option>Tuesday</option><option>Wednesday</option><option>Thursday</option><option>Friday</option><option>Saturday</option></select>
  <label>Start *</label><input type="time" id="sStart">
  <label>End *</label><input type="time" id="sEnd">
  <label>Room</label><input type="text" id="sRoom">
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('schedModal')">Cancel</button><button class="btn btn-primary" onclick="saveSched()">Save</button></div>
</div></div>

<div class="modal" id="noteModal"><div class="modal-box">
  <h2>📝 New Note</h2>
  <label>Title *</label><input type="text" id="nTitle">
  <label>Folder</label><select id="nFolder"><option>General</option><option>Reviewer</option><option>Lecture</option><option>Personal</option></select>
  <label>Content</label><textarea id="nContent" rows="4"></textarea>
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('noteModal')">Cancel</button><button class="btn btn-primary" onclick="saveNote()">Save</button></div>
</div></div>

<div class="modal" id="projModal"><div class="modal-box">
  <h2>👥 New Project</h2>
  <label>Project Name *</label><input type="text" id="pName">
  <label>Members</label><input type="text" id="pMembers" placeholder="Names, comma separated">
  <label>Deadline</label><input type="date" id="pDeadline">
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('projModal')">Cancel</button><button class="btn btn-primary" onclick="saveProj()">Save</button></div>
</div></div>

<div class="modal" id="gradeModal"><div class="modal-box">
  <h2>📊 Record Grade</h2>
  <label>Subject *</label><input type="text" id="gSubject">
  <label>Score (0-100) *</label><input type="number" id="gScore" min="0" max="100" step="0.1">
  <label>Units</label><input type="number" id="gUnits" value="3" min="1">
  <label>Semester</label><input type="text" id="gSem" placeholder="1st Sem AY 2024-2025">
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('gradeModal')">Cancel</button><button class="btn btn-primary" onclick="saveGrade()">Save</button></div>
</div></div>

<div class="modal" id="budgModal"><div class="modal-box">
  <h2>💰 Add Transaction</h2>
  <label>Type</label><select id="bType"><option value="income">📈 Income</option><option value="expense">📉 Expense</option></select>
  <label>Category</label><input type="text" id="bCat" placeholder="Food, Transport...">
  <label>Amount (₱) *</label><input type="number" id="bAmt" step="1">
  <label>Description</label><input type="text" id="bDesc">
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('budgModal')">Cancel</button><button class="btn btn-primary" onclick="saveBudg()">Save</button></div>
</div></div>

<div class="modal" id="goalModal"><div class="modal-box">
  <h2>🎯 New Goal</h2>
  <label>Goal *</label><textarea id="goalText" rows="3"></textarea>
  <label>Target Date</label><input type="date" id="goalDate">
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('goalModal')">Cancel</button><button class="btn btn-primary" onclick="saveGoal()">Save</button></div>
</div></div>

<div class="modal" id="groupModal"><div class="modal-box">
  <h2>💬 New Group Chat</h2>
  <label>Group Name *</label><input type="text" id="grpName" placeholder="e.g. Study Buddies">
  <label>Add Friends (select multiple)</label>
  <div id="grpMembers" style="max-height:180px;overflow-y:auto;margin-bottom:10px;"></div>
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('groupModal')">Cancel</button><button class="btn btn-primary" onclick="createGroup()">Create</button></div>
</div></div>

<div class="modal" id="premLockModal"><div class="modal-box" style="text-align:center;">
  <div style="font-size:44px;margin-bottom:10px;">🔒</div>
  <h2>Premium Feature</h2>
  <p style="color:var(--muted);margin-bottom:16px;font-size:14px;">This is available for Premium subscribers only. Upgrade for ₱50.00 / 30 days!</p>
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('premLockModal')">Not Now</button><button class="btn btn-primary" onclick="closeModal('premLockModal');go('premium');">Upgrade ✨</button></div>
</div></div>

<div class="modal" id="quickModal"><div class="modal-box">
  <h2>⚡ Quick Add</h2>
  <div class="grid-4" style="margin-top:10px;">
    <button class="quick-btn" onclick="closeModal('quickModal');openModal('taskModal')"><span>✅</span>Task</button>
    <button class="quick-btn" onclick="closeModal('quickModal');openModal('schedModal')"><span>📅</span>Class</button>
    <button class="quick-btn" onclick="closeModal('quickModal');openModal('noteModal')"><span>📝</span>Note</button>
    <button class="quick-btn" onclick="closeModal('quickModal');openModal('projModal')"><span>👥</span>Project</button>
  </div>
  <button class="btn btn-outline" style="width:100%;margin-top:14px;" onclick="closeModal('quickModal')">Cancel</button>
</div></div>

<div class="modal" id="rejectModal"><div class="modal-box">
  <h2>❌ Reject Payment</h2>
  <label>Reason</label><input type="text" id="rejectReason" placeholder="e.g. Screenshot unclear">
  <div class="modal-actions"><button class="btn btn-outline" onclick="closeModal('rejectModal')">Cancel</button><button class="btn btn-danger" onclick="confirmReject()">Reject</button></div>
</div></div>

<script>
let ME=null, isPremium=false, isAdmin=false;
let tasks=[], sched=[], notes=[], projects=[], grades=[], budget=[], goals=[];
let friends=[], currentChatFriend=null, currentGroup=null, dmLastId=0, gLastId=0;
let chatTimer=null, gChatTimer=null, rejectPid=null;

const $=id=>document.getElementById(id);
function api(url, opts){return fetch(url, opts).then(r=>r.json());}
function jpost(url, data){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}

// ---------- AUTH ----------
function showLogin(){$('loginFormBox').style.display='block';$('regFormBox').style.display='none';}
function showRegister(){$('loginFormBox').style.display='none';$('regFormBox').style.display='block';}
function doLogin(){
  const email=$('loginEmail').value, pass=$('loginPass').value, rem=$('rememberMe').checked;
  jpost('/api/login',{email,password:pass,remember:rem}).then(d=>{
    if(d.success){$('loginErr').classList.remove('show');boot();}
    else{$('loginErr').textContent=d.error;$('loginErr').classList.add('show');}
  });
}
function doRegister(){
  const data={full_name:$('regName').value,email:$('regEmail').value,student_id:$('regSid').value,
    course_year:$('regCourse').value,password:$('regPass').value,confirm_password:$('regPass2').value};
  jpost('/api/register',data).then(d=>{
    if(d.success){$('regErr').classList.remove('show');showLogin();$('loginEmail').value=data.email;
      $('loginOk').textContent='✅ Account created! Please log in.';$('loginOk').classList.add('show');}
    else{$('regErr').textContent=d.error;$('regErr').classList.add('show');}
  });
}
function logout(){if(confirm('Log out?'))window.location.href='/logout';}

function boot(){
  api('/api/user').then(u=>{
    if(u.error){$('authWrap').style.display='flex';$('appWrap').style.display='none';return;}
    ME=u; isPremium=u.is_premium; isAdmin=u.is_admin;
    $('authWrap').style.display='none';$('appWrap').style.display='block';
    applyTheme(u.theme); updateUserUI(); loadAll();
    if(isPremium){$('sideBudget').classList.remove('locked');$('sideBudget').onclick=()=>go('budget');
      $('sideBudget .lock')&&($('sideBudget .lock').style.display='none');
      $('sideGroups').classList.remove('locked');$('sideGroups').onclick=()=>go('groups');
      $('sideGroups .lock')&&($('sideGroups .lock').style.display='none');
      document.querySelectorAll('.quick-btn.locked').forEach(b=>{b.classList.remove('locked');
        if(b.textContent.includes('Export'))b.onclick=doExport; else b.onclick=()=>alert('Premium feature active! ✅');});
    }
    if(isAdmin)$('sideAdmin').style.display='block';
    setGreeting(); setQuote();
  }).catch(()=>{$('authWrap').style.display='flex';$('appWrap').style.display='none';});
}
window.addEventListener('DOMContentLoaded',boot);

function updateUserUI(){
  $('sideName').textContent=ME.full_name; $('sideCourse').textContent=ME.course_year;
  $('sidePrem').style.display=isPremium?'block':'none';
  $('setName').textContent=ME.full_name; $('setEmail').textContent=ME.email;
  $('setSid').textContent=ME.student_id; $('setCourse').textContent=ME.course_year;
  $('setJoin').textContent=new Date(ME.join_date).toLocaleDateString('en-PH');
  $('setPlan').textContent=isPremium?'👑 Premium':'Free';
  $('setStatus').textContent=isPremium?'Active ✅':'Inactive';
  $('setStatus').style.color=isPremium?'var(--success)':'var(--muted)';
}

function applyTheme(t){if(t==='dark'){document.body.classList.add('dark');$('darkToggle').checked=true;}
  else{document.body.classList.remove('dark');$('darkToggle').checked=false;}}
function toggleTheme(){const dark=$('darkToggle').checked;applyTheme(dark?'dark':'light');
  jpost('/api/user/theme',{theme:dark?'dark':'light'});}

function setGreeting(){const h=new Date().getHours();let g='Good Evening';
  if(h>=5&&h<12)g='Good Morning';else if(h<18)g='Good Afternoon';
  $('greeting').textContent=`${g}, ${ME?ME.full_name.split(' ')[0]:''}!`;}
function setQuote(){const q=['"Your future is created by what you do today."','"Study now, be proud later."',
  '"Every expert was once a beginner."','"Dream big. Start small. Start now."','"It always seems impossible until done."'];
  $('quote').textContent=q[new Date().getDate()%q.length];}

function toggleSidebar(){$('sidebar').classList.toggle('show');$('overlay').classList.toggle('show');}
function go(page){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  const el=$('page-'+page); if(el)el.classList.add('active');
  const titles={dashboard:'Dashboard',tasks:'Tasks',schedule:'Schedule',notes:'Notes',projects:'Projects',
    grades:'Grades',planner:'Study Planner',budget:'Budget Tracker',friends:'Friends',chat:'Chat',
    groups:'Group Chats',gchat:'Group Chat',premium:'✨ Premium',admin:'🛡️ Admin Panel',settings:'Settings'};
  $('pageTitle').textContent=titles[page]||'TaskHive';
  document.querySelectorAll('.side-item').forEach(s=>s.classList.remove('active'));
  const si=document.querySelector(.side-item[data-page="${page}"]);if(si)si.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  const ni=document.querySelector(.nav-item[data-page="${page}"]);if(ni)ni.classList.add('active');
  $('sidebar').classList.remove('show');$('overlay').classList.remove('show');
  if(page==='premium')loadPremium();
  if(page==='friends'){loadFriends();loadFriendRequests();}
  if(page==='admin')loadAdmin();
  if(page==='groups')loadGroups();
  if(page==='budget'&&isPremium)loadBudget();
  window.scrollTo(0,0);
}
function premLock(page){openModal('premLockModal');}
function openModal(id){$(id).classList.add('show');}
function closeModal(id){$(id).classList.remove('show');}

// ---------- LOAD ALL ----------
function loadAll(){loadTasks();loadSched();loadNotes();loadProjects();loadGrades();loadGoals();if(isPremium)loadBudget();}

// ---------- TASKS ----------
function loadTasks(){api('/api/tasks').then(d=>{tasks=d;renderDashboard();renderTasks();updateStats();});}
function saveTask(){
  if(!$('tTitle').value.trim()||!$('tDate').value){alert('Title and due date required!');return;}
  jpost('/api/tasks',{title:$('tTitle').value,subject:$('tSubject').value,description:$('tDesc').value,
    due_date:$('tDate').value,due_time:$('tTime').value,priority:$('tPrio').value,reminder_set:0,created_at:''})
    .then(()=>{closeModal('taskModal');['tTitle','tSubject','tDesc'].forEach(i=>$(i).value='');loadTasks();});
}
function toggleTask(id,done){jpost('/api/tasks',{id,completed:done?0:1}).then(loadTasks);}
function delTask(id){if(confirm('Delete?'))fetch('/api/tasks?id='+id,{method:'DELETE'}).then(loadTasks);}
function daysLeft(d){const due=new Date(d),now=new Date();now.setHours(0,0,0,0);due.setHours(0,0,0,0);
  return Math.ceil((due-now)/86400000);}
function renderDashboard(){
  const today=new Date().toISOString().split('T')[0];
  const up=tasks.filter(t=>t.due_date>=today&&!t.completed).sort((a,b)=>new Date(a.due_date)-new Date(b.due_date)).slice(0,5);
  $('upcomingTasks').innerHTML=up.length?up.map(t=>{
    const dl=daysLeft(t.due_date);let cls='b-later',txt=dl+'d left';
    if(dl===0){cls='b-today';txt='Today!';}else if(dl<0){cls='b-over';txt=Math.abs(dl)+'d overdue';}
    return `<div class="task-item"><div class="prio-dot p-${t.priority}"></div>
      <div class="task-text"><div class="task-title">${t.title}</div>
      <div class="task-meta">${t.subject||'No subject'} · ${new Date(t.due_date).toLocaleDateString('en-PH')}<span class="badge ${cls}">${txt}</span></div></div></div>`;
  }).join(''):'<div class="empty"><span>🎉</span>No upcoming deadlines!</div>';
}
function renderTasks(){
  const q=($('taskSearch')?.value||'').toLowerCase();
  const list=tasks.filter(t=>!q||(t.title+t.subject).toLowerCase().includes(q))
    .sort((a,b)=>new Date(a.due_date)-new Date(b.due_date));
  $('taskList').innerHTML=list.length?list.map(t=>{
    const dl=daysLeft(t.due_date);let cls='b-later',txt=dl+'d';
    if(dl===0){cls='b-today';txt='Today';}else if(dl<0){cls='b-over';txt=Math.abs(dl)+'d late';}
    return `<div class="card" style="margin-bottom:10px;"><div class="task-item" style="border:none;padding:0;">
      <input type="checkbox" ${t.completed?'checked':''} onchange="toggleTask(${t.id},${t.completed})" style="width:auto;margin-top:4px;">
      <div class="prio-dot p-${t.priority}"></div>
      <div class="task-text"><div class="task-title ${t.completed?'done':''}">${t.title}</div>
      <div class="task-meta">${t.subject?'<strong>'+t.subject+'</strong> · ':''}${new Date(t.due_date).toLocaleDateString('en-PH')} ${t.due_time||''}<span class="badge ${cls}">${txt}</span></div>
      ${t.description?`<div style="font-size:12px;color:var(--muted);margin-top:4px;">${t.description}</div>`:''}</div>
      <button onclick="delTask(${t.id})" style="background:none;border:none;color:var(--danger);cursor:pointer;">🗑️</button></div></div>`;
  }).join(''):'<div class="empty"><span>📋</span>No tasks yet.</div>';
}
function updateStats(){const total=tasks.length,done=tasks.filter(t=>t.completed).length;
  const today=new Date().toISOString().split('T')[0];
  const over=tasks.filter(t=>!t.completed&&t.due_date<today).length;
  const pct=total?Math.round(done/total*100):0;
  $('statPct').textContent=pct+'%';$('statDone').textContent=done;
  $('statPending').textContent=total-done;$('statOver').textContent=over;}

// ---------- SCHEDULE ----------
function loadSched(){api('/api/schedule').then(d=>{sched=d;renderTodaySched();renderSched();});}
function saveSched(){
  if(!$('sSubject').value.trim()||!$('sStart').value||!$('sEnd').value){alert('Fill required fields!');return;}
  jpost('/api/schedule',{subject:$('sSubject').value,day:$('sDay').value,time_start:$('sStart').value,
    time_end:$('sEnd').value,room:$('sRoom').value,color:'#6366F1'}).then(()=>{closeModal('schedModal');loadSched();});
}
function delSched(id){if(confirm('Delete?'))fetch('/api/schedule?id='+id,{method:'DELETE'}).then(loadSched);}
function fmtTime(t){if(!t)return'';const[h,m]=t.split(':');const hr=parseInt(h);
  return ${hr%12||12}:${m} ${hr>=12?'PM':'AM'};}
function todayName(){return ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][new Date().getDay()];}
function renderTodaySched(){
  const td=sched.filter(s=>s.day===todayName()).sort((a,b)=>a.time_start.localeCompare(b.time_start));
  $('todaySched').innerHTML=td.length?td.map(s=>`<div class="task-item">
    <div style="width:4px;background:${s.color};border-radius:2px;flex-shrink:0;"></div>
    <div class="task-text"><div class="task-title">${s.subject}</div>
    <div class="task-meta">${fmtTime(s.time_start)} - ${fmtTime(s.time_end)} · ${s.room||'No room'}</div></div></div>`).join('')
    :'<div class="empty"><span>📭</span>No classes today!</div>';
}
function renderSched(){
  const days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  $('schedList').innerHTML=sched.length?days.map(d=>{
    const ds=sched.filter(s=>s.day===d);if(!ds.length)return'';
    return `<div class="card"><h4 style="margin-bottom:8px;color:var(--primary);">${d}</h4>${ds.map(s=>
      `<div class="task-item"><div style="width:4px;background:${s.color};border-radius:2px;min-height:36px;flex-shrink:0;"></div>
      <div class="task-text"><div style="font-weight:500;font-size:14px;">${s.subject}</div>
      <div class="task-meta">${fmtTime(s.time_start)} - ${fmtTime(s.time_end)} · ${s.room||'No room'}</div></div>
      <button onclick="delSched(${s.id})" style="background:none;border:none;color:var(--muted);cursor:pointer;">×</button></div>`).join('')}</div>`;
  }).join(''):'<div class="empty"><span>📅</span>No schedule yet.</div>';
}

// ---------- NOTES ----------
function loadNotes(){api('/api/notes').then(d=>{notes=d;renderNotes();});}
function saveNote(){
  if(!$('nTitle').value.trim()){alert('Title required!');return;}
  jpost('/api/notes',{title:$('nTitle').value,content:$('nContent').value,folder_name:$('nFolder').value,
    created_at:'',updated_at:''}).then(()=>{closeModal('noteModal');$('nTitle').value='';$('nContent').value='';loadNotes();});
}
function delNote(id){if(confirm('Delete?'))fetch('/api/notes?id='+id,{method:'DELETE'}).then(loadNotes);}
function renderNotes(){
  const folders=['General','Reviewer','Lecture','Personal'];
  $('noteList').innerHTML=notes.length?folders.map(f=>{
    const fn=notes.filter(n=>n.folder_name===f);if(!fn.length)return'';
    return `<div class="card"><h4 style="margin-bottom:10px;">📁 ${f}</h4>${fn.map(n=>
      `<div style="padding:8px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start;">
      <div><div style="font-weight:500;font-size:14px;">${n.title}</div>
      ${n.content?`<div style="font-size:12px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px;">${n.content}</div>`:''}
      <div style="font-size:11px;color:var(--muted);margin-top:2px;">${new Date(n.updated_at).toLocaleDateString('en-PH')}</div></div>
      <button onclick="delNote(${n.id})" style="background:none;border:none;color:var(--danger);cursor:pointer;">🗑️</button></div>`).join('')}</div>`;
  }).join(''):'<div class="empty"><span>📝</span>No notes yet.</div>';
}

// ---------- PROJECTS ----------
function loadProjects(){api('/api/projects').then(d=>{projects=d;renderProjects();});}
function saveProj(){
  if(!$('pName').value.trim()){alert('Name required!');return;}
  jpost('/api/projects',{name:$('pName').value,members:$('pMembers').value,deadline:$('pDeadline').value,status:'Ongoing',created_at:''})
    .then(()=>{closeModal('projModal');loadProjects();});
}
function projDone(id){jpost('/api/projects',{id,status:'Completed'}).then(loadProjects);}
function delProj(id){if(confirm('Delete?'))fetch('/api/projects?id='+id,{method:'DELETE'}).then(loadProjects);}
function renderProjects(){
  $('projList').innerHTML=projects.length?projects.map(p=>`<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
    <h4>${p.name}</h4><span class="badge" style="background:${p.status==='Completed'?'rgba(16,185,129,.1)':'rgba(245,158,11,.1)'};color:${p.status==='Completed'?'var(--success)':'var(--warning)'};">${p.status}</span></div>
    ${p.members?`<p style="font-size:13px;color:var(--muted);"><strong>Members:</strong> ${p.members}</p>`:''}
    ${p.deadline?`<p style="font-size:13px;color:var(--muted);"><strong>Deadline:</strong> ${new Date(p.deadline).toLocaleDateString('en-PH')}</p>`:''}
    <div style="display:flex;gap:8px;margin-top:10px;">
    ${p.status!=='Completed'?`<button class="btn btn-success btn-sm" onclick="projDone(${p.id})">✓ Done</button>`:''}
    <button class="btn btn-danger btn-sm" onclick="delProj(${p.id})">🗑️ Delete</button></div></div>`).join('')
    :'<div class="empty"><span>👥</span>No projects yet.</div>';
}

// ---------- GRADES ----------
function loadGrades(){api('/api/grades').then(d=>{grades=d;renderGrades();calcGPA();});}
function saveGrade(){
  const s=parseFloat($('gScore').value);
  if(!$('gSubject').value.trim()||isNaN(s)||s<0||s>100){alert('Valid subject and score (0-100) required!');return;}
  jpost('/api/grades',{subject:$('gSubject').value,score:s,units:parseFloat($('gUnits').value)||3,semester:$('gSem').value,recorded_at:''})
    .then(()=>{closeModal('gradeModal');loadGrades();});
}
function delGrade(id){if(confirm('Delete?'))fetch('/api/grades?id='+id,{method:'DELETE'}).then(loadGrades);}
function toGPA(s){if(s>=97)return 1;if(s>=93)return 1.25;if(s>=89)return 1.5;if(s>=85)return 1.75;if(s>=81)return 2;
  if(s>=77)return 2.25;if(s>=73)return 2.5;if(s>=69)return 2.75;if(s>=65)return 3;return 5;}
function calcGPA(){if(!grades.length){$('gpaVal').textContent='--';return;}
  let w=0,u=0;grades.forEach(g=>{w+=toGPA(g.score)*g.units;u+=g.units;});
  $('gpaVal').textContent=(w/u).toFixed(2);}
function renderGrades(){
  $('gradeList').innerHTML=grades.length?grades.map(g=>{const gp=toGPA(g.score);
    const c=gp<=1.5?'var(--success)':gp<=2.5?'var(--warning)':'var(--danger)';
    return `<div class="card" style="margin-bottom:10px;"><div style="display:flex;justify-content:space-between;align-items:center;">
    <div><div style="font-weight:500;">${g.subject}</div><div class="task-meta">${g.units} unit${g.units>1?'s':''} · ${g.semester||''}</div></div>
    <div style="text-align:right;"><div style="font-size:20px;font-weight:700;color:${c};">${gp.toFixed(2)}</div>
    <div class="task-meta">${g.score}/100</div></div></div>
    <button onclick="delGrade(${g.id})" style="margin-top:6px;background:none;border:none;color:var(--danger);cursor:pointer;font-size:12px;">🗑️ Delete</button></div>`;}).join('')
    :'<div class="empty"><span>📊</span>No grades recorded.</div>';
}

// ---------- BUDGET ----------
function loadBudget(){api('/api/budget').then(d=>{if(Array.isArray(d)){budget=d;renderBudget();}});}
function saveBudg(){
  const a=parseFloat($('bAmt').value);if(isNaN(a)||a<=0){alert('Valid amount required!');return;}
  jpost('/api/budget',{type:$('bType').value,category:$('bCat').value||'General',amount:a,description:$('bDesc').value,recorded_at:''})
    .then(()=>{closeModal('budgModal');loadBudget();});
}
function delBudg(id){if(confirm('Delete?'))fetch('/api/budget?id='+id,{method:'DELETE'}).then(loadBudget);}
function renderBudget(){
  let inc=0,exp=0;budget.forEach(b=>{if(b.type==='income')inc+=b.amount;else exp+=b.amount;});
  $('budgBal').textContent='₱'+(inc-exp).toFixed(2);$('budgIn').textContent='+₱'+inc.toFixed(2);$('budgOut').textContent='-₱'+exp.toFixed(2);
  $('budgList').innerHTML=budget.length?budget.map(b=>`<div class="card" style="margin-bottom:8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
    <div><div style="font-weight:500;font-size:14px;">${b.category}</div>
    <div class="task-meta">${b.description||'No note'} · ${new Date(b.recorded_at).toLocaleDateString('en-PH')}</div></div>
    <div style="font-weight:600;color:${b.type==='income'?'var(--success)':'var(--danger)'};">${b.type==='income'?'+':'-'}₱${b.amount.toFixed(2)}</div></div></div>`).join('')
    :'<div class="empty"><span>💰</span>No transactions yet.</div>';
}

// ---------- PLANNER / GOALS ----------
function loadGoals(){api('/api/planner').then(d=>{goals=d;renderGoals();});}
function saveGoal(){
  if(!$('goalText').value.trim()){alert('Goal required!');return;}
  jpost('/api/planner',{goal:$('goalText').value,target_date:$('goalDate').value,progress:0,created_at:''})
    .then(()=>{closeModal('goalModal');$('goalText').value='';loadGoals();});
}
function goalProg(id,p){jpost('/api/planner',{id,progress:p}).then(loadGoals);}
function delGoal(id){if(confirm('Delete?'))fetch('/api/planner?id='+id,{method:'DELETE'}).then(loadGoals);}
function renderGoals(){
  $('goalList').innerHTML=goals.length?goals.map(g=>`<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
    <div style="flex:1;"><div style="font-weight:500;font-size:14px;">${g.goal}</div>
    ${g.target_date?`<div class="task-meta">Target: ${new Date(g.target_date).toLocaleDateString('en-PH')}</div>`:''}</div>
    <div style="font-weight:600;color:var(--primary);">${g.progress}%</div></div>
    <div class="progress-bar"><div class="progress-fill" style="width:${g.progress}%;"></div></div>
    <div style="display:flex;gap:6px;align-items:center;">
    <button class="btn btn-outline btn-sm" onclick="goalProg(${g.id},Math.max(0,${g.progress}-10))">-10%</button>
    <button class="btn btn-outline btn-sm" onclick="goalProg(${g.id},Math.min(100,${g.progress}+10))">+10%</button>
    <button class="btn btn-success btn-sm" style="margin-left:auto;" onclick="goalProg(${g.id},100)">✓ Done</button>
    <button class="btn btn-danger btn-sm" onclick="delGoal(${g.id})">🗑️</button></div></div>`).join('')
    :'<div class="empty"><span>🎯</span>No goals yet. Set one!</div>';
}

// ---------- EXPORT ----------
function doExport(){if(!isPremium){openModal('premLockModal');return;}window.location.href='/api/export';}

// ---------- PREMIUM ----------
let myRef=null;
function loadPremium(){
  jpost('/api/premium/request',{}).then(d=>{if(d.success){myRef=d.reference_id;$('refId').value=d.reference_id;
    $('gcNum').textContent=d.gcash_number;$('gcName').textContent=d.gcash_name;}});
  api('/api/premium/status').then(d=>{
    const sc=$('premStatusCard');
    if(d.is_premium){$('payCard').style.display='none';
      sc.innerHTML=`<div style="text-align:center;"><div style="font-size:30px;">✅</div>
      <p style="color:var(--success);font-weight:600;margin:6px 0;">Premium Active!</p>
      <p class="task-meta">Valid until: ${new Date(d.expiry_date.replace(' ','T')).toLocaleDateString('en-PH')}</p>
      <div class="countdown">Expires in <strong>${d.days_left} days</strong></div></div>`;
    }else{$('payCard').style.display='block';
      const last=d.payments&&d.payments[0];
      let statusHtml='<p style="color:var(--muted);font-size:13px;">You are on the <strong>Free Plan</strong>.</p>';
      if(last){
        if(last.status==='pending'&&last.submitted_at){statusHtml=`<div class="countdown" style="background:var(--warning);">⏳ Payment submitted — Waiting for admin approval...</div>`;}
        else if(last.status==='rejected'){statusHtml=`<div class="countdown" style="background:var(--danger);">❌ Rejected: ${last.reject_reason||'Please resubmit.'}</div>`;}
      }
      sc.innerHTML=statusHtml+`<div class="countdown"><div style="font-size:24px;">₱50.00</div><div style="font-size:12px;opacity:.9;">for 30 days</div></div>`;
    }
  });
}
function submitPayment(){
  const gcashRef=$('gcashRef').value.trim();
  if(!gcashRef){$('payErr').textContent='GCash reference number required!';$('payErr').classList.add('show');return;}
  $('payErr').classList.remove('show');
  const fd=new FormData();
  fd.append('reference_id',myRef);fd.append('gcash_ref',gcashRef);
  const f=$('screenshot').files[0];if(f)fd.append('screenshot',f);
  fetch('/api/premium/submit',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.success){alert('✅ Submitted! Waiting for admin approval.');loadPremium();}
    else{$('payErr').textContent=d.error;$('payErr').classList.add('show');}
  });
}

// ---------- ADMIN ----------
function loadAdmin(){
  api('/api/admin/pending').then(d=>{
    $('adminPending').innerHTML=d.length?d.map(p=>`<div class="card" style="margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
      <div><strong>${p.full_name}</strong> <span class="task-meta">(${p.email})</span><br>
      <span class="task-meta">Ref ID: ${p.reference_id} · GCash Ref: ${p.gcash_ref||'--'} · ₱${p.amount}</span><br>
      ${p.screenshot?`<a href="/uploads/${p.screenshot}" target="_blank" style="font-size:12px;">📷 View Screenshot</a>`:'<span class="task-meta">No screenshot</span>'}</div>
      <div style="display:flex;gap:6px;">
      <button class="btn btn-success btn-sm" onclick="approvePay(${p.id})">✅ Approve</button>
      <button class="btn btn-danger btn-sm" onclick="askReject(${p.id})">❌ Reject</button></div></div></div>`).join('')
      :'<div class="empty"><span>✅</span>No pending requests.</div>';
  });
  api('/api/admin/users').then(d=>{
    $('adminUsers').innerHTML=d.map(u=>`<tr><td>${u.full_name}</td><td>${u.student_id||'--'}</td><td>${u.course_year||'--'}</td>
      <td>${u.is_premium?'👑 Yes':'No'}</td><td>${u.premium_expiry?new Date(u.premium_expiry.replace(' ','T')).toLocaleDateString('en-PH'):'--'}</td></tr>`).join('');
  });
  api('/api/admin/all-payments').then(d=>{
    $('adminPayments').innerHTML=d.map(p=>{const c=p.status==='approved'?'var(--success)'😛.status==='rejected'?'var(--danger)':'var(--warning)';
      return `<tr><td>${p.full_name}</td><td>${p.reference_id}</td><td>₱${p.amount}</td>
      <td style="color:${c};font-weight:600;">${p.status}</td><td>${p.submitted_at?new Date(p.submitted_at.replace(' ','T')).toLocaleDateString('en-PH'):'--'}</td></tr>`;}).join('');
  });
}
function approvePay(id){jpost('/api/admin/approve',{payment_id:id}).then(d=>{alert('✅ Approved! '+d.message);loadAdmin();});}
function askReject(id){rejectPid=id;$('rejectReason').value='';openModal('rejectModal');}
function confirmReject(){jpost('/api/admin/reject',{payment_id:rejectPid,reason:$('rejectReason').value||'Payment could not be verified.'})
  .then(()=>{closeModal('rejectModal');loadAdmin();});}

// ---------- FRIENDS ----------
let searchTimer=null;
function searchFriends(){clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>{
    const q=$('friendSearch').value.trim();if(q.length<2){$('friendSearchResults').innerHTML='';return;}
    api('/api/users/search?q='+encodeURIComponent(q)).then(d=>{
      $('friendSearchResults').innerHTML=d.length?d.map(u=>`<div class="task-item">
        <div><strong>${u.full_name}</strong> <span class="task-meta">${u.student_id||''} · ${u.course_year||''}</span>
        <br>${u.online?'<span class="online-dot"></span>Online':'<span class="offline-dot"></span>Offline'}</div>
        <div style="margin-left:auto;">${u.are_friends?'<span class="badge b-later">✓ Friends</span>':
          <button class="btn btn-primary btn-sm" onclick="addFriend('${u.user_id}')">+ Add</button>`}</div></div>).join('')
        :'<div class="empty" style="padding:14px;"><span>🔍</span>No users found.</div>';
    });
  },400);
}
function addFriend(uid){jpost('/api/friends/requests',{to_user:uid}).then(d=>{
  if(d.success){alert('✅ Friend request sent!');searchFriends();}
  else{alert(d.error);if(d.premium_required)go('premium');}});
}
function loadFriendRequests(){api('/api/friends/requests').then(d=>{
  $('reqCount').style.display=d.length?'inline-block':'none';$('reqCount').textContent=d.length;
  $('friendRequests').innerHTML=d.length?d.map(r=>`<div class="task-item">
    <div><strong>${r.full_name}</strong> <span class="task-meta">${r.student_id||''} · ${r.course_year||''}</span></div>
    <div style="margin-left:auto;display:flex;gap:6px;">
    <button class="btn btn-success btn-sm" onclick="respondReq(${r.id},'accept')">✓ Accept</button>
    <button class="btn btn-danger btn-sm" onclick="respondReq(${r.id},'decline')">✕ Decline</button></div></div>`).join('')
    :'<div class="empty" style="padding:14px;"><span>📭</span>No pending requests.</div>';
});}
function respondReq(id,act){jpost('/api/friends/respond',{request_id:id,action:act}).then(d=>{
  if(d.success){loadFriendRequests();loadFriends();}else{alert(d.error);if(d.premium_required)go('premium');}});
}
function loadFriends(){api('/api/friends').then(d=>{friends=d;
  $('friendCountLabel').textContent=`${d.length}${ME&&ME.friend_limit!==null?' / '+ME.friend_limit+' (Free limit)':''}`;
  $('friendList').innerHTML=d.length?d.map(f=>`<div class="task-item">
    <div>${f.online?'<span class="online-dot"></span>':'<span class="offline-dot"></span>'}<strong>${f.full_name}</strong>
    <span class="task-meta">${f.student_id||''}</span><br><span class="task-meta">${f.online?'Online':'Offline'}</span></div>
    <button class="btn btn-primary btn-sm" style="margin-left:auto;" onclick="openChat('${f.user_id}','${f.full_name}')">💬 Chat</button></div>`).join('')
    :'<div class="empty" style="padding:14px;"><span>👥</span>No friends yet. Search above!</div>';
  // populate group member picker
  $('grpMembers').innerHTML=d.map(f=>`<label style="display:flex;align-items:center;gap:8px;font-weight:400;padding:4px 0;">
    <input type="checkbox" value="${f.user_id}" class="grpMem" style="width:auto;margin:0;"> ${f.full_name}</label>`).join('')||'<span class="task-meta">Add friends first to create a group.</span>';
});}

// ---------- DIRECT CHAT ----------
function openChat(fid,name){currentChatFriend=fid;dmLastId=0;
  $('chatTitle').textContent=name;$('dmChatBox').innerHTML='';go('chat');
  loadDm();if(chatTimer)clearInterval(chatTimer);chatTimer=setInterval(loadDm,2000);}
function loadDm(){if(!currentChatFriend)return;
  api(/api/chat/${currentChatFriend}?after_id=${dmLastId}).then(d=>{
    if(d.length){d.forEach(m=>{dmLastId=m.id;appendDm(m);});$('dmChatBox').scrollTop=$('dmChatBox').scrollHeight;}
  });
  api(/api/typing?conv=dm_${currentChatFriend}).then(d=>{
    $('dmTyping').textContent=d.length?d.join(', ')+(d.length>1?' are ':' is ')+'typing...':'';
  });
}
function appendDm(m){const div=document.createElement('div');
  div.className='msg '+(m.sender_id===ME.user_id||m.sender_id===ME?'me':'them');
  div.textContent=m.content;$('dmChatBox').appendChild(div);}
let dmTypingTimer=null;
function typingDm(){jpost('/api/typing',{conv:'dm_'+currentChatFriend});
  clearTimeout(dmTypingTimer);dmTypingTimer=setTimeout(()=>{},1000);}
function sendDm(){const txt=$('dmInput').value.trim();if(!txt)return;
  jpost(/api/chat/${currentChatFriend},{content:txt}).then(()=>{$('dmInput').value='';loadDm();});}

// ---------- GROUPS ----------
function loadGroups(){api('/api/groups').then(d=>{
  $('groupList').innerHTML=d.length?d.map(g=>`<div class="card" style="cursor:pointer;" onclick="openGchat(${g.id},'${g.name.replace(/'/g,"\\'")}')">
    <div style="display:flex;justify-content:space-between;align-items:center;">
    <div><strong>💬 ${g.name}</strong><div class="task-meta">${g.members.length} member${g.members.length>1?'s':''}: ${g.members.map(m=>m.full_name).join(', ')}</div></div>
    <span style="font-size:20px;">→</span></div></div>`).join('')
    :'<div class="empty"><span>💬</span>No groups yet. Create one! (Premium)</div>';
});}
function createGroup(){
  if(!isPremium){alert('Premium required!');return;}
  const name=$('grpName').value.trim();if(!name){alert('Group name required!');return;}
  const members=[...document.querySelectorAll('.grpMem:checked')].map(c=>c.value);
  jpost('/api/groups',{name,members}).then(d=>{if(d.success){closeModal('groupModal');$('grpName').value='';loadGroups();}else alert(d.error);});
}
function openGchat(gid,name){currentGroup=gid;gLastId=0;
  $('gchatTitle').textContent=name;$('gChatBox').innerHTML='';go('gchat');
  loadG();if(gChatTimer)clearInterval(gChatTimer);gChatTimer=setInterval(loadG,2000);}
function loadG(){if(!currentGroup)return;
  api(/api/groups/${currentGroup}/messages?after_id=${gLastId}).then(d=>{
    if(d.length){d.forEach(m=>{gLastId=m.id;appendG(m);});$('gChatBox').scrollTop=$('gChatBox').scrollHeight;}
  });
  api(/api/typing?conv=group_${currentGroup}).then(d=>{
    $('gTyping').textContent=d.length?d.join(', ')+(d.length>1?' are ':' is ')+'typing...':'';
  });
}
function appendG(m){const div=document.createElement('div');
  const mine=(m.sender_id===ME.user_id||m.sender_id===ME);
  div.className='msg '+(mine?'me':'them');
  if(!mine){const s=document.createElement('div');s.className='sender';s.textContent=m.full_name;div.appendChild(s);}
  div.appendChild(document.createTextNode(m.content));$('gChatBox').appendChild(div);}
let gTypingTimer=null;
function typingG(){jpost('/api/typing',{conv:'group_'+currentGroup});clearTimeout(gTypingTimer);gTypingTimer=setTimeout(()=>{},1000);}
function sendG(){const txt=$('gInput').value.trim();if(!txt)return;
  jpost(/api/groups/${currentGroup}/messages,{content:txt}).then(()=>{$('gInput').value='';loadG();});}
</script>
</body>
</html>
"""

try:
    init_db()
    print("✅ Database connected & tables ready (Neon PostgreSQL).")
except Exception as e:
    print("⚠️  WARNING: Could not initialize database:", e)
    print("   Make sure DATABASE_URL is set to your Neon connection string.")
    print("   Example: export DATABASE_URL='postgresql://user:pass@host/db?sslmode=require'")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
