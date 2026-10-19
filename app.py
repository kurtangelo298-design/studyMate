
import os
import io
import csv
import json
import base64
import html
import datetime
import secrets
from functools import wraps

from flask import (Flask, request, redirect, url_for, session, flash,
                   jsonify, Response, abort)
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'taskhive-dev-secret-change-me')
app.permanent_session_lifetime = datetime.timedelta(days=31)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB upload cap

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:postgres@localhost:5432/taskhive'
)
GCASH_NUMBER = os.environ.get('GCASH_NUMBER', '0917-000-0000')  # <-- palitan
GCASH_NAME = os.environ.get('GCASH_NAME', 'TaskHive Premium')
PREMIUM_PRICE = 50.00
PREMIUM_DAYS = 30
FREE_FRIEND_LIMIT = 3  # free users: max 3 friends, no group chat

e = html.escape  # shortcut for HTML escaping

# In-memory typing indicator (single-process fine)
typing_state = {}  # key: ('dm', min, max, user_id) or ('grp', group_id, user_id) -> timestamp

QUOTES = [
    "The secret of getting ahead is getting started.",
    "Success is the sum of small efforts, repeated day in and day out.",
    "Don't watch the clock; do what it does. Keep going.",
    "The future depends on what you do today.",
    "Study while others are sleeping; prepare while others are daydreaming.",
    "Believe you can and you're halfway there.",
    "It always seems impossible until it's done.",
    "Push yourself, because no one else is going to do it for you.",
    "Great things never come from comfort zones.",
    "Dream it. Wish it. Do it.",
    "Little by little, one travels far.",
    "Stay focused and never give up.",
]

# ---------------------------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------------------------
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def query_all(sql, args=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]


def query_one(sql, args=()):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, args)
            r = cur.fetchone()
            return dict(r) if r else None


def execute(sql, args=(), returning=False):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, args)
            if returning:
                r = cur.fetchone()
                return dict(r) if r else None
    return None


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                student_id TEXT UNIQUE NOT NULL,
                course_year TEXT,
                password_hash TEXT NOT NULL,
                join_date DATE DEFAULT CURRENT_DATE,
                theme TEXT DEFAULT 'light',
                is_admin BOOLEAN DEFAULT FALSE,
                last_seen TIMESTAMP DEFAULT NOW()
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS premium_payments (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                reference_number TEXT,
                receipt_base64 TEXT,
                status TEXT DEFAULT 'pending',
                submitted_at TIMESTAMP DEFAULT NOW(),
                activation_date DATE,
                expiry_date DATE
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                due_datetime TIMESTAMP,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                day TEXT NOT NULL,
                start_time TIME,
                end_time TIME,
                room TEXT
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                title TEXT,
                content TEXT,
                folder TEXT DEFAULT 'General',
                created_at TIMESTAMP DEFAULT NOW()
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                members TEXT,
                deadline DATE,
                progress INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS grades (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                score NUMERIC(5,2),
                units NUMERIC(4,1) DEFAULT 3.0,
                semester TEXT
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS study_goals (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                goal TEXT NOT NULL,
                target_date DATE,
                progress INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS budget (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                description TEXT,
                amount NUMERIC(10,2),
                type TEXT DEFAULT 'expense',
                date DATE DEFAULT CURRENT_DATE
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                exam_date DATE,
                created_at TIMESTAMP DEFAULT NOW()
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS friendships (
                id SERIAL PRIMARY KEY,
                requester_id INT REFERENCES users(id) ON DELETE CASCADE,
                addressee_id INT REFERENCES users(id) ON DELETE CASCADE,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(requester_id, addressee_id)
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                creator_id INT REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INT REFERENCES groups(id) ON DELETE CASCADE,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY (group_id, user_id)
            );""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                sender_id INT REFERENCES users(id) ON DELETE CASCADE,
                receiver_id INT,
                group_id INT,
                content TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                is_read BOOLEAN DEFAULT FALSE
            );""")
            # seed admin
            cur.execute("SELECT id FROM users WHERE email='admin@taskhive.com'")
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO users (full_name, email, student_id, course_year, password_hash, is_admin) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    ("TaskHive Admin", "admin@taskhive.com", "ADMIN-001", "N/A",
                     generate_password_hash("Admin@12345"), True))
        conn.commit()


# ---------------------------------------------------------------------------
# AUTH / SESSION HELPERS
# ---------------------------------------------------------------------------
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return query_one("SELECT * FROM users WHERE id=%s", (uid,))


def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        u = current_user()
        if not u or not u.get('is_admin'):
            abort(403)
        return f(*a, **kw)
    return wrap


def premium_active(user_id):
    """Return dict(activation_date, expiry_date, days_left) or None."""
    row = query_one(
        "SELECT activation_date, expiry_date FROM premium_payments "
        "WHERE user_id=%s AND status='approved' AND expiry_date >= CURRENT_DATE "
        "ORDER BY expiry_date DESC LIMIT 1", (user_id,))
    if not row:
        return None
    days_left = (row['expiry_date'] - datetime.date.today()).days
    return {'activation_date': row['activation_date'],
            'expiry_date': row['expiry_date'],
            'days_left': max(0, days_left)}


def is_premium(user_id):
    return premium_active(user_id) is not None


def friend_ids(user_id):
    rows = query_all(
        "SELECT requester_id, addressee_id FROM friendships "
        "WHERE status='accepted' AND (requester_id=%s OR addressee_id=%s)",
        (user_id, user_id))
    ids = set()
    for r in rows:
        ids.add(r['requester_id'] if r['addressee_id'] == user_id else r['addressee_id'])
    return ids


def is_online(user):
    if not user or not user.get('last_seen'):
        return False
    ls = user['last_seen']
    if isinstance(ls, str):
        ls = datetime.datetime.fromisoformat(ls.replace('Z', ''))
    return (datetime.datetime.now() - ls).total_seconds() < 120


@app.before_request
def touch_last_seen():
    uid = session.get('user_id')
    if uid and request.endpoint and not request.path.startswith('/static'):
        try:
            execute("UPDATE users SET last_seen=NOW() WHERE id=%s", (uid,))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CSS (responsive)
# ---------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
 --bg:#f4f6fb; --card:#ffffff; --text:#1a2233; --muted:#6b7280;
 --primary:#4f46e5; --primary-soft:#eef2ff; --green:#16a34a; --orange:#ea580c;
 --red:#dc2626; --blue:#2563eb; --border:#e5e7eb; --shadow:0 2px 10px rgba(0,0,0,.06);
 --nav:#ffffff; --chat-me:#4f46e5; --chat-them:#e5e7eb;
}
body.dark{
 --bg:#0f1420; --card:#1a2233; --text:#e6e9f2; --muted:#9aa3b5;
 --border:#2a3348; --shadow:0 2px 10px rgba(0,0,0,.4); --nav:#1a2233;
 --primary-soft:#262d4a; --chat-them:#2a3348;
}
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;background:var(--bg);color:var(--text);
 min-height:100vh;line-height:1.5}
a{color:var(--primary);text-decoration:none}
.wrap{max-width:1100px;margin:0 auto;padding:20px 20px 90px 20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;
 padding:18px;margin-bottom:16px;box-shadow:var(--shadow)}
h1{font-size:22px;margin-bottom:6px}
h2{font-size:18px;margin-bottom:10px}
h3{font-size:15px;margin-bottom:8px}
.muted{color:var(--muted);font-size:13px}
.grid{display:grid;gap:14px}
.grid-2{grid-template-columns:1fr 1fr}
.grid-3{grid-template-columns:repeat(3,1fr)}
.grid-4{grid-template-columns:repeat(4,1fr)}
.btn{display:inline-block;background:var(--primary);color:#fff;border:none;
 padding:10px 16px;border-radius:10px;font-size:14px;cursor:pointer;font-weight:600}
.btn:hover{opacity:.92}
.btn-sm{padding:6px 12px;font-size:12px;border-radius:8px}
.btn-green{background:var(--green)}
.btn-orange{background:var(--orange)}
.btn-red{background:var(--red)}
.btn-gray{background:var(--muted)}
.btn-outline{background:transparent;color:var(--primary);border:1px solid var(--primary)}
input,select,textarea{width:100%;padding:10px 12px;border:1px solid var(--border);
 border-radius:10px;font-size:14px;background:var(--card);color:var(--text);margin-bottom:10px}
label{font-size:13px;font-weight:600;display:block;margin-bottom:4px;color:var(--muted)}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;color:#fff}
.b-complete{background:var(--green)}
.b-today{background:var(--orange)}
.b-overdue{background:var(--red)}
.b-pending{background:var(--blue)}
.b-premium{background:linear-gradient(90deg,#f59e0b,#ef4444)}
.stat{text-align:center;padding:14px;border-radius:12px;background:var(--primary-soft)}
.stat .num{font-size:26px;font-weight:800;color:var(--primary)}
.stat .lbl{font-size:12px;color:var(--muted)}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.spread{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.item{border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:8px;background:var(--card)}
.item .actions{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
@media (max-width:760px){.item .actions{display:none}}
.flash{background:#fef3c7;color:#92400e;padding:10px 14px;border-radius:10px;margin-bottom:12px;font-size:13px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:10px;flex-wrap:wrap}
.search{flex:1;min-width:180px}
.tabs{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}
.tab{padding:8px 14px;border-radius:20px;background:var(--card);border:1px solid var(--border);
 font-size:13px;cursor:pointer;color:var(--text)}
.tab.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.progress{height:8px;background:var(--border);border-radius:6px;overflow:hidden;margin-top:6px}
.progress>div{height:100%;background:var(--primary)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px;text-align:left;border-bottom:1px solid var(--border)}
/* Sidebar (desktop) */
.sidebar{position:fixed;left:0;top:0;bottom:0;width:210px;background:var(--nav);
 border-right:1px solid var(--border);padding:20px 14px;display:flex;flex-direction:column;gap:4px;z-index:40}
.sidebar .logo{font-size:20px;font-weight:800;color:var(--primary);margin-bottom:14px;padding:0 8px}
.sidebar a{display:block;padding:10px 12px;border-radius:10px;color:var(--text);font-size:14px;font-weight:600}
.sidebar a:hover{background:var(--primary-soft)}
.sidebar a.active{background:var(--primary);color:#fff}
.sidebar .spacer{flex:1}
.main{margin-left:210px}
/* Bottom nav (mobile) */
.bottomnav{display:none;position:fixed;bottom:0;left:0;right:0;background:var(--nav);
 border-top:1px solid var(--border);z-index:50;justify-content:space-around;align-items:center;padding:6px 4px}
.bottomnav a{flex:1;text-align:center;font-size:11px;color:var(--muted);padding:4px 2px;font-weight:600}
.bottomnav a.active{color:var(--primary)}
.bottomnav .fab{flex:0 0 auto;background:var(--primary);color:#fff;width:46px;height:46px;
 border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;margin-top:-22px;
 box-shadow:0 4px 12px rgba(79,70,229,.5);cursor:pointer;border:none}
/* Modal */
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100;
 align-items:center;justify-content:center;padding:16px}
.modal.open{display:flex}
.modal .box{background:var(--card);border-radius:14px;padding:22px;width:100%;max-width:420px;max-height:90vh;overflow:auto}
/* Chat */
.chatbox{height:420px;overflow-y:auto;padding:12px;background:var(--bg);border-radius:12px;border:1px solid var(--border);margin-bottom:10px}
.msg{margin-bottom:8px;max-width:75%}
.msg .who{font-size:11px;color:var(--muted);margin-bottom:2px}
.msg .bubble{padding:8px 12px;border-radius:14px;font-size:14px;display:inline-block;word-break:break-word}
.msg.me{margin-left:auto;text-align:right}
.msg.me .bubble{background:var(--chat-me);color:#fff;border-bottom-right-radius:4px}
.msg.them .bubble{background:var(--chat-them);color:var(--text);border-bottom-left-radius:4px}
.msg .time{font-size:10px;color:var(--muted);margin-top:2px}
.typing{font-size:12px;color:var(--muted);font-style:italic;height:18px;margin-bottom:4px}
.online-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#9ca3af;margin-right:5px}
.online-dot.on{background:var(--green)}
.lock{background:linear-gradient(135deg,#fef3c7,#fee2e2);border:1px dashed #f59e0b;
 border-radius:14px;padding:30px;text-align:center}
.authwrap{max-width:420px;margin:60px auto;padding:20px}
.qr{width:180px;height:180px;background:#fff;border:8px solid #fff;border-radius:10px;margin:10px auto;display:flex;align-items:center;justify-content:center;color:#333;font-size:12px;text-align:center}
@media (max-width:760px){
 .sidebar{display:none}
 .main{margin-left:0}
 .bottomnav{display:flex}
 .wrap{padding:14px 14px 90px 14px}
 .grid-2,.grid-3,.grid-4{grid-template-columns:1fr}
 h1{font-size:19px}
 .chatbox{height:52vh}
}
"""

# ---------------------------------------------------------------------------
# SHARED JS
# ---------------------------------------------------------------------------
JS = """
function openModal(id){document.getElementById(id).classList.add('open')}
function closeModal(id){document.getElementById(id).classList.remove('open')}
document.addEventListener('click',function(e){
 if(e.target.classList.contains('modal')) e.target.classList.remove('open');
});
// simple swipe-left to reveal actions on .swipe items
var startX=null;
document.addEventListener('touchstart',function(e){var t=e.target.closest('.swipe');if(t)startX=e.touches[0].clientX;},{passive:true});
document.addEventListener('touchend',function(e){
 var t=e.target.closest('.swipe');if(!t||startX===null)return;
 var dx=e.changedTouches[0].clientX-startX;startX=null;
 var act=t.querySelector('.actions');if(!act)return;
 if(dx<-40){act.style.display='flex';}else if(dx>40){act.style.display='none';}
},{passive:true});
"""


# ---------------------------------------------------------------------------
# LAYOUT RENDERER
# ---------------------------------------------------------------------------
def render_page(title, content, active='', user=None, extra_head=''):
    user = user or current_user()
    theme = user['theme'] if user else 'light'
    dark_class = ' class="dark"' if theme == 'dark' else ''

    # desktop sidebar links
    links = [
        ('/', 'Home', 'home'),
        ('/tasks', 'Tasks', 'tasks'),
        ('/schedule', 'Schedule', 'schedule'),
        ('/notes', 'Notes', 'notes'),
        ('/projects', 'Projects', 'projects'),
        ('/grades', 'Grades', 'grades'),
        ('/planner', 'Study Planner', 'planner'),
        ('/friends', 'Friends & Chat', 'friends'),
        ('/premium', 'Premium', 'premium'),
        ('/profile', 'Profile', 'profile'),
    ]
    if user and user.get('is_admin'):
        links.append(('/admin', 'Admin', 'admin'))

    sidebar = '<div class="sidebar"><div class="logo">TaskHive</div>'
    for href, label, key in links:
        sidebar += '<a href="%s"%s>%s</a>' % (href, ' class="active"' if active == key else '', e(label))
    sidebar += '<div class="spacer"></div>'
    if user:
        sidebar += '<a href="/logout">Logout</a>'
    sidebar += '</div>'

    # mobile bottom nav: Home, Tasks, +, Schedule, Friends, Profile
    bn = ('<nav class="bottomnav">'
          '<a href="/"%s>Home</a>'
          '<a href="/tasks"%s>Tasks</a>'
          '<button class="fab" onclick="openModal(\'quickadd\')" title="Quick Add">+</button>'
          '<a href="/schedule"%s>Schedule</a>'
          '<a href="/friends"%s>Friends</a>'
          '<a href="/profile"%s>Profile</a>'
          '</nav>') % (
        ' class="active"' if active == 'home' else '',
        ' class="active"' if active == 'tasks' else '',
        ' class="active"' if active == 'schedule' else '',
        ' class="active"' if active == 'friends' else '',
        ' class="active"' if active == 'profile' else '',
    )

    quick_add = ''
    if user:
        quick_add = """
        <div class="modal" id="quickadd"><div class="box">
          <h2>Quick Add Task</h2>
          <form method="post" action="/tasks/add">
            <label>Title</label><input name="title" required autofocus>
            <label>Due date & time</label><input type="datetime-local" name="due_datetime">
            <label>Priority</label>
            <select name="priority">
              <option value="low">Low</option><option value="medium" selected>Medium</option>
              <option value="high">High</option>
            </select>
            <div class="row"><button class="btn" type="submit">Add Task</button>
            <button type="button" class="btn btn-gray" onclick="closeModal('quickadd')">Cancel</button></div>
          </form></div></div>"""

    page = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s - TaskHive</title>
<style>%s</style>
%s
</head>
<body%s>
%s
<div class="main">
<div class="wrap">
%s
</div>
</div>
%s
%s
<script>%s</script>
</body></html>""" % (
        e(title), CSS, extra_head, dark_class, sidebar, content, bn, quick_add, JS)
    return page


def flash_msg(text):
    """Store a flash message in the session (mutable list -> mark modified)."""
    session.setdefault('_flashes', [])
    session['_flashes'].append(text)
    session.modified = True


def render_flashes():
    msgs = session.pop('_flashes', [])
    if not msgs:
        return ''
    return ''.join('<div class="flash">%s</div>' % e(m) for m in msgs)


# ---------------------------------------------------------------------------
# TASK STATUS HELPER
# ---------------------------------------------------------------------------
def task_status(task):
    if task['status'] == 'complete':
        return 'complete'
    due = task.get('due_datetime')
    if not due:
        return 'pending'
    if isinstance(due, str):
        due = datetime.datetime.fromisoformat(due.replace('Z', ''))
    now = datetime.datetime.now()
    if due < now:
        return 'overdue'
    if due.date() == now.date():
        return 'today'
    return 'pending'


STATUS_BADGE = {
    'complete': '<span class="badge b-complete">Complete</span>',
    'today': '<span class="badge b-today">Due Today</span>',
    'overdue': '<span class="badge b-overdue">Overdue</span>',
    'pending': '<span class="badge b-pending">Pending</span>',
}


def fmt_dt(v):
    if not v:
        return 'No due date'
    if isinstance(v, str):
        try:
            v = datetime.datetime.fromisoformat(v.replace('Z', ''))
        except Exception:
            return v
    return v.strftime('%b %d, %Y %I:%M %p')


def fmt_date(v):
    if not v:
        return ''
    if isinstance(v, str):
        try:
            v = datetime.date.fromisoformat(v[:10])
        except Exception:
            return v
    return v.strftime('%b %d, %Y')


# ===========================================================================
# AUTH ROUTES
# ===========================================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        student_id = request.form.get('student_id', '').strip()
        course_year = request.form.get('course_year', '').strip()
        password = request.form.get('password', '')
        if not all([full_name, email, student_id, password]):
            flash_msg('All fields are required.')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash_msg('Password must be at least 6 characters.')
            return redirect(url_for('register'))
        existing = query_one("SELECT id FROM users WHERE email=%s OR student_id=%s",
                             (email, student_id))
        if existing:
            flash_msg('Email or Student ID already registered.')
            return redirect(url_for('register'))
        execute(
            "INSERT INTO users (full_name,email,student_id,course_year,password_hash) "
            "VALUES (%s,%s,%s,%s,%s)",
            (full_name, email, student_id, course_year, generate_password_hash(password)))
        u = query_one("SELECT * FROM users WHERE email=%s", (email,))
        session['user_id'] = u['id']
        session.permanent = True
        return redirect(url_for('dashboard'))
    content = render_flashes() + """
    <div class="authwrap"><div class="card">
      <h1>Create your TaskHive account</h1>
      <p class="muted" style="margin-bottom:14px">Plan * Study * Achieve</p>
      <form method="post">
        <label>Full Name</label><input name="full_name" required>
        <label>Email</label><input type="email" name="email" required>
        <label>Student ID</label><input name="student_id" required>
        <label>Course & Year</label><input name="course_year" placeholder="e.g. BSCS 2nd Year">
        <label>Password</label><input type="password" name="password" required minlength="6">
        <button class="btn" style="width:100%" type="submit">Register</button>
      </form>
      <p class="muted" style="margin-top:12px">Already have an account? <a href="/login">Login</a></p>
    </div></div>"""
    return render_page('Register', content)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember')
        u = query_one("SELECT * FROM users WHERE email=%s", (email,))
        if not u or not check_password_hash(u['password_hash'], password):
            flash_msg('Invalid email or password.')
            return redirect(url_for('login'))
        session['user_id'] = u['id']
        session.permanent = bool(remember)
        return redirect(url_for('dashboard'))
    content = render_flashes() + """
    <div class="authwrap"><div class="card">
      <h1>Welcome back to TaskHive</h1>
      <p class="muted" style="margin-bottom:14px">Login to continue</p>
      <form method="post">
        <label>Email</label><input type="email" name="email" required>
        <label>Password</label><input type="password" name="password" required>
        <label style="display:flex;align-items:center;gap:8px;font-weight:400">
          <input type="checkbox" name="remember" style="width:auto;margin:0"> Remember me</label>
        <button class="btn" style="width:100%" type="submit">Login</button>
      </form>
      <p class="muted" style="margin-top:12px">No account? <a href="/register">Register here</a></p>
    </div></div>"""
    return render_page('Login', content)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    u = current_user()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        course_year = request.form.get('course_year', '').strip()
        if full_name:
            execute("UPDATE users SET full_name=%s, course_year=%s WHERE id=%s",
                    (full_name, course_year, u['id']))
            flash_msg('Profile updated.')
        return redirect(url_for('profile'))
    u = current_user()
    prem = premium_active(u['id'])
    prem_block = ''
    if prem:
        prem_block = """
        <div class="card"><h3><span class="badge b-premium">PREMIUM</span></h3>
        <p>Activation: %s</p><p>Expiry: %s</p>
        <p><strong>Days remaining: %d</strong></p></div>""" % (
            fmt_date(prem['activation_date']), fmt_date(prem['expiry_date']), prem['days_left'])
    else:
        prem_block = ('<div class="card"><p>You are on the <strong>Free plan</strong>. '
                      '<a href="/premium">Unlock Premium</a> for all features.</p></div>')
    content = render_flashes() + """
    <h1>My Profile</h1>
    <div class="card">
      <form method="post">
        <label>Full Name</label><input name="full_name" value="%s">
        <label>Email</label><input value="%s" disabled>
        <label>Student ID</label><input value="%s" disabled>
        <label>Course & Year</label><input name="course_year" value="%s">
        <label>Join Date</label><input value="%s" disabled>
        <button class="btn" type="submit">Save Changes</button>
      </form>
    </div>
    %s
    <div class="card">
      <h3>Appearance</h3>
      <p>Current theme: <strong>%s</strong></p>
      <form method="post" action="/theme" style="margin-top:8px">
        <button class="btn btn-outline" type="submit">Toggle Dark / Light Mode</button>
      </form>
    </div>
    """ % (e(u['full_name']), e(u['email']), e(u['student_id']),
           e(u['course_year'] or ''), fmt_date(u['join_date']), prem_block, e(u['theme']))
    return render_page('Profile', content, active='profile', user=u)


@app.route('/theme', methods=['POST'])
@login_required
def toggle_theme():
    u = current_user()
    new_theme = 'dark' if u['theme'] == 'light' else 'light'
    execute("UPDATE users SET theme=%s WHERE id=%s", (new_theme, u['id']))
    return redirect(request.referrer or url_for('dashboard'))


# ===========================================================================
# DASHBOARD
# ===========================================================================
@app.route('/')
@login_required
def dashboard():
    u = current_user()
    now = datetime.datetime.now()
    hour = now.hour
    if hour < 12:
        greeting = 'Good morning'
    elif hour < 18:
        greeting = 'Good afternoon'
    else:
        greeting = 'Good evening'
    quote = QUOTES[now.timetuple().tm_yday % len(QUOTES)]

    day_name = now.strftime('%A')
    today_sched = query_all(
        "SELECT * FROM schedules WHERE user_id=%s AND day=%s ORDER BY start_time",
        (u['id'], day_name))

    upcoming = query_all(
        "SELECT * FROM tasks WHERE user_id=%s AND status='pending' AND due_datetime IS NOT NULL "
        "ORDER BY due_datetime ASC LIMIT 5", (u['id']))

    stats = query_one(
        "SELECT "
        "COUNT(*) FILTER (WHERE status='complete') AS complete, "
        "COUNT(*) FILTER (WHERE status='pending') AS pending, "
        "COUNT(*) FILTER (WHERE status='pending' AND due_datetime < NOW()) AS overdue "
        "FROM tasks WHERE user_id=%s", (u['id']))

    sched_html = ''.join(
        '<div class="item"><strong>%s</strong> <span class="muted">%s - %s · %s</span></div>'
        % (e(s['subject']), str(s['start_time'])[:5], str(s['end_time'])[:5], e(s['room'] or ''))
        for s in today_sched) or '<p class="muted">No classes today.</p>'

    up_html = ''
    for t in upcoming:
        st = task_status(t)
        up_html += ('<div class="item spread"><div><strong>%s</strong><br>'
                    '<span class="muted">%s</span></div>%s</div>'
                    % (e(t['title']), fmt_dt(t['due_datetime']), STATUS_BADGE[st]))
    if not up_html:
        up_html = '<p class="muted">No upcoming deadlines. Add a task!</p>'

    content = render_flashes() + """
    <div class="topbar"><div>
      <h1>%s, %s!</h1>
      <p class="muted">&ldquo;%s&rdquo;</p>
    </div>
    <a class="btn btn-sm" href="/tasks">View All Tasks</a></div>

    <div class="grid grid-3" style="margin-bottom:16px">
      <div class="stat"><div class="num">%s</div><div class="lbl">Complete</div></div>
      <div class="stat"><div class="num">%s</div><div class="lbl">Pending</div></div>
      <div class="stat"><div class="num" style="color:var(--red)">%s</div><div class="lbl">Overdue</div></div>
    </div>

    <div class="grid grid-2">
      <div class="card"><h2>Today's Schedule (%s)</h2>%s</div>
      <div class="card"><h2>Upcoming Deadlines</h2>%s</div>
    </div>
    """ % (e(greeting), e(u['full_name'].split()[0]), e(quote),
           stats['complete'], stats['pending'], stats['overdue'],
           day_name, sched_html, up_html)
    return render_page('Home', content, active='home', user=u)


# ===========================================================================
# TASKS
# ===========================================================================
@app.route('/tasks')
@login_required
def tasks():
    u = current_user()
    q = request.args.get('q', '').strip()
    if q:
        rows = query_all(
            "SELECT * FROM tasks WHERE user_id=%s AND title ILIKE %s ORDER BY due_datetime NULLS LAST",
            (u['id'], '%' + q + '%'))
    else:
        rows = query_all(
            "SELECT * FROM tasks WHERE user_id=%s ORDER BY status='complete', due_datetime NULLS LAST",
            (u['id'],))
    items = ''
    for t in rows:
        st = task_status(t)
        strike = ' style="text-decoration:line-through;opacity:.6"' if t['status'] == 'complete' else ''
        items += """
        <div class="item swipe">
          <div class="spread">
            <div><strong%s>%s</strong> <span class="badge" style="background:var(--primary)">%s</span><br>
            <span class="muted">%s</span></div>
            %s
          </div>
          <div class="actions" style="display:none">
            <form method="post" action="/tasks/%d/complete"><button class="btn btn-sm btn-green">Done</button></form>
            <button class="btn btn-sm btn-orange" onclick="var f=document.getElementById('rs_%d');f.style.display=(f.style.display==='flex'?'none':'flex')">Reschedule</button>
            <form method="post" action="/tasks/%d/delete" onsubmit="return confirm('Delete this task?')">
              <button class="btn btn-sm btn-red">Delete</button></form>
            <form method="post" action="/tasks/%d/reschedule" id="rs_%d" style="display:none;gap:6px;align-items:center">
              <input type="datetime-local" name="due_datetime" style="width:auto;margin:0">
              <button class="btn btn-sm" type="submit">Save</button>
            </form>
          </div>
        </div>""" % (strike, e(t['title']), e(t['priority']), fmt_dt(t['due_datetime']),
                     STATUS_BADGE[st], t['id'], t['id'], t['id'], t['id'], t['id'])
    if not items:
        items = '<p class="muted">No tasks yet. Tap + to add one.</p>'

    content = render_flashes() + """
    <div class="topbar">
      <h1>My Tasks</h1>
      <form method="get" class="search row"><input name="q" placeholder="Search tasks..." value="%s">
      <button class="btn btn-sm">Search</button></form>
    </div>
    <div class="card">
      <form method="post" action="/tasks/add" class="row">
        <input name="title" placeholder="Task title..." style="flex:2" required>
        <input type="datetime-local" name="due_datetime" style="flex:1">
        <select name="priority" style="flex:1">
          <option value="low">Low</option><option value="medium" selected>Medium</option>
          <option value="high">High</option></select>
        <button class="btn">Add</button>
      </form>
    </div>
    <p class="muted" style="margin-bottom:8px">Swipe left on a task (mobile) or tap to reveal actions.</p>
    %s
    """ % (e(q), items)
    return render_page('Tasks', content, active='tasks', user=u)


@app.route('/tasks/add', methods=['POST'])
@login_required
def task_add():
    u = current_user()
    title = request.form.get('title', '').strip()
    due = request.form.get('due_datetime') or None
    priority = request.form.get('priority', 'medium')
    desc = request.form.get('description', '')
    if title:
        execute("INSERT INTO tasks (user_id,title,description,due_datetime,priority) VALUES (%s,%s,%s,%s,%s)",
                (u['id'], title, desc, due, priority))
        flash_msg('Task added.')
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/<int:tid>/complete', methods=['POST'])
@login_required
def task_complete(tid):
    u = current_user()
    execute("UPDATE tasks SET status = CASE WHEN status='complete' THEN 'pending' ELSE 'complete' END "
            "WHERE id=%s AND user_id=%s", (tid, u['id']))
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/<int:tid>/delete', methods=['POST'])
@login_required
def task_delete(tid):
    u = current_user()
    execute("DELETE FROM tasks WHERE id=%s AND user_id=%s", (tid, u['id']))
    flash_msg('Task deleted.')
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/<int:tid>/reschedule', methods=['POST'])
@login_required
def task_reschedule(tid):
    u = current_user()
    due = request.form.get('due_datetime')
    if due:
        execute("UPDATE tasks SET due_datetime=%s WHERE id=%s AND user_id=%s", (due, tid, u['id']))
        flash_msg('Task rescheduled.')
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/<int:tid>/edit', methods=['POST'])
@login_required
def task_edit(tid):
    u = current_user()
    title = request.form.get('title', '').strip()
    due = request.form.get('due_datetime') or None
    priority = request.form.get('priority', 'medium')
    if title:
        execute("UPDATE tasks SET title=%s, due_datetime=%s, priority=%s WHERE id=%s AND user_id=%s",
                (title, due, priority, tid, u['id']))
    return redirect(url_for('tasks'))


# ===========================================================================
# SCHEDULE
# ===========================================================================
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


@app.route('/schedule')
@login_required
def schedule():
    u = current_user()
    rows = query_all("SELECT * FROM schedules WHERE user_id=%s ORDER BY start_time", (u['id']))
    by_day = {d: [] for d in DAYS}
    for r in rows:
        by_day.setdefault(r['day'], []).append(r)
    grid = ''
    for d in DAYS:
        items = ''.join(
            '<div class="item"><strong>%s</strong><br><span class="muted">%s - %s · Room: %s</span>'
            '<div class="actions">'
            '<form method="post" action="/schedule/%d/delete"><button class="btn btn-sm btn-red">Delete</button></form>'
            '</div></div>'
            % (e(s['subject']), str(s['start_time'])[:5], str(s['end_time'])[:5],
               e(s['room'] or '-'), s['id'])
            for s in by_day.get(d, [])) or '<p class="muted">—</p>'
        grid += '<div class="card"><h3>%s</h3>%s</div>' % (d, items)

    day_opts = ''.join('<option>%s</option>' % d for d in DAYS)
    content = render_flashes() + """
    <div class="topbar"><h1>Class Schedule</h1></div>
    <div class="card">
      <form method="post" action="/schedule/add">
        <div class="grid grid-4">
          <div><label>Subject</label><input name="subject" required></div>
          <div><label>Day</label><select name="day">%s</select></div>
          <div><label>Start</label><input type="time" name="start_time"></div>
          <div><label>End</label><input type="time" name="end_time"></div>
        </div>
        <label>Room</label><input name="room" placeholder="e.g. Room 204">
        <button class="btn" type="submit">Add Class</button>
      </form>
    </div>
    <div class="grid grid-2">%s</div>
    """ % (day_opts, grid)
    return render_page('Schedule', content, active='schedule', user=u)


@app.route('/schedule/add', methods=['POST'])
@login_required
def schedule_add():
    u = current_user()
    subject = request.form.get('subject', '').strip()
    day = request.form.get('day', DAYS[0])
    st = request.form.get('start_time') or None
    et = request.form.get('end_time') or None
    room = request.form.get('room', '')
    if subject:
        execute("INSERT INTO schedules (user_id,subject,day,start_time,end_time,room) VALUES (%s,%s,%s,%s,%s,%s)",
                (u['id'], subject, day, st, et, room))
        flash_msg('Class added.')
    return redirect(url_for('schedule'))


@app.route('/schedule/<int:sid>/delete', methods=['POST'])
@login_required
def schedule_delete(sid):
    u = current_user()
    execute("DELETE FROM schedules WHERE id=%s AND user_id=%s", (sid, u['id']))
    return redirect(url_for('schedule'))


# ===========================================================================
# NOTES
# ===========================================================================
NOTE_FOLDERS = ['General', 'Reviewer', 'Lecture', 'Personal']


@app.route('/notes')
@login_required
def notes():
    u = current_user()
    folder = request.args.get('folder', 'General')
    if folder not in NOTE_FOLDERS:
        folder = 'General'
    rows = query_all("SELECT * FROM notes WHERE user_id=%s AND folder=%s ORDER BY created_at DESC",
                     (u['id'], folder))
    items = ''.join(
        '<div class="item"><strong>%s</strong><p class="muted" style="white-space:pre-wrap">%s</p>'
        '<div class="actions"><form method="post" action="/notes/%d/delete">'
        '<button class="btn btn-sm btn-red">Delete</button></form></div></div>'
        % (e(n['title'] or '(Untitled)'), e(n['content'] or ''), n['id'])
        for n in rows) or '<p class="muted">No notes in this folder.</p>'

    tabs = ''.join(
        '<a class="tab%s" href="/notes?folder=%s">%s</a>' %
        (' active' if folder == f else '', f, f) for f in NOTE_FOLDERS)
    folder_opts = ''.join('<option>%s</option>' % f for f in NOTE_FOLDERS)

    content = render_flashes() + """
    <div class="topbar"><h1>Notes</h1></div>
    <div class="tabs">%s</div>
    <div class="card">
      <form method="post" action="/notes/add">
        <label>Title</label><input name="title" placeholder="Note title...">
        <label>Content</label><textarea name="content" rows="4" placeholder="Write here..."></textarea>
        <label>Folder</label><select name="folder">%s</select>
        <button class="btn" type="submit">Save Note</button>
      </form>
    </div>
    %s
    """ % (tabs, folder_opts, items)
    return render_page('Notes', content, active='notes', user=u)


@app.route('/notes/add', methods=['POST'])
@login_required
def notes_add():
    u = current_user()
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '')
    folder = request.form.get('folder', 'General')
    if folder not in NOTE_FOLDERS:
        folder = 'General'
    execute("INSERT INTO notes (user_id,title,content,folder) VALUES (%s,%s,%s,%s)",
            (u['id'], title or 'Untitled', content, folder))
    flash_msg('Note saved.')
    return redirect('/notes?folder=' + folder)


@app.route('/notes/<int:nid>/delete', methods=['POST'])
@login_required
def notes_delete(nid):
    u = current_user()
    execute("DELETE FROM notes WHERE id=%s AND user_id=%s", (nid, u['id']))
    return redirect(request.referrer or url_for('notes'))


# ===========================================================================
# PROJECTS
# ===========================================================================
@app.route('/projects')
@login_required
def projects():
    u = current_user()
    rows = query_all("SELECT * FROM projects WHERE user_id=%s ORDER BY deadline NULLS LAST", (u['id']))
    items = ''
    for p in rows:
        items += """
        <div class="item">
          <div class="spread"><strong>%s</strong>
          <span class="muted">Deadline: %s</span></div>
          <p class="muted">%s</p>
          <p><strong>Members:</strong> %s</p>
          <p>Progress: %d%%</p>
          <div class="progress"><div style="width:%d%%"></div></div>
          <div class="actions">
            <form method="post" action="/projects/%d/progress" class="row">
              <input type="number" name="progress" min="0" max="100" value="%d" style="width:80px;margin:0">
              <button class="btn btn-sm">Update</button></form>
            <form method="post" action="/projects/%d/delete">
              <button class="btn btn-sm btn-red">Delete</button></form>
          </div>
        </div>""" % (e(p['name']), fmt_date(p['deadline']), e(p['description'] or ''),
                     e(p['members'] or '-'), p['progress'], p['progress'],
                     p['id'], p['progress'], p['id'])
    if not items:
        items = '<p class="muted">No projects yet.</p>'

    content = render_flashes() + """
    <div class="topbar"><h1>Group Projects</h1></div>
    <div class="card">
      <form method="post" action="/projects/add">
        <label>Project Name</label><input name="name" required>
        <label>Description</label><input name="description">
        <label>Members (comma separated)</label><input name="members" placeholder="Juan, Maria, Pedro">
        <label>Deadline</label><input type="date" name="deadline">
        <button class="btn" type="submit">Add Project</button>
      </form>
    </div>
    %s
    """ % items
    return render_page('Projects', content, active='projects', user=u)


@app.route('/projects/add', methods=['POST'])
@login_required
def projects_add():
    u = current_user()
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '')
    members = request.form.get('members', '')
    deadline = request.form.get('deadline') or None
    if name:
        execute("INSERT INTO projects (user_id,name,description,members,deadline) VALUES (%s,%s,%s,%s,%s)",
                (u['id'], name, desc, members, deadline))
        flash_msg('Project added.')
    return redirect(url_for('projects'))


@app.route('/projects/<int:pid>/progress', methods=['POST'])
@login_required
def projects_progress(pid):
    u = current_user()
    prog = max(0, min(100, int(request.form.get('progress', 0) or 0)))
    execute("UPDATE projects SET progress=%s WHERE id=%s AND user_id=%s", (prog, pid, u['id']))
    return redirect(url_for('projects'))


@app.route('/projects/<int:pid>/delete', methods=['POST'])
@login_required
def projects_delete(pid):
    u = current_user()
    execute("DELETE FROM projects WHERE id=%s AND user_id=%s", (pid, u['id']))
    return redirect(url_for('projects'))


# ===========================================================================
# GRADES + GPA
# ===========================================================================
@app.route('/grades')
@login_required
def grades():
    u = current_user()
    rows = query_all("SELECT * FROM grades WHERE user_id=%s ORDER BY id", (u['id']))
    total_units = 0.0
    weighted = 0.0
    trs = ''
    for g in rows:
        score = float(g['score'] or 0)
        units = float(g['units'] or 0)
        total_units += units
        weighted += score * units
        trs += ('<tr><td>%s</td><td>%.2f</td><td>%.1f</td><td>%s</td>'
                '<td><form method="post" action="/grades/%d/delete">'
                '<button class="btn btn-sm btn-red">Delete</button></form></td></tr>'
                % (e(g['subject']), score, units, e(g['semester'] or '-'), g['id']))
    gpa = (weighted / total_units) if total_units else 0.0

    content = render_flashes() + """
    <div class="topbar"><h1>Grades & GPA</h1></div>
    <div class="card">
      <form method="post" action="/grades/add">
        <div class="grid grid-4">
          <div><label>Subject</label><input name="subject" required></div>
          <div><label>Grade (1.00-5.00)</label><input type="number" step="0.01" name="score" required></div>
          <div><label>Units</label><input type="number" step="0.5" name="units" value="3"></div>
          <div><label>Semester</label><input name="semester" placeholder="1st Yr-1st Sem"></div>
        </div>
        <button class="btn" type="submit">Add Grade</button>
      </form>
    </div>
    <div class="card">
      <table><thead><tr><th>Subject</th><th>Grade</th><th>Units</th><th>Semester</th><th></th></tr></thead>
      <tbody>%s</tbody></table>
      <hr style="margin:14px 0;border-color:var(--border)">
      <h2>General Weighted Average (GWA/GPA): <span style="color:var(--primary)">%.2f</span></h2>
      <p class="muted">Based on %s total units.</p>
    </div>
    """ % (trs or '<tr><td colspan="5" class="muted">No grades recorded yet.</td></tr>',
           gpa, '%.1f' % total_units)
    return render_page('Grades', content, active='grades', user=u)


@app.route('/grades/add', methods=['POST'])
@login_required
def grades_add():
    u = current_user()
    subject = request.form.get('subject', '').strip()
    try:
        score = float(request.form.get('score', 0) or 0)
        units = float(request.form.get('units', 3) or 3)
    except ValueError:
        score, units = 0.0, 3.0
    semester = request.form.get('semester', '')
    if subject:
        execute("INSERT INTO grades (user_id,subject,score,units,semester) VALUES (%s,%s,%s,%s,%s)",
                (u['id'], subject, score, units, semester))
        flash_msg('Grade added.')
    return redirect(url_for('grades'))


@app.route('/grades/<int:gid>/delete', methods=['POST'])
@login_required
def grades_delete(gid):
    u = current_user()
    execute("DELETE FROM grades WHERE id=%s AND user_id=%s", (gid, u['id']))
    return redirect(url_for('grades'))


# ===========================================================================
# STUDY PLANNER
# ===========================================================================
@app.route('/planner')
@login_required
def planner():
    u = current_user()
    rows = query_all("SELECT * FROM study_goals WHERE user_id=%s ORDER BY target_date NULLS LAST", (u['id']))
    items = ''
    for g in rows:
        items += """
        <div class="item"><strong>%s</strong> <span class="muted">Target: %s</span>
        <p>Progress: %d%%</p>
        <div class="progress"><div style="width:%d%%"></div></div>
        <div class="actions">
          <form method="post" action="/planner/%d/progress" class="row">
            <input type="number" name="progress" min="0" max="100" value="%d" style="width:80px;margin:0">
            <button class="btn btn-sm">Update</button></form>
          <form method="post" action="/planner/%d/delete">
            <button class="btn btn-sm btn-red">Delete</button></form>
        </div></div>""" % (e(g['goal']), fmt_date(g['target_date']), g['progress'],
                          g['progress'], g['id'], g['progress'], g['id'])
    if not items:
        items = '<p class="muted">No study goals yet. Set your first goal!</p>'

    content = render_flashes() + """
    <div class="topbar"><h1>Study Planner</h1></div>
    <div class="card">
      <form method="post" action="/planner/add">
        <label>Goal</label><input name="goal" placeholder="e.g. Finish Chapter 5" required>
        <label>Target Date</label><input type="date" name="target_date">
        <button class="btn" type="submit">Set Goal</button>
      </form>
    </div>
    %s
    """ % items
    return render_page('Study Planner', content, active='planner', user=u)


@app.route('/planner/add', methods=['POST'])
@login_required
def planner_add():
    u = current_user()
    goal = request.form.get('goal', '').strip()
    target = request.form.get('target_date') or None
    if goal:
        execute("INSERT INTO study_goals (user_id,goal,target_date) VALUES (%s,%s,%s)",
                (u['id'], goal, target))
        flash_msg('Goal set.')
    return redirect(url_for('planner'))


@app.route('/planner/<int:gid>/progress', methods=['POST'])
@login_required
def planner_progress(gid):
    u = current_user()
    prog = max(0, min(100, int(request.form.get('progress', 0) or 0)))
    execute("UPDATE study_goals SET progress=%s WHERE id=%s AND user_id=%s", (prog, gid, u['id']))
    return redirect(url_for('planner'))


@app.route('/planner/<int:gid>/delete', methods=['POST'])
@login_required
def planner_delete(gid):
    u = current_user()
    execute("DELETE FROM study_goals WHERE id=%s AND user_id=%s", (gid, u['id']))
    return redirect(url_for('planner'))


# ===========================================================================
# PREMIUM — PAYMENT + ADMIN APPROVAL
# ===========================================================================
def gcash_qr_data_uri():
    """Generate a QR code data URI for the GCash number; return None if qrcode missing."""
    try:
        import qrcode
        img = qrcode.make('GCash:%s?Name=%s' % (GCASH_NUMBER, GCASH_NAME))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


@app.route('/premium', methods=['GET'])
@login_required
def premium():
    u = current_user()
    prem = premium_active(u['id'])
    qr_uri = gcash_qr_data_uri()
    qr_html = ('<img class="qr" src="%s" alt="GCash QR">' % qr_uri) if qr_uri else (
        '<div class="qr">GCash QR Code<br>(install qrcode lib:<br>pip install qrcode[pil])</div>')

    pending = query_one("SELECT * FROM premium_payments WHERE user_id=%s AND status='pending' "
                        "ORDER BY id DESC LIMIT 1", (u['id']))

    if prem:
        status_html = """
        <div class="card"><h2><span class="badge b-premium">PREMIUM ACTIVE</span></h2>
        <p>Activation Date: <strong>%s</strong></p>
        <p>Expiry Date: <strong>%s</strong></p>
        <p>Days Remaining: <strong style="font-size:22px;color:var(--primary)">%d</strong></p>
        <p class="muted">All premium features are unlocked.</p></div>""" % (
            fmt_date(prem['activation_date']), fmt_date(prem['expiry_date']), prem['days_left'])
    elif pending:
        status_html = """
        <div class="card"><h2>Payment Status: <span class="badge b-today">PENDING APPROVAL</span></h2>
        <p>Reference #: <strong>%s</strong></p>
        <p class="muted">Submitted %s. Please wait for admin approval.</p></div>""" % (
            e(pending['reference_number'] or '-'), fmt_date(pending['submitted_at']))
    else:
        status_html = """
        <div class="card">
          <h2>Unlock Premium — ₱%.2f / %d Days</h2>
          <p class="muted" style="margin-bottom:10px">Pay via GCash, then submit your reference number + receipt screenshot.</p>
          <div style="text-align:center">
            %s
            <p><strong>GCash #: %s</strong><br>Name: %s<br>Amount: ₱%.2f</p>
          </div>
          <form method="post" action="/premium/submit" enctype="multipart/form-data" style="margin-top:14px">
            <label>GCash Reference Number</label><input name="reference_number" required>
            <label>Receipt Screenshot (image)</label><input type="file" name="receipt" accept="image/*" required>
            <button class="btn" type="submit">Submit Payment</button>
          </form>
        </div>""" % (PREMIUM_PRICE, PREMIUM_DAYS, qr_html, e(GCASH_NUMBER), e(GCASH_NAME), PREMIUM_PRICE)

    features = ('<div class="card"><h3>Premium Features</h3><ul style="padding-left:20px">'
                '<li>Budget Tracker</li><li>Deadline Reminders</li>'
                '<li>Missed Task Recovery</li><li>Export Reports (CSV / PDF)</li>'
                '<li>Time Estimator</li><li>AI Study Assistant</li>'
                '<li>Exam Countdown</li><li>Focus Mode</li>'
                '<li>Friends, 1-on-1 Chat & Group Chat — UNLIMITED</li></ul></div>')

    content = render_flashes() + '<h1>TaskHive Premium</h1>' + status_html + features
    return render_page('Premium', content, active='premium', user=u)


@app.route('/premium/submit', methods=['POST'])
@login_required
def premium_submit():
    u = current_user()
    ref = request.form.get('reference_number', '').strip()
    f = request.files.get('receipt')
    if not ref or not f:
        flash_msg('Reference number and receipt screenshot are required.')
        return redirect(url_for('premium'))
    raw = f.read()
    if len(raw) > 6 * 1024 * 1024:
        flash_msg('Receipt image too large (max 6MB).')
        return redirect(url_for('premium'))
    mime = f.mimetype or 'image/png'
    b64 = 'data:%s;base64,%s' % (mime, base64.b64encode(raw).decode())
    execute("INSERT INTO premium_payments (user_id,reference_number,receipt_base64,status) VALUES (%s,%s,%s,'pending')",
            (u['id'], ref, b64))
    flash_msg('Payment submitted! Status: Pending Approval.')
    return redirect(url_for('premium'))


@app.route('/admin')
@admin_required
def admin_panel():
    rows = query_all(
        "SELECT p.*, u.full_name, u.email FROM premium_payments p JOIN users u ON u.id=p.user_id "
        "ORDER BY p.id DESC")
    trs = ''
    for p in rows:
        receipt = ('<a href="%s" target="_blank">View receipt</a>' % p['receipt_base64']
                   if p['receipt_base64'] else '—')
        actions = ''
        if p['status'] == 'pending':
            actions = ('<form method="post" action="/admin/%d/approve" style="display:inline">'
                       '<button class="btn btn-sm btn-green">Approve</button></form> '
                       '<form method="post" action="/admin/%d/decline" style="display:inline">'
                       '<button class="btn btn-sm btn-red">Decline</button></form>' % (p['id'], p['id']))
        else:
            actions = '<span class="badge %s">%s</span>' % (
                'b-complete' if p['status'] == 'approved' else 'b-overdue', p['status'].upper())
        trs += ('<tr><td>%s<br><span class="muted">%s</span></td><td>%s</td><td>%s</td>'
                '<td>%s</td><td>%s</td><td>%s</td></tr>' % (
                    e(p['full_name']), e(p['email']), e(p['reference_number'] or '-'),
                    receipt, fmt_date(p['submitted_at']),
                    fmt_date(p['activation_date']) + ' → ' + fmt_date(p['expiry_date'])
                    if p['activation_date'] else '—', actions))
    content = render_flashes() + """
    <h1>Admin — Premium Approvals</h1>
    <div class="card"><table>
      <thead><tr><th>User</th><th>Ref #</th><th>Receipt</th><th>Submitted</th><th>Active Period</th><th>Action</th></tr></thead>
      <tbody>%s</tbody></table></div>""" % (trs or '<tr><td colspan="6" class="muted">No payments.</td></tr>')
    return render_page('Admin', content, active='admin')


@app.route('/admin/<int:pid>/approve', methods=['POST'])
@admin_required
def admin_approve(pid):
    today = datetime.date.today()
    expiry = today + datetime.timedelta(days=PREMIUM_DAYS)
    execute("UPDATE premium_payments SET status='approved', activation_date=%s, expiry_date=%s WHERE id=%s",
            (today, expiry, pid))
    flash_msg('Payment approved — premium activated for 30 days.')
    return redirect(url_for('admin_panel'))


@app.route('/admin/<int:pid>/decline', methods=['POST'])
@admin_required
def admin_decline(pid):
    execute("UPDATE premium_payments SET status='declined' WHERE id=%s", (pid,))
    flash_msg('Payment declined.')
    return redirect(url_for('admin_panel'))


def premium_gate(feature_name, feature_url):
    """Return upsell HTML if user is NOT premium, else None."""
    u = current_user()
    if is_premium(u['id']):
        return None
    return ('<div class="lock"><h2>%s — Premium Feature</h2>'
            '<p class="muted" style="margin:10px 0">Unlock Premium (₱%.2f / 30 days) to access this feature.</p>'
            '<a class="btn" href="/premium">Unlock Premium</a></div>' % (e(feature_name), PREMIUM_PRICE))


# ===========================================================================
# PREMIUM FEATURES
# ===========================================================================
@app.route('/budget')
@login_required
def budget():
    u = current_user()
    gate = premium_gate('Budget Tracker', '/budget')
    if gate:
        return render_page('Budget', render_flashes() + '<h1>Budget Tracker</h1>' + gate, user=u)
    rows = query_all("SELECT * FROM budget WHERE user_id=%s ORDER BY date DESC", (u['id']))
    income = sum(float(r['amount'] or 0) for r in rows if r['type'] == 'income')
    expense = sum(float(r['amount'] or 0) for r in rows if r['type'] == 'expense')
    trs = ''.join(
        '<tr><td>%s</td><td>%s</td><td>₱%.2f</td><td>%s</td><td>%s</td>'
        '<td><form method="post" action="/budget/%d/delete"><button class="btn btn-sm btn-red">X</button></form></td></tr>'
        % (fmt_date(r['date']), e(r['description'] or ''), float(r['amount'] or 0),
           r['type'].title(), '', r['id']) for r in rows)
    content = render_flashes() + """
    <h1>Budget Tracker <span class="badge b-premium">PREMIUM</span></h1>
    <div class="grid grid-3" style="margin-bottom:14px">
      <div class="stat"><div class="num" style="color:var(--green)">₱%.2f</div><div class="lbl">Income</div></div>
      <div class="stat"><div class="num" style="color:var(--red)">₱%.2f</div><div class="lbl">Expense</div></div>
      <div class="stat"><div class="num">₱%.2f</div><div class="lbl">Balance</div></div>
    </div>
    <div class="card"><form method="post" action="/budget/add">
      <div class="grid grid-4">
        <div><label>Description</label><input name="description" required></div>
        <div><label>Amount</label><input type="number" step="0.01" name="amount" required></div>
        <div><label>Type</label><select name="type"><option value="expense">Expense</option>
          <option value="income">Income</option></select></div>
        <div><label>Date</label><input type="date" name="date"></div>
      </div><button class="btn">Add</button></form></div>
    <div class="card"><table><thead><tr><th>Date</th><th>Description</th><th>Amount</th><th>Type</th><th></th><th></th></tr></thead>
    <tbody>%s</tbody></table></div>
    """ % (income, expense, income - expense, trs or '<tr><td colspan="6" class="muted">No entries.</td></tr>')
    return render_page('Budget', content, user=u)


@app.route('/budget/add', methods=['POST'])
@login_required
def budget_add():
    u = current_user()
    if not is_premium(u['id']):
        return redirect(url_for('premium'))
    desc = request.form.get('description', '')
    try:
        amt = float(request.form.get('amount', 0) or 0)
    except ValueError:
        amt = 0
    typ = request.form.get('type', 'expense')
    date = request.form.get('date') or None
    execute("INSERT INTO budget (user_id,description,amount,type,date) VALUES (%s,%s,%s,%s,%s)",
            (u['id'], desc, amt, typ, date))
    return redirect(url_for('budget'))


@app.route('/budget/<int:bid>/delete', methods=['POST'])
@login_required
def budget_delete(bid):
    u = current_user()
    execute("DELETE FROM budget WHERE id=%s AND user_id=%s", (bid, u['id']))
    return redirect(url_for('budget'))


@app.route('/reminders')
@login_required
def reminders():
    u = current_user()
    gate = premium_gate('Deadline Reminders', '/reminders')
    if gate:
        return render_page('Reminders', render_flashes() + '<h1>Deadline Reminders</h1>' + gate, user=u)
    soon = query_all(
        "SELECT * FROM tasks WHERE user_id=%s AND status='pending' AND due_datetime IS NOT NULL "
        "AND due_datetime <= NOW() + INTERVAL '48 hours' ORDER BY due_datetime", (u['id']))
    items = ''.join(
        '<div class="item"><strong>%s</strong> — %s %s</div>'
        % (e(t['title']), fmt_dt(t['due_datetime']), STATUS_BADGE[task_status(t)])
        for t in soon) or '<p class="muted">No deadlines in the next 48 hours.</p>'
    content = render_flashes() + ('<h1>Deadline Reminders <span class="badge b-premium">PREMIUM</span></h1>'
                                  '<p class="muted">Tasks due within 48 hours:</p>' + items)
    return render_page('Reminders', content, user=u)


@app.route('/recovery')
@login_required
def recovery():
    u = current_user()
    gate = premium_gate('Missed Task Recovery', '/recovery')
    if gate:
        return render_page('Recovery', render_flashes() + '<h1>Missed Task Recovery</h1>' + gate, user=u)
    overdue = query_all(
        "SELECT * FROM tasks WHERE user_id=%s AND status='pending' AND due_datetime < NOW() ORDER BY due_datetime",
        (u['id']))
    items = ''.join(
        '<div class="item"><strong>%s</strong> <span class="muted">was due %s</span>'
        '<div class="actions">'
        '<form method="post" action="/tasks/%d/complete"><button class="btn btn-sm btn-green">Mark Done</button></form>'
        '<form method="post" action="/tasks/%d/reschedule"><input type="hidden" name="due_datetime" value="%s">'
        '<button class="btn btn-sm btn-orange">Move to Today</button></form>'
        '</div></div>'
        % (e(t['title']), fmt_dt(t['due_datetime']), t['id'], t['id'],
           (datetime.datetime.now() + datetime.timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M'))
        for t in overdue) or '<p class="muted">No missed tasks. Great job!</p>'
    content = render_flashes() + ('<h1>Missed Task Recovery <span class="badge b-premium">PREMIUM</span></h1>' + items)
    return render_page('Recovery', content, user=u)


@app.route('/export/csv')
@login_required
def export_csv():
    u = current_user()
    if not is_premium(u['id']):
        return redirect(url_for('premium'))
    rows = query_all("SELECT * FROM tasks WHERE user_id=%s ORDER BY due_datetime", (u['id']))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['ID', 'Title', 'Description', 'Due', 'Priority', 'Status', 'Created'])
    for r in rows:
        w.writerow([r['id'], r['title'], r['description'] or '', r['due_datetime'] or '',
                    r['priority'], r['status'], r['created_at']])
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=taskhive_tasks.csv'})


@app.route('/export/report')
@login_required
def export_report():
    u = current_user()
    gate = premium_gate('Export Reports', '/export/report')
    if gate:
        return render_page('Export Report', render_flashes() + '<h1>Export Reports</h1>' + gate, user=u)
    tasks = query_all("SELECT * FROM tasks WHERE user_id=%s ORDER BY due_datetime", (u['id']))
    grades = query_all("SELECT * FROM grades WHERE user_id=%s", (u['id']))
    trs = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
                  (e(t['title']), fmt_dt(t['due_datetime']), e(t['priority']), t['status']) for t in tasks)
    gtrs = ''.join('<tr><td>%s</td><td>%.2f</td><td>%.1f</td></tr>' %
                   (e(g['subject']), float(g['score'] or 0), float(g['units'] or 0)) for g in grades)
    content = render_flashes() + """
    <h1>Report <span class="badge b-premium">PREMIUM</span></h1>
    <div class="row" style="margin-bottom:12px">
      <button class="btn" onclick="window.print()">Print / Save as PDF</button>
      <a class="btn btn-outline" href="/export/csv">Download CSV</a>
    </div>
    <div class="card"><h2>Tasks</h2><table><thead><tr><th>Title</th><th>Due</th><th>Priority</th><th>Status</th></tr></thead>
    <tbody>%s</tbody></table></div>
    <div class="card"><h2>Grades</h2><table><thead><tr><th>Subject</th><th>Grade</th><th>Units</th></tr></thead>
    <tbody>%s</tbody></table></div>
    """ % (trs or '<tr><td colspan="4" class="muted">None</td></tr>',
           gtrs or '<tr><td colspan="3" class="muted">None</td></tr>')
    return render_page('Report', content, user=u)


@app.route('/estimator', methods=['GET', 'POST'])
@login_required
def estimator():
    u = current_user()
    gate = premium_gate('Time Estimator', '/estimator')
    if gate:
        return render_page('Time Estimator', render_flashes() + '<h1>Time Estimator</h1>' + gate, user=u)
    result = ''
    if request.method == 'POST':
        try:
            pages = float(request.form.get('pages', 0) or 0)
            difficulty = request.form.get('difficulty', 'medium')
            mult = {'easy': 0.5, 'medium': 1.0, 'hard': 1.8}[difficulty]
            minutes = max(15, int(pages * 8 * mult))
            result = ('<div class="card"><h3>Estimated study time: ~%d minutes (%d hour(s) %d min)</h3>'
                      '<p class="muted">Includes short breaks. Adjust based on your pace.</p></div>'
                      % (minutes, minutes // 60, minutes % 60))
        except Exception:
            result = '<div class="flash">Invalid input.</div>'
    content = render_flashes() + """
    <h1>Time Estimator <span class="badge b-premium">PREMIUM</span></h1>
    <div class="card"><form method="post">
      <label>Pages / topics to cover</label><input type="number" name="pages" min="1" required>
      <label>Difficulty</label><select name="difficulty">
        <option value="easy">Easy</option><option value="medium" selected>Medium</option>
        <option value="hard">Hard</option></select>
      <button class="btn">Estimate</button>
    </form></div>%s""" % result
    return render_page('Time Estimator', content, user=u)


AI_RULES = [
    (['hello', 'hi', 'hey', 'kamusta'], "Hi! I'm your AI Study Assistant. Ask me for study tips, how to focus, or how to manage your time!"),
    (['focus', 'focused', 'distract'], "Try the Pomodoro technique: 25 minutes of focused study, then a 5-minute break. Use Focus Mode in TaskHive!"),
    (['time', 'manage', 'schedule', 'plan'], "Break big tasks into small chunks, set deadlines in TaskHive, and review your schedule every morning."),
    (['exam', 'test', 'review', 'crams'], "Don't cram! Review a little each day. Use the Reviewer folder in Notes and check the Exam Countdown."),
    (['note', 'notes'], "Use Cornell notes: divide your page into cues, notes, and summary. Store them in TaskHive Notes folders."),
    (['motivat', 'tired', 'lazy', 'burnout'], "Rest is part of studying. Take a 10-minute walk, drink water, then come back. Small progress still counts!"),
    (['gpa', 'grade', 'grades'], "Record your grades and units in TaskHive Grades — your GPA is auto-calculated for you."),
    (['sleep', 'sleeping'], "Aim for 7-8 hours of sleep. Memory consolidation happens during sleep, so all-nighters hurt retention."),
]


@app.route('/ai')
@login_required
def ai_page():
    u = current_user()
    gate = premium_gate('AI Study Assistant', '/ai')
    if gate:
        return render_page('AI Study Assistant', render_flashes() + '<h1>AI Study Assistant</h1>' + gate, user=u)
    content = render_flashes() + """
    <h1>AI Study Assistant <span class="badge b-premium">PREMIUM</span></h1>
    <div class="card">
      <div id="ailog" class="chatbox">
        <div class="msg them"><div class="bubble">Hello! I can help with study tips, focus, time management, exams, and more. Ask me anything!</div></div>
      </div>
      <form id="aiform" class="row" onsubmit="sendAI(event)">
        <input id="aiinput" placeholder="Ask a question..." style="flex:1;margin:0" autocomplete="off">
        <button class="btn">Send</button>
      </form>
    </div>
    <script>
    function sendAI(e){e.preventDefault();
      var inp=document.getElementById('aiinput');var q=inp.value.trim();if(!q)return;
      var log=document.getElementById('ailog');
      log.innerHTML+='<div class="msg me"><div class="bubble">'+escapeHtml(q)+'</div></div>';
      inp.value='';log.scrollTop=log.scrollHeight;
      fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'q='+encodeURIComponent(q)})
      .then(r=>r.json()).then(d=>{
        log.innerHTML+='<div class="msg them"><div class="bubble">'+escapeHtml(d.reply)+'</div></div>';
        log.scrollTop=log.scrollHeight;});
    }
    function escapeHtml(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
    </script>"""
    return render_page('AI Assistant', content, user=u)


@app.route('/api/ai', methods=['POST'])
@login_required
def api_ai():
    u = current_user()
    if not is_premium(u['id']):
        return jsonify({'reply': 'Premium required.'}), 403
    q = (request.form.get('q') or '').lower()
    for keys, reply in AI_RULES:
        if any(k in q for k in keys):
            return jsonify({'reply': reply})
    return jsonify({'reply': "Great question! Try breaking it into smaller tasks and track them in TaskHive. "
                             "I can help with: focus tips, time management, exam prep, note-taking, motivation, grades, and sleep."})


@app.route('/exams', methods=['GET', 'POST'])
@login_required
def exams():
    u = current_user()
    gate = premium_gate('Exam Countdown', '/exams')
    if gate:
        return render_page('Exam Countdown', render_flashes() + '<h1>Exam Countdown</h1>' + gate, user=u)
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        date = request.form.get('exam_date') or None
        if subject:
            execute("INSERT INTO exams (user_id,subject,exam_date) VALUES (%s,%s,%s)", (u['id'], subject, date))
        return redirect(url_for('exams'))
    rows = query_all("SELECT * FROM exams WHERE user_id=%s ORDER BY exam_date NULLS LAST", (u['id']))
    today = datetime.date.today()
    items = ''
    for ex in rows:
        d = ex['exam_date']
        if isinstance(d, str):
            d = datetime.date.fromisoformat(d[:10])
        days = (d - today).days if d else 0
        color = 'var(--red)' if days <= 3 else ('var(--orange)' if days <= 7 else 'var(--primary)')
        items += ('<div class="item spread"><div><strong>%s</strong><br><span class="muted">%s</span></div>'
                  '<div style="text-align:right"><div style="font-size:24px;font-weight:800;color:%s">%s</div>'
                  '<span class="muted">%s</span></div>'
                  '<form method="post" action="/exams/%d/delete"><button class="btn btn-sm btn-red">X</button></form>'
                  '</div>' % (e(ex['subject']), fmt_date(d), color,
                              ('DONE' if days < 0 else '%d day(s)' % days),
                              ('already passed' if days < 0 else 'to go'), ex['id']))
    content = render_flashes() + """
    <h1>Exam Countdown <span class="badge b-premium">PREMIUM</span></h1>
    <div class="card"><form method="post" class="row">
      <input name="subject" placeholder="Subject" style="flex:2;margin:0" required>
      <input type="date" name="exam_date" style="flex:1;margin:0">
      <button class="btn">Add Exam</button></form></div>
    %s""" % (items or '<p class="muted">No exams scheduled.</p>')
    return render_page('Exam Countdown', content, user=u)


@app.route('/exams/<int:eid>/delete', methods=['POST'])
@login_required
def exams_delete(eid):
    u = current_user()
    execute("DELETE FROM exams WHERE id=%s AND user_id=%s", (eid, u['id']))
    return redirect(url_for('exams'))


@app.route('/focus')
@login_required
def focus():
    u = current_user()
    gate = premium_gate('Focus Mode', '/focus')
    if gate:
        return render_page('Focus Mode', render_flashes() + '<h1>Focus Mode</h1>' + gate, user=u)
    content = render_flashes() + """
    <h1>Focus Mode <span class="badge b-premium">PREMIUM</span></h1>
    <div class="card" style="text-align:center;padding:40px">
      <div id="timer" style="font-size:64px;font-weight:800;color:var(--primary);margin:20px 0">25:00</div>
      <div class="row" style="justify-content:center">
        <button class="btn" onclick="startTimer(25)">Pomodoro 25m</button>
        <button class="btn btn-outline" onclick="startTimer(5)">Short Break 5m</button>
        <button class="btn btn-outline" onclick="startTimer(15)">Long Break 15m</button>
        <button class="btn btn-gray" onclick="stopTimer()">Stop</button>
      </div>
      <p class="muted" style="margin-top:16px">Stay focused. Put your phone away. You got this!</p>
    </div>
    <script>
    var tInt=null;var remaining=0;
    function startTimer(m){stopTimer();remaining=m*60;tick();
      tInt=setInterval(tick,1000);}
    function stopTimer(){if(tInt){clearInterval(tInt);tInt=null;}
      document.getElementById('timer').textContent='25:00';}
    function tick(){
      if(remaining<=0){clearInterval(tInt);tInt=null;
        document.getElementById('timer').textContent='DONE!';
        try{new Audio('data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ==').play();}catch(e){}
        alert('Time is up! Take a break.');return;}
      var m=Math.floor(remaining/60),s=remaining%60;
      document.getElementById('timer').textContent=
        String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
      remaining--;}
    </script>"""
    return render_page('Focus Mode', content, user=u)


# ===========================================================================
# FRIENDS & CHAT
# ===========================================================================
@app.route('/friends')
@login_required
def friends():
    u = current_user()
    prem = is_premium(u['id'])
    fids = friend_ids(u['id'])
    friends_list = []
    if fids:
        friends_list = query_all(
            "SELECT id, full_name, student_id, course_year, last_seen FROM users WHERE id IN %s",
            (tuple(fids),)) if fids else []

    requests_in = query_all(
        "SELECT f.id, u.id AS uid, u.full_name, u.student_id FROM friendships f "
        "JOIN users u ON u.id=f.requester_id WHERE f.addressee_id=%s AND f.status='pending'",
        (u['id'],))

    q = request.args.get('q', '').strip()
    search_results = []
    if q:
        search_results = query_all(
            "SELECT id, full_name, student_id, course_year FROM users "
            "WHERE id != %s AND (full_name ILIKE %s OR student_id ILIKE %s) LIMIT 20",
            (u['id'], '%' + q + '%', '%' + q + '%'))

    # build friend cards
    fhtml = ''
    for f in friends_list:
        on = is_online(f)
        fhtml += ('<div class="item spread"><div>'
                  '<span class="online-dot %s"></span><strong>%s</strong><br>'
                  '<span class="muted">%s · %s</span></div>'
                  '<div class="actions">'
                  '<a class="btn btn-sm" href="/chat/%d">Chat</a>'
                  '<form method="post" action="/friends/%d/remove">'
                  '<button class="btn btn-sm btn-gray">Unfriend</button></form>'
                  '</div></div>'
                  % ('on' if on else '', e(f['full_name']), e(f['student_id']),
                     e(f['course_year'] or ''), f['id'], f['id']))
    if not fhtml:
        fhtml = '<p class="muted">No friends yet. Search for users below!</p>'

    rhtml = ''.join(
        '<div class="item spread"><strong>%s</strong> <span class="muted">%s</span>'
        '<div class="actions">'
        '<form method="post" action="/friends/%d/accept"><button class="btn btn-sm btn-green">Accept</button></form>'
        '<form method="post" action="/friends/%d/decline"><button class="btn btn-sm btn-red">Decline</button></form>'
        '</div></div>' % (e(r['full_name']), e(r['student_id']), r['id'], r['id'])
        for r in requests_in) or '<p class="muted">No pending requests.</p>'

    shtml = ''
    for s in search_results:
        sid = s['id']
        if sid in fids:
            btn = '<span class="badge b-complete">Friends</span>'
        else:
            existing = query_one(
                "SELECT id, status FROM friendships WHERE "
                "(requester_id=%s AND addressee_id=%s) OR (requester_id=%s AND addressee_id=%s)",
                (u['id'], sid, sid, u['id']))
            if existing and existing['status'] == 'pending':
                btn = '<span class="badge b-today">Request sent</span>'
            else:
                btn = ('<form method="post" action="/friends/add">'
                       '<input type="hidden" name="user_id" value="%d">'
                       '<button class="btn btn-sm">Add Friend</button></form>' % sid)
        shtml += ('<div class="item spread"><div><strong>%s</strong><br>'
                  '<span class="muted">%s · %s</span></div>%s</div>'
                  % (e(s['full_name']), e(s['student_id']), e(s['course_year'] or ''), btn))
    if q and not shtml:
        shtml = '<p class="muted">No users found.</p>'

    # groups
    my_groups = query_all(
        "SELECT g.id, g.name FROM groups g JOIN group_members gm ON gm.group_id=g.id "
        "WHERE gm.user_id=%s ORDER BY g.id DESC", (u['id']))
    ghtml = ''.join(
        '<div class="item spread"><strong>%s</strong>'
        '<a class="btn btn-sm" href="/group/%d">Open Group</a></div>'
        % (e(g['name']), g['id']) for g in my_groups)
    if not ghtml:
        ghtml = '<p class="muted">No groups yet.</p>'
    if not prem:
        ghtml += ('<p class="muted" style="margin-top:8px">Group chat is for Premium users. '
                  '<a href="/premium">Upgrade</a> to create groups.</p>')

    limit_note = ''
    if not prem and len(friends_list) >= FREE_FRIEND_LIMIT:
        limit_note = ('<div class="flash">Free plan: friend limit (%d) reached. '
                      '<a href="/premium">Go Premium</a> for unlimited friends & chat!</div>'
                      % FREE_FRIEND_LIMIT)

    content = render_flashes() + limit_note + """
    <div class="topbar"><h1>Friends & Chat</h1></div>
    <div class="tabs">
      <span class="tab active" onclick="showTab('flist',this)">Friends (%d)</span>
      <span class="tab" onclick="showTab('freq',this)">Requests (%d)</span>
      <span class="tab" onclick="showTab('fsearch',this)">Search</span>
      <span class="tab" onclick="showTab('fgrp',this)">Groups</span>
    </div>
    <div id="flist" class="tabc">%s</div>
    <div id="freq" class="tabc" style="display:none">%s</div>
    <div id="fsearch" class="tabc" style="display:none">
      <form method="get" class="row" style="margin-bottom:10px">
        <input name="q" placeholder="Search by name or Student ID..." value="%s" style="flex:1;margin:0">
        <button class="btn">Search</button>
      </form>%s</div>
    <div id="fgrp" class="tabc" style="display:none">
      %s
      <div class="card" style="margin-top:12px"><h3>Create Group</h3>
      <form method="post" action="/groups/create">
        <label>Group Name</label><input name="name" placeholder="e.g. Study Buddies" required>
        <label>Add Friends (hold Ctrl to select multiple)</label>
        <select name="members" multiple size="5">%s</select>
        <button class="btn" type="submit" %s>Create Group</button>
        %s
      </form></div>
    </div>
    <script>
    function showTab(id,el){document.querySelectorAll('.tabc').forEach(t=>t.style.display='none');
      document.getElementById(id).style.display='block';
      document.querySelectorAll('.tabs .tab').forEach(t=>t.classList.remove('active'));
      el.classList.add('active');}
    </script>
    """ % (len(friends_list), len(requests_in), fhtml, rhtml, e(q), shtml, ghtml,
           ''.join('<option value="%d">%s</option>' % (f['id'], e(f['full_name'])) for f in friends_list),
           '' if prem else 'disabled',
           '' if prem else '<p class="muted" style="color:var(--red)">Premium required to create groups.</p>')
    return render_page('Friends', content, active='friends', user=u)


@app.route('/friends/add', methods=['POST'])
@login_required
def friends_add():
    u = current_user()
    if not is_premium(u['id']) and len(friend_ids(u['id'])) >= FREE_FRIEND_LIMIT:
        flash_msg('Free friend limit reached. Upgrade to Premium for unlimited friends!')
        return redirect(url_for('friends'))
    target = int(request.form.get('user_id', 0))
    if target and target != u['id']:
        exists = query_one(
            "SELECT id FROM friendships WHERE (requester_id=%s AND addressee_id=%s) "
            "OR (requester_id=%s AND addressee_id=%s)", (u['id'], target, target, u['id']))
        if not exists:
            execute("INSERT INTO friendships (requester_id,addressee_id,status) VALUES (%s,%s,'pending')",
                    (u['id'], target))
            flash_msg('Friend request sent.')
    return redirect(request.referrer or url_for('friends'))


@app.route('/friends/<int:fid>/accept', methods=['POST'])
@login_required
def friends_accept(fid):
    u = current_user()
    execute("UPDATE friendships SET status='accepted' WHERE id=%s AND addressee_id=%s", (fid, u['id']))
    flash_msg('Friend request accepted.')
    return redirect(url_for('friends'))


@app.route('/friends/<int:fid>/decline', methods=['POST'])
@login_required
def friends_decline(fid):
    u = current_user()
    execute("DELETE FROM friendships WHERE id=%s AND addressee_id=%s", (fid, u['id']))
    flash_msg('Friend request declined.')
    return redirect(url_for('friends'))


@app.route('/friends/<int:fid>/remove', methods=['POST'])
@login_required
def friends_remove(fid):
    u = current_user()
    execute("DELETE FROM friendships WHERE (requester_id=%s AND addressee_id=%s) "
            "OR (requester_id=%s AND addressee_id=%s)", (u['id'], fid, fid, u['id']))
    flash_msg('Friend removed.')
    return redirect(url_for('friends'))


@app.route('/groups/create', methods=['POST'])
@login_required
def groups_create():
    u = current_user()
    if not is_premium(u['id']):
        flash_msg('Group chat is a Premium feature.')
        return redirect(url_for('premium'))
    name = request.form.get('name', '').strip()
    members = request.form.getlist('members')
    if name:
        row = execute("INSERT INTO groups (name,creator_id) VALUES (%s,%s) RETURNING id",
                      (name, u['id']), returning=True)
        gid = row['id']
        execute("INSERT INTO group_members (group_id,user_id) VALUES (%s,%s)", (gid, u['id']))
        fids = friend_ids(u['id'])
        for m in members:
            mid = int(m)
            if mid in fids:
                execute("INSERT INTO group_members (group_id,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (gid, mid))
        flash_msg('Group created.')
        return redirect('/group/%d' % gid)
    return redirect(url_for('friends'))


def chat_js(friend_id=None, group_id=None):
    param = 'friend_id=%d' % friend_id if friend_id else 'group_id=%d' % group_id
    send_param = 'friend_id' if friend_id else 'group_id'
    send_val = friend_id if friend_id else group_id
    return """
    <script>
    var lastId=0;
    function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
    function loadMsgs(){
      fetch('/api/messages?%s&since='+lastId).then(r=>r.json()).then(d=>{
        var box=document.getElementById('chatbox');
        d.messages.forEach(m=>{
          lastId=Math.max(lastId,m.id);
          var mine=m.sender_id==%d;
          var who=mine?'':('<div class="who">'+esc(m.sender_name)+'</div>');
          var cls=mine?'msg me':'msg them';
          box.innerHTML+='<div class="'+cls+'">'+who+
            '<div class="bubble">'+esc(m.content)+'</div>'+
            '<div class="time">'+m.time+'</div></div>';
        });
        if(d.messages.length) box.scrollTop=box.scrollHeight;
      });
      fetch('/api/typing?%s').then(r=>r.json()).then(d=>{
        document.getElementById('typing').textContent=
          d.typing.length? d.typing.join(', ')+' typing...':'';
      });
    }
    function sendMsg(e){e.preventDefault();
      var inp=document.getElementById('msginput');var c=inp.value.trim();if(!c)return;
      fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:'%s=%d&content='+encodeURIComponent(c)});
      inp.value='';loadMsgs();
    }
    function pingTyping(){
      fetch('/api/typing',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:'%s=%d'});
    }
    setInterval(loadMsgs,2000);loadMsgs();
    </script>
    """ % (param, session['user_id'], param, send_param, send_val, send_param, send_val)


@app.route('/chat/<int:friend_id>')
@login_required
def chat_dm(friend_id):
    u = current_user()
    if friend_id not in friend_ids(u['id']):
        flash_msg('You are not friends with that user.')
        return redirect(url_for('friends'))
    other = query_one("SELECT id, full_name, student_id, last_seen FROM users WHERE id=%s", (friend_id,))
    on = is_online(other)
    content = render_flashes() + """
    <div class="topbar">
      <h1><span class="online-dot %s"></span>%s</h1>
      <a class="btn btn-outline btn-sm" href="/friends">&larr; Back</a>
    </div>
    <div class="card">
      <div id="chatbox" class="chatbox"></div>
      <div id="typing" class="typing"></div>
      <form class="row" onsubmit="sendMsg(event)">
        <input id="msginput" placeholder="Type a message..." style="flex:1;margin:0"
          autocomplete="off" onkeydown="pingTyping()">
        <button class="btn">Send</button>
      </form>
    </div>
    %s
    """ % ('on' if on else '', e(other['full_name']), chat_js(friend_id=friend_id))
    return render_page('Chat with ' + other['full_name'], content, active='friends', user=u)


@app.route('/group/<int:group_id>')
@login_required
def chat_group(group_id):
    u = current_user()
    member = query_one("SELECT 1 FROM group_members WHERE group_id=%s AND user_id=%s", (group_id, u['id']))
    if not member:
        abort(403)
    grp = query_one("SELECT * FROM groups WHERE id=%s", (group_id,))
    members = query_all(
        "SELECT u.full_name FROM group_members gm JOIN users u ON u.id=gm.user_id WHERE gm.group_id=%s",
        (group_id,))
    member_names = ', '.join(m['full_name'] for m in members)
    content = render_flashes() + """
    <div class="topbar">
      <div><h1>%s</h1><p class="muted">Members: %s</p></div>
      <a class="btn btn-outline btn-sm" href="/friends">&larr; Back</a>
    </div>
    <div class="card">
      <div id="chatbox" class="chatbox"></div>
      <div id="typing" class="typing"></div>
      <form class="row" onsubmit="sendMsg(event)">
        <input id="msginput" placeholder="Message the group..." style="flex:1;margin:0"
          autocomplete="off" onkeydown="pingTyping()">
        <button class="btn">Send</button>
      </form>
    </div>
    %s
    """ % (e(grp['name']), e(member_names), chat_js(group_id=group_id))
    return render_page('Group: ' + grp['name'], content, active='friends', user=u)


# ---------- chat API ----------
@app.route('/api/messages')
@login_required
def api_messages():
    u = current_user()
    since = int(request.args.get('since', 0) or 0)
    friend_id = request.args.get('friend_id')
    group_id = request.args.get('group_id')
    if friend_id:
        fid = int(friend_id)
        if fid not in friend_ids(u['id']):
            return jsonify({'messages': []})
        rows = query_all(
            "SELECT m.*, u.full_name AS sender_name FROM messages m "
            "JOIN users u ON u.id=m.sender_id WHERE m.id>%s AND m.group_id IS NULL AND "
            "((m.sender_id=%s AND m.receiver_id=%s) OR (m.sender_id=%s AND m.receiver_id=%s)) "
            "ORDER BY m.id LIMIT 200",
            (since, u['id'], fid, fid, u['id']))
    elif group_id:
        gid = int(group_id)
        member = query_one("SELECT 1 FROM group_members WHERE group_id=%s AND user_id=%s", (gid, u['id']))
        if not member:
            return jsonify({'messages': []})
        rows = query_all(
            "SELECT m.*, u.full_name AS sender_name FROM messages m "
            "JOIN users u ON u.id=m.sender_id WHERE m.id>%s AND m.group_id=%s ORDER BY m.id LIMIT 200",
            (since, gid))
    else:
        return jsonify({'messages': []})
    out = []
    for r in rows:
        t = r['created_at']
        if isinstance(t, str):
            t = datetime.datetime.fromisoformat(t.replace('Z', ''))
        out.append({'id': r['id'], 'sender_id': r['sender_id'],
                    'sender_name': r['sender_name'], 'content': r['content'],
                    'time': t.strftime('%I:%M %p')})
    return jsonify({'messages': out})


@app.route('/api/send', methods=['POST'])
@login_required
def api_send():
    u = current_user()
    content = (request.form.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False})
    friend_id = request.form.get('friend_id')
    group_id = request.form.get('group_id')
    if friend_id:
        fid = int(friend_id)
        if fid not in friend_ids(u['id']):
            return jsonify({'ok': False, 'error': 'not friends'})
        execute("INSERT INTO messages (sender_id,receiver_id,content) VALUES (%s,%s,%s)",
                (u['id'], fid, content))
    elif group_id:
        gid = int(group_id)
        member = query_one("SELECT 1 FROM group_members WHERE group_id=%s AND user_id=%s", (gid, u['id']))
        if not member:
            return jsonify({'ok': False, 'error': 'not member'})
        execute("INSERT INTO messages (sender_id,group_id,content) VALUES (%s,%s,%s)",
                (u['id'], gid, content))
    else:
        return jsonify({'ok': False})
    return jsonify({'ok': True})


@app.route('/api/typing', methods=['GET', 'POST'])
@login_required
def api_typing():
    u = current_user()
    now = datetime.datetime.now()
    if request.method == 'POST':
        friend_id = request.form.get('friend_id')
        group_id = request.form.get('group_id')
        if group_id:
            key = ('grp', int(group_id), u['id'])
        elif friend_id:
            a, b = sorted([u['id'], int(friend_id)])
            key = ('dm', a, b, u['id'])
        else:
            return jsonify({'typing': []})
        typing_state[key] = now
        return jsonify({'ok': True})
    # GET: who is typing
    friend_id = request.args.get('friend_id')
    group_id = request.args.get('group_id')
    names = []
    cutoff = now - datetime.timedelta(seconds=3)
    if group_id:
        gid = int(group_id)
        for key, ts in list(typing_state.items()):
            if key[0] == 'grp' and key[1] == gid and key[2] != u['id'] and ts > cutoff:
                who = query_one("SELECT full_name FROM users WHERE id=%s", (key[2],))
                if who:
                    names.append(who['full_name'])
    elif friend_id:
        fid = int(friend_id)
        a, b = sorted([u['id'], fid])
        for key, ts in list(typing_state.items()):
            if (key[0] == 'dm' and key[1] == a and key[2] == b
                    and key[3] != u['id'] and ts > cutoff):
                who = query_one("SELECT full_name FROM users WHERE id=%s", (key[3],))
                if who:
                    names.append(who['full_name'])
    # clean old entries
    for key in [k for k, ts in typing_state.items() if ts < cutoff]:
        typing_state.pop(key, None)
    return jsonify({'typing': sorted(set(names))})


# ===========================================================================
# ENTRY POINT
# ===========================================================================
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
