from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import sqlite3
import os
import datetime
import uuid
import hashlib

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
DATABASE = "taskhive.db"
PREMIUM_PRICE = 50.00
PREMIUM_DAYS = 30

# ✅ Iisa na lang ang number — tugma na sa QR mo (+63 970 456 ••••, JE***N V.)
#    ⚠️ PALITAN LANG ANG "XXXX" sa GCASH_NUMBER ng huling 4 digits ng number mo.
GCASH_NUMBER = "0970-456-XXXX"   # ⚠️ PALITAN ANG "XXXX" ng HULING 4 DIGITS (nasa QR: +63 970 456 ••••)
GCASH_NAME = "JE***N V."          # Pangalan na naka-register sa QR (JE***N V.)
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")  # Para sa manual management (/api/premium/approve)

# ==================== DATABASE HELPERS ====================
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            theme TEXT DEFAULT 'light'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            day TEXT NOT NULL,
            time_start TEXT NOT NULL,
            time_end TEXT NOT NULL,
            room TEXT,
            color TEXT DEFAULT '#6366F1'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            folder_name TEXT DEFAULT 'General',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            members TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'Ongoing',
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            score REAL NOT NULL,
            units REAL DEFAULT 3,
            semester TEXT,
            recorded_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            recorded_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS planner (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            goal TEXT NOT NULL,
            target_date TEXT,
            progress INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            amount REAL NOT NULL,
            reference_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',
            sent_at TEXT,
            activated_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_ph_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))

def format_date(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def check_premium_status(user_id):
    """Check and update if premium is expired"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    is_premium = row['is_premium']
    expiry_str = row['premium_expiry']
    if is_premium and expiry_str:
        expiry = datetime.datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        now = get_ph_time().replace(tzinfo=None)
        if now > expiry:
            cur.execute("UPDATE users SET is_premium = 0, premium_start = NULL, premium_expiry = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            return False
    conn.close()
    return bool(is_premium)

def get_user_data(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return dict(user) if user else None

# ==================== ROUTES ====================
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template_string(FRONTEND_HTML, page='register')
    data = request.get_json()
    required = ['full_name', 'email', 'student_id', 'course_year', 'password']
    for field in required:
        if not data.get(field, '').strip():
            return jsonify({'success': False, 'error': 'All fields are required'})
    if data['password'] != data.get('confirm_password', ''):
        return jsonify({'success': False, 'error': 'Passwords do not match'})
    if len(data['password']) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'})
    conn = get_db()
    cur = conn.cursor()
    try:
        user_id = str(uuid.uuid4())[:8]
        now = format_date(get_ph_time())
        cur.execute("""
            INSERT INTO users (user_id, full_name, email, student_id, course_year, password_hash, join_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, data['full_name'].strip(), data['email'].strip().lower(),
              data['student_id'].strip(), data['course_year'].strip(),
              hash_password(data['password']), now))
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': 'Email already registered'})
    finally:
        conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template_string(FRONTEND_HTML, page='login')
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    remember = data.get('remember', False)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    conn.close()
    if not user or user['password_hash'] != hash_password(password):
        return jsonify({'success': False, 'error': 'Invalid email or password'})
    session['user_id'] = user['user_id']
    session.permanent = bool(remember)
    return jsonify({'success': True, 'user_id': user['user_id'], 'name': user['full_name']})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template_string(FRONTEND_HTML, page='dashboard')

@app.route('/api/user', methods=['GET'])
def get_user():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    user = get_user_data(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    is_premium = check_premium_status(user_id)
    expiry = user.get('premium_expiry') if is_premium else None
    return jsonify({
        'full_name': user['full_name'],
        'email': user['email'],
        'student_id': user['student_id'],
        'course_year': user['course_year'],
        'join_date': user['join_date'],
        'is_premium': is_premium,
        'premium_expiry': expiry,
        'theme': user.get('theme', 'light')
    })

@app.route('/api/user/theme', methods=['POST'])
def set_theme():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    theme = data.get('theme', 'light')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET theme = ? WHERE user_id = ?", (theme, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ==================== PREMIUM & PAYMENT SYSTEM (AUTO-UNLOCK) ====================
@app.route('/api/premium/request', methods=['POST'])
def request_premium():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT reference_id FROM payments
        WHERE user_id = ? AND status IN ('pending', 'waiting')
        ORDER BY id DESC LIMIT 1
    """, (session['user_id'],))
    existing = cur.fetchone()
    if existing:
        conn.close()
        return jsonify({
            'success': True,
            'reference_id': existing['reference_id'],
            'amount': PREMIUM_PRICE,
            'gcash_number': GCASH_NUMBER,
            'gcash_name': GCASH_NAME
        })
    reference_id = f"TH-{session['user_id']}-{str(uuid.uuid4())[:6].upper()}"
    now = format_date(get_ph_time())
    cur.execute("""
        INSERT INTO payments (user_id, amount, reference_id, status, sent_at)
        VALUES (?, ?, ?, 'pending', ?)
    """, (session['user_id'], PREMIUM_PRICE, reference_id, now))
    conn.commit()
    conn.close()
    return jsonify({
        'success': True,
        'reference_id': reference_id,
        'amount': PREMIUM_PRICE,
        'gcash_number': GCASH_NUMBER,
        'gcash_name': GCASH_NAME
    })

@app.route('/api/premium/confirm-payment', methods=['POST'])
def confirm_payment():
    """AUTO-UNLOCK: pag-click ng user ng 'I Have Sent Payment', activate agad ang
    Premium — WALANG admin approval na hihintayin. Ang /api/premium/approve ay
    natira para sa manual management/revocation ng admin."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    reference_id = str(data.get('reference_id', '')).strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE reference_id = ? AND user_id = ?",
                (reference_id, session['user_id']))
    payment = cur.fetchone()
    if not payment:
        conn.close()
        return jsonify({'success': False, 'error': 'Reference ID not found'})
    if payment['status'] == 'activated':
        cur.execute("SELECT premium_expiry FROM users WHERE user_id = ?", (session['user_id'],))
        row = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'activated': True,
                        'message': 'Premium already activated',
                        'expiry_date': row['premium_expiry'] if row else None})
    # === AUTO-ACTIVATE AGAD (walang hihintayin na admin) ===
    now = get_ph_time().replace(tzinfo=None)
    cur.execute("SELECT premium_expiry FROM users WHERE user_id = ?", (payment['user_id'],))
    row = cur.fetchone()
    start = now
    if row and row['premium_expiry']:
        try:
            old = datetime.datetime.strptime(row['premium_expiry'], "%Y-%m-%d %H:%M:%S")
            if old > now:
                start = old  # renewal: dagdag sa natitirang araw
        except Exception:
            pass
    expiry = start + datetime.timedelta(days=PREMIUM_DAYS)
    cur.execute(
        "UPDATE users SET is_premium = 1, premium_start = COALESCE(premium_start, ?), premium_expiry = ? WHERE user_id = ?",
        (format_date(now), format_date(expiry), payment['user_id']))
    cur.execute("UPDATE payments SET status = 'activated', activated_at = ? WHERE reference_id = ?",
                (format_date(now), reference_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'activated': True, 'message': 'Premium Activated!',
                    'expiry_date': format_date(expiry), 'days_left': PREMIUM_DAYS})

# Admin manual management (natira — para sa pag-activate o pag-revoke kung kailangan):
#   POST /api/premium/approve   header: X-Admin-Key: <ADMIN_KEY>   body: {"reference_id": "TH-..."}
@app.route('/api/premium/approve', methods=['POST'])
def approve_payment():
    if not ADMIN_KEY or request.headers.get('X-Admin-Key', '') != ADMIN_KEY:
        return jsonify({'error': 'Forbidden'}), 403
    reference_id = (request.get_json(silent=True) or {}).get('reference_id', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE reference_id = ?", (reference_id,))
    payment = cur.fetchone()
    if not payment:
        conn.close()
        return jsonify({'success': False, 'error': 'Reference ID not found'}), 404
    if payment['status'] == 'activated':
        conn.close()
        return jsonify({'success': True, 'message': 'Already activated'})
    now = get_ph_time().replace(tzinfo=None)
    cur.execute("SELECT premium_expiry FROM users WHERE user_id = ?", (payment['user_id'],))
    row = cur.fetchone()
    start = now
    if row and row['premium_expiry']:
        old = datetime.datetime.strptime(row['premium_expiry'], "%Y-%m-%d %H:%M:%S")
        if old > now:
            start = old
    expiry = start + datetime.timedelta(days=PREMIUM_DAYS)
    cur.execute("UPDATE users SET is_premium = 1, premium_start = COALESCE(premium_start, ?), premium_expiry = ? WHERE user_id = ?",
                (format_date(now), format_date(expiry), payment['user_id']))
    cur.execute("UPDATE payments SET status = 'activated', activated_at = ? WHERE reference_id = ?",
                (format_date(now), reference_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Premium activated'})

@app.route('/api/premium/status', methods=['GET'])
def premium_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    is_premium = check_premium_status(session['user_id'])
    user = get_user_data(session['user_id'])
    days_left = 0
    if is_premium and user.get('premium_expiry'):
        expiry = datetime.datetime.strptime(user['premium_expiry'], "%Y-%m-%d %H:%M:%S")
        now = get_ph_time().replace(tzinfo=None)
        days_left = (expiry - now).days
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (session['user_id'],))
    payment = cur.fetchone()
    conn.close()
    return jsonify({
        'is_premium': is_premium,
        'days_left': days_left,
        'expiry_date': user.get('premium_expiry') if is_premium else None,
        'latest_payment': dict(payment) if payment else None,
        'price': PREMIUM_PRICE
    })

# ==================== TASKS API ====================
@app.route('/api/tasks', methods=['GET', 'POST', 'PUT', 'DELETE'])
def tasks():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'GET':
        cur.execute("SELECT * FROM tasks WHERE user_id = ? ORDER BY due_date ASC, priority DESC", (user_id,))
        tasks = cur.fetchall()
        conn.close()
        return jsonify([dict(t) for t in tasks])
    elif request.method == 'POST':
        data = request.get_json()
        now = format_date(get_ph_time())
        cur.execute("""
            INSERT INTO tasks (user_id, title, subject, description, due_date, due_time, priority, reminder_set, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, data['title'], data.get('subject',''), data.get('description',''),
              data['due_date'], data.get('due_time','23:59'), data.get('priority','medium'),
              1 if data.get('reminder_set') else 0, now))
        conn.commit()
        task_id = cur.lastrowid
        conn.close()
        return jsonify({'success': True, 'id': task_id})
    elif request.method == 'PUT':
        data = request.get_json()
        cur.execute("UPDATE tasks SET completed = ? WHERE id = ? AND user_id = ?",
                    (data.get('completed', 0), data['id'], user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        task_id = request.args.get('id')
        cur.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ==================== SCHEDULE API ====================
@app.route('/api/schedule', methods=['GET', 'POST', 'DELETE'])
def schedule():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    if request.method == 'GET':
        cur.execute("SELECT * FROM schedule WHERE user_id = ? ORDER BY time_start", (user_id,))
        items = cur.fetchall()
        conn.close()
        return jsonify([dict(s) for s in items])
    elif request.method == 'POST':
        data = request.get_json()
        cur.execute("""
            INSERT INTO schedule (user_id, subject, day, time_start, time_end, room, color)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, data['subject'], data['day'], data['time_start'],
              data['time_end'], data.get('room',''), data.get('color','#6366F1')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        item_id = request.args.get('id')
        cur.execute("DELETE FROM schedule WHERE id = ? AND user_id = ?", (item_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ==================== NOTES API ====================
@app.route('/api/notes', methods=['GET', 'POST', 'PUT', 'DELETE'])
def notes():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    now = format_date(get_ph_time())
    if request.method == 'GET':
        cur.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
        items = cur.fetchall()
        conn.close()
        return jsonify([dict(n) for n in items])
    elif request.method == 'POST':
        data = request.get_json()
        cur.execute("""
            INSERT INTO notes (user_id, title, content, folder_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, data['title'], data.get('content',''), data.get('folder_name','General'), now, now))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        note_id = request.args.get('id')
        cur.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ==================== PROJECTS API ====================
@app.route('/api/projects', methods=['GET', 'POST', 'PUT', 'DELETE'])
def projects():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    now = format_date(get_ph_time())
    if request.method == 'GET':
        cur.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        items = cur.fetchall()
        conn.close()
        return jsonify([dict(p) for p in items])
    elif request.method == 'POST':
        data = request.get_json()
        cur.execute("""
            INSERT INTO projects (user_id, name, members, deadline, status, created_at)
            VALUES (?, ?, ?, ?, 'Ongoing', ?)
        """, (user_id, data['name'], data.get('members',''), data.get('deadline',''), now))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.get_json()
        cur.execute("UPDATE projects SET status = ? WHERE id = ? AND user_id = ?",
                    (data['status'], data['id'], user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        proj_id = request.args.get('id')
        cur.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (proj_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ==================== GRADES API ====================
@app.route('/api/grades', methods=['GET', 'POST', 'DELETE'])
def grades():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    now = format_date(get_ph_time())
    if request.method == 'GET':
        cur.execute("SELECT * FROM grades WHERE user_id = ? ORDER BY recorded_at DESC", (user_id,))
        items = cur.fetchall()
        conn.close()
        return jsonify([dict(g) for g in items])
    elif request.method == 'POST':
        data = request.get_json()
        cur.execute("""
            INSERT INTO grades (user_id, subject, score, units, semester, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, data['subject'], data['score'], data.get('units', 3),
              data.get('semester',''), now))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        grade_id = request.args.get('id')
        cur.execute("DELETE FROM grades WHERE id = ? AND user_id = ?", (grade_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ==================== BUDGET API (PREMIUM ONLY) ====================
@app.route('/api/budget', methods=['GET', 'POST', 'DELETE'])
def budget():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if not check_premium_status(session['user_id']):
        return jsonify({'error': 'Premium required', 'premium_required': True}), 403
    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    now = format_date(get_ph_time())
    if request.method == 'GET':
        cur.execute("SELECT * FROM budget WHERE user_id = ? ORDER BY recorded_at DESC", (user_id,))
        items = cur.fetchall()
        conn.close()
        return jsonify([dict(b) for b in items])
    elif request.method == 'POST':
        data = request.get_json()
        cur.execute("""
            INSERT INTO budget (user_id, type, category, amount, description, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, data['type'], data['category'], data['amount'],
              data.get('description',''), now))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        item_id = request.args.get('id')
        cur.execute("DELETE FROM budget WHERE id = ? AND user_id = ?", (item_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ==================== PLANNER API ====================
@app.route('/api/planner', methods=['GET', 'POST', 'PUT', 'DELETE'])
def planner():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    now = format_date(get_ph_time())
    if request.method == 'GET':
        cur.execute("SELECT * FROM planner WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        items = cur.fetchall()
        conn.close()
        return jsonify([dict(g) for g in items])
    elif request.method == 'POST':
        data = request.get_json()
        cur.execute("""
            INSERT INTO planner (user_id, goal, target_date, progress, created_at)
            VALUES (?, ?, ?, 0, ?)
        """, (user_id, data['goal'], data.get('target_date', ''), now))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.get_json()
        progress = max(0, min(100, int(data.get('progress', 0))))
        cur.execute("UPDATE planner SET progress = ? WHERE id = ? AND user_id = ?",
                    (progress, data['id'], user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        goal_id = request.args.get('id')
        cur.execute("DELETE FROM planner WHERE id = ? AND user_id = ?", (goal_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# ==================== FRONTEND HTML ====================
FRONTEND_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>TaskHive — Plan • Study • Achieve</title>
<style>
:root {
    --bg: #EFF6FF; --card: #FFFFFF; --text: #0F172A; --muted: #64748B;
    --primary: #6366F1; --secondary: #3B82F6; --accent: #8B5CF6;
    --success: #10B981; --warning: #F59E0B; --danger: #EF4444;
    --border: #E2E8F0; --shadow: 0 2px 8px rgba(99, 102, 241, 0.08);
    --gradient: linear-gradient(135deg, #6366F1 0%, #3B82F6 100%);
}
.dark {
    --bg: #0F172A; --card: #1E293B; --text: #FFFFFF; --muted: #94A3B8;
    --border: #334155; --shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}
* {margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Roboto, sans-serif;}
body {background: var(--bg); color: var(--text); min-height: 100vh; transition: background 0.3s ease;}
.app-container {max-width: 480px; margin: 0 auto; min-height: 100vh; background: var(--bg); position: relative;}
.auth-page {min-height: 100vh; display: flex; flex-direction: column; justify-content: center; padding: 24px; background: var(--gradient);}
.auth-card {background: var(--card); padding: 32px 24px; border-radius: 20px; box-shadow: var(--shadow);}
.auth-logo {text-align: center; margin-bottom: 24px;}
.auth-logo h1 {font-size: 28px; background: var(--gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
.auth-logo p {color: var(--muted); font-size: 14px; margin-top: 4px;}
.form-group {margin-bottom: 16px;}
.form-group label {display: block; font-size: 14px; font-weight: 500; margin-bottom: 6px; color: var(--text);}
.form-group input, .form-group select, .form-group textarea {width: 100%; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; font-size: 15px; background: transparent; color: var(--text);}
.form-group input:focus {outline: none; border-color: var(--primary);}
.btn {width: 100%; padding: 14px; border: none; border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer; transition: opacity 0.2s;}
.btn:hover {opacity: 0.92;}
.btn-primary {background: var(--gradient); color: white;}
.btn-outline {background: transparent; border: 1px solid var(--primary); color: var(--primary);}
.btn-success {background: var(--success); color: white;}
.btn-danger {background: var(--danger); color: white;}
.btn-sm {padding: 8px 14px; font-size: 14px; width: auto;}
.link {text-align: center; margin-top: 16px; font-size: 14px; color: var(--muted);}
.link a {color: var(--primary); text-decoration: none; font-weight: 500;}
.error-text {color: var(--danger); font-size: 13px; margin-top: 6px; display: none;}
.error-text.show {display: block;}
.success-text {color: var(--success); font-size: 13px; margin: 0 0 12px; display: none; font-weight: 500;}
.success-text.show {display: block;}
.header {background: var(--card); padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: var(--shadow); position: sticky; top: 0; z-index: 100;}
.header h2 {font-size: 18px; font-weight: 600;}
.menu-btn {background: none; border: none; font-size: 24px; color: var(--text); cursor: pointer;}
.sidebar-overlay {position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 200; display: none;}
.sidebar-overlay.show {display: block;}
.sidebar {position: fixed; top: 0; left: 0; bottom: 0; width: 280px; background: var(--card); z-index: 300; transform: translateX(-100%); transition: transform 0.3s ease; overflow-y: auto;}
.sidebar.show {transform: translateX(0);}
.sidebar-close {text-align: right; padding: 16px 20px 0;}
.sidebar-close button {background: none; border: none; font-size: 22px; color: var(--muted); cursor: pointer;}
.sidebar-profile {padding: 20px; border-bottom: 1px solid var(--border);}
.sidebar-profile h3 {font-size: 17px; margin-bottom: 4px;}
.sidebar-profile p {font-size: 13px; color: var(--muted); margin-bottom: 8px;}
.premium-badge {display: inline-block; background: linear-gradient(135deg, #F59E0B, #D97706); color: white; font-size: 11px; padding: 3px 10px; border-radius: 12px; font-weight: 600; margin-bottom: 6px;}
.sidebar-menu {padding: 12px 0;}
.sidebar-item {display: flex; align-items: center; gap: 12px; padding: 14px 20px; color: var(--text); text-decoration: none; font-size: 15px; cursor: pointer; transition: background 0.15s;}
.sidebar-item:hover {background: rgba(99, 102, 241, 0.08);}
.sidebar-item.locked {opacity: 0.5;}
.sidebar-item .lock {margin-left: auto; font-size: 14px; color: var(--muted);}
.content {padding: 20px; padding-bottom: 90px;}
.page {display: none; animation: fadeIn 0.3s ease;}
.page.active {display: block;}
@keyframes fadeIn {from {opacity: 0; transform: translateY(8px);} to {opacity: 1; transform: translateY(0);}}
.greeting {font-size: 22px; font-weight: 700; margin-bottom: 4px;}
.quote {font-size: 13px; color: var(--muted); margin-bottom: 24px; font-style: italic;}
.card {background: var(--card); border-radius: 16px; padding: 18px; margin-bottom: 16px; box-shadow: var(--shadow);}
.card h3 {font-size: 15px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center;}
.card h3 span {font-size: 12px; color: var(--primary); cursor: pointer;}
.task-item {padding: 12px 0; border-bottom: 1px solid var(--border); display: flex; align-items: flex-start; gap: 10px;}
.task-item:last-child {border-bottom: none;}
.task-priority {width: 10px; height: 10px; border-radius: 50%; margin-top: 4px; flex-shrink: 0;}
.priority-high {background: var(--danger);}
.priority-medium {background: var(--warning);}
.priority-low {background: var(--success);}
.task-text {flex: 1;}
.task-title {font-size: 15px; font-weight: 500;}
.task-title.completed {text-decoration: line-through; color: var(--muted);}
.task-meta {font-size: 12px; color: var(--muted); margin-top: 2px;}
.task-due {font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 6px;}
.due-today {background: rgba(245, 158, 11, 0.15); color: var(--warning);}
.due-overdue {background: rgba(239, 68, 68, 0.1); color: var(--danger);}
.due-later {background: rgba(16, 185, 129, 0.1); color: var(--success);}
.task-actions {display: flex; gap: 6px; flex-shrink: 0;}
.task-actions button {background: none; border: none; font-size: 16px; cursor: pointer; padding: 2px 6px;}
.stats-grid {display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; text-align: center;}
.stat-circle {width: 60px; height: 60px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; margin: 0 auto 6px; position: relative;}
.stat-circle span {font-size: 16px; font-weight: 700; z-index: 2;}
.stat-label {font-size: 11px; color: var(--muted);}
.quick-grid {display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;}
.quick-btn {display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 16px 8px; background: var(--card); border-radius: 12px; text-decoration: none; color: var(--text); font-size: 12px; box-shadow: var(--shadow); border: none; cursor: pointer; transition: transform 0.15s;}
.quick-btn:hover {transform: translateY(-2px);}
.quick-btn span {font-size: 22px;}
.quick-btn.locked {opacity: 0.5; position: relative;}
.quick-btn.locked::after {content: "🔒"; position: absolute; top: 4px; right: 4px; font-size: 12px;}
.bottom-nav {position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); max-width: 480px; width: 100%; background: var(--card); display: flex; justify-content: space-around; padding: 10px 0; box-shadow: 0 -2px 10px rgba(0,0,0,0.05); z-index: 150;}
.nav-item {display: flex; flex-direction: column; align-items: center; gap: 2px; color: var(--muted); text-decoration: none; font-size: 11px; cursor: pointer;}
.nav-item.active {color: var(--primary);}
.nav-item span {font-size: 20px;}
.modal-overlay {position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 500; display: none; align-items: center; justify-content: center; padding: 20px;}
.modal-overlay.show {display: flex;}
.modal {background: var(--card); border-radius: 20px; padding: 24px; width: 100%; max-width: 400px; max-height: 90vh; overflow-y: auto;}
.modal h2 {font-size: 20px; margin-bottom: 16px; text-align: center;}
.modal-actions {display: flex; gap: 10px; margin-top: 20px;}
.modal-actions button {flex: 1;}
.qr-code {width: 220px; margin: 16px auto; border-radius: 12px; overflow: hidden; border: 1px solid var(--border); background: #fff;}
.qr-code img {width: 100%; display: block;}
.premium-features {margin: 16px 0;}
.premium-features p {padding: 8px 0; font-size: 14px; border-bottom: 1px solid var(--border);}
.countdown-box {background: linear-gradient(135deg, #F59E0B, #D97706); color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 600; margin: 12px 0;}
.hidden {display: none !important;}
input[type="checkbox"] {width: auto; margin-right: 8px;}
.empty-state {text-align: center; padding: 40px 20px; color: var(--muted);}
.empty-state span {font-size: 48px; display: block; margin-bottom: 12px; opacity: 0.5;}
.qr-hint {text-align: center; font-size: 12px; color: var(--muted); margin-top: 10px; line-height: 1.5;}
.qr-hint strong {color: var(--success);}
'''
# Ginawang raw string (r''') para hindi sirain ng Python ang mga \' sa loob ng JavaScript
FRONTEND_HTML += r'''
</style>
</head>
<body>
<div class="app-container" id="app">
    <!-- AUTH PAGES -->
    <div id="authSection" style="display: block;">
        <div id="loginPage" class="auth-page" style="display: none;">
            <div class="auth-card">
                <div class="auth-logo">
                    <h1>🐝 TaskHive</h1>
                    <p>Plan • Study • Achieve</p>
                </div>
                <form id="loginForm">
                    <div class="form-group">
                        <label>Email Address</label>
                        <input type="email" id="loginEmail" placeholder="you@email.com" required>
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="password" id="loginPassword" placeholder="Enter password" required>
                    </div>
                    <label style="display: flex; align-items: center; margin-bottom: 16px; font-size: 14px;">
                        <input type="checkbox" id="rememberMe"> Remember me
                    </label>
                    <div class="success-text" id="loginSuccess"></div>
                    <div class="error-text" id="loginError"></div>
                    <button type="submit" class="btn btn-primary">Log In</button>
                </form>
                <div class="link">
                    Don't have an account? <a href="#" onclick="showAuthPage('register'); return false;">Sign Up</a>
                </div>
            </div>
        </div>
        <div id="registerPage" class="auth-page" style="display: none;">
            <div class="auth-card">
                <div class="auth-logo">
                    <h1>🐝 Join TaskHive</h1>
                    <p>Start organizing your study life today!</p>
                </div>
                <form id="registerForm">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" id="regName" placeholder="Juan Dela Cruz" required>
                    </div>
                    <div class="form-group">
                        <label>Email</label>
                        <input type="email" id="regEmail" placeholder="you@email.com" required>
                    </div>
                    <div class="form-group">
                        <label>Student ID</label>
                        <input type="text" id="regStudentId" placeholder="e.g. 2023-12345" required>
                    </div>
                    <div class="form-group">
                        <label>Course & Year</label>
                        <input type="text" id="regCourse" placeholder="BS Computer Science - 2nd Year" required>
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="password" id="regPassword" placeholder="At least 6 characters" required>
                    </div>
                    <div class="form-group">
                        <label>Confirm Password</label>
                        <input type="password" id="regConfirmPass" placeholder="Re-enter password" required>
                    </div>
                    <div class="error-text" id="regError"></div>
                    <button type="submit" class="btn btn-primary">Create Account</button>
                </form>
                <div class="link">
                    Already have an account? <a href="#" onclick="showAuthPage('login'); return false;">Log In</a>
                </div>
            </div>
        </div>
    </div>
    <!-- MAIN APP -->
    <div id="mainApp" style="display: none;">
        <div class="header">
            <button class="menu-btn" onclick="toggleSidebar()">☰</button>
            <h2 id="pageTitle">Dashboard</h2>
            <span></span>
        </div>
        <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
        <div class="sidebar" id="sidebar">
            <div class="sidebar-close">
                <button onclick="toggleSidebar()">×</button>
            </div>
            <div class="sidebar-profile">
                <h3 id="sidebarName">User Name</h3>
                <p id="sidebarCourse">Course & Year</p>
                <div id="sidebarPremiumBadge" class="premium-badge" style="display: none;">👑 Premium</div>
                <p id="sidebarExpiry" style="font-size: 11px; color: var(--muted);"></p>
            </div>
            <div class="sidebar-menu">
                <div class="sidebar-item" onclick="navigateTo('dashboard')">🏠 Dashboard</div>
                <div class="sidebar-item" onclick="navigateTo('tasks')">✅ My Tasks</div>
                <div class="sidebar-item" onclick="navigateTo('schedule')">📅 Schedule</div>
                <div class="sidebar-item" onclick="navigateTo('notes')">📝 Notes</div>
                <div class="sidebar-item" onclick="navigateTo('projects')">👥 Projects</div>
                <div class="sidebar-item" onclick="navigateTo('grades')">📊 Grades</div>
                <div class="sidebar-item" id="menuBudget" onclick="navigateTo('budget')">💰 Budget Tracker <span class="lock">🔒</span></div>
                <div class="sidebar-item" onclick="navigateTo('planner')">📈 Study Planner</div>
                <div class="sidebar-item" id="menuPremium" onclick="navigateTo('premium')">✨ Premium Features</div>
                <div class="sidebar-item" onclick="navigateTo('settings')">⚙️ Settings</div>
                <div class="sidebar-item" style="color: var(--danger);" onclick="logout()">🚪 Log Out</div>
            </div>
        </div>
        <div class="content">
            <!-- DASHBOARD -->
            <div id="pageDashboard" class="page active">
                <h2 class="greeting" id="greeting">Good Morning!</h2>
                <p class="quote" id="dailyQuote">"Your future is created by what you do today, not tomorrow."</p>
                <div class="card">
                    <h3>📅 Today's Schedule</h3>
                    <div id="todayScheduleList">
                        <div class="empty-state"><span>📭</span>No classes today. Enjoy your time!</div>
                    </div>
                </div>
                <div class="card">
                    <h3>⏰ Upcoming Deadlines</h3>
                    <div id="upcomingTasksList">
                        <div class="empty-state"><span>🎉</span>No upcoming deadlines. You're all caught up!</div>
                    </div>
                </div>
                <div class="card">
                    <h3>📊 Quick Stats</h3>
                    <div class="stats-grid">
                        <div>
                            <div class="stat-circle" style="background: conic-gradient(var(--primary) 0% 0%, var(--border) 0% 100%);">
                                <span id="statPercent">0%</span>
                            </div>
                            <div class="stat-label">Complete</div>
                        </div>
                        <div>
                            <div class="stat-circle" style="background: var(--card); border: 3px solid var(--success);">
                                <span id="statDone">0</span>
                            </div>
                            <div class="stat-label">Done</div>
                        </div>
                        <div>
                            <div class="stat-circle" style="background: var(--card); border: 3px solid var(--warning);">
                                <span id="statPending">0</span>
                            </div>
                            <div class="stat-label">Pending</div>
                        </div>
                        <div>
                            <div class="stat-circle" style="background: var(--card); border: 3px solid var(--danger);">
                                <span id="statOverdue">0</span>
                            </div>
                            <div class="stat-label">Overdue</div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <h3>⚡ Quick Actions</h3>
                    <div class="quick-grid">
                        <button class="quick-btn" onclick="showAddTaskModal()"><span>➕</span>Add Task</button>
                        <button class="quick-btn" onclick="navigateTo('schedule')"><span>📆</span>Schedule</button>
                        <button class="quick-btn" onclick="navigateTo('planner')"><span>🎯</span>Planner</button>
                        <button class="quick-btn locked" onclick="showPremiumModal()"><span>⏱️</span>Focus</button>
                        <button class="quick-btn locked" onclick="showPremiumModal()"><span>🤖</span>AI Help</button>
                        <button class="quick-btn locked" onclick="showPremiumModal()"><span>🔔</span>Remind</button>
                        <button class="quick-btn locked" onclick="showPremiumModal()"><span>♻️</span>Recover</button>
                        <button class="quick-btn locked" onclick="showPremiumModal()"><span>📄</span>Export</button>
                    </div>
                </div>
            </div>
            <!-- TASKS -->
            <div id="pageTasks" class="page">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h2 style="font-size: 20px;">✅ My Tasks</h2>
                    <button class="btn btn-primary btn-sm" onclick="showAddTaskModal()">+ Add Task</button>
                </div>
                <div id="allTasksList"></div>
            </div>
            <!-- SCHEDULE -->
            <div id="pageSchedule" class="page">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h2 style="font-size: 20px;">📅 Class Schedule</h2>
                    <button class="btn btn-primary btn-sm" onclick="showAddScheduleModal()">+ Add</button>
                </div>
                <div id="scheduleList"></div>
            </div>
            <!-- NOTES -->
            <div id="pageNotes" class="page">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h2 style="font-size: 20px;">📝 Notes</h2>
                    <button class="btn btn-primary btn-sm" onclick="showAddNoteModal()">+ Note</button>
                </div>
                <div id="notesList"></div>
            </div>
            <!-- PROJECTS -->
            <div id="pageProjects" class="page">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h2 style="font-size: 20px;">👥 Group Projects</h2>
                    <button class="btn btn-primary btn-sm" onclick="showAddProjectModal()">+ Project</button>
                </div>
                <div id="projectsList"></div>
            </div>
            <!-- GRADES -->
            <div id="pageGrades" class="page">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h2 style="font-size: 20px;">📊 Grades & GPA</h2>
                    <button class="btn btn-primary btn-sm" onclick="showAddGradeModal()">+ Grade</button>
                </div>
                <div class="card">
                    <h3>📈 GPA Summary</h3>
                    <div style="text-align: center; padding: 10px 0;">
                        <div style="font-size: 42px; font-weight: 700; color: var(--primary);" id="gpaDisplay">--</div>
                        <div style="font-size: 14px; color: var(--muted);">Current GPA</div>
                    </div>
                </div>
                <div id="gradesList"></div>
            </div>
            <!-- BUDGET TRACKER (PREMIUM ONLY) -->
            <div id="pageBudget" class="page">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h2 style="font-size: 20px;">💰 Budget Tracker</h2>
                    <button class="btn btn-primary btn-sm" id="addBudgetBtn" onclick="showAddBudgetModal()">+ Entry</button>
                </div>
                <div class="card">
                    <h3>💵 Balance</h3>
                    <div style="text-align: center; padding: 10px 0;">
                        <div style="font-size: 32px; font-weight: 700;" id="budgetBalance">₱0.00</div>
                    </div>
                    <div style="display: flex; justify-content: space-around; margin-top: 10px;">
                        <div style="text-align: center;">
                            <div style="color: var(--success); font-weight: 600;" id="totalIncome">+₱0.00</div>
                            <div style="font-size: 12px; color: var(--muted);">Income</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: var(--danger); font-weight: 600;" id="totalExpense">-₱0.00</div>
                            <div style="font-size: 12px; color: var(--muted);">Expense</div>
                        </div>
                    </div>
                </div>
                <div id="budgetList"></div>
            </div>
            <!-- STUDY PLANNER -->
            <div id="pagePlanner" class="page">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h2 style="font-size: 20px;">📈 Study Planner</h2>
                    <button class="btn btn-primary btn-sm" onclick="showAddGoalModal()">+ Goal</button>
                </div>
                <div id="goalsList"></div>
            </div>
            <!-- PREMIUM PAGE -->
            <div id="pagePremium" class="page">
                <div style="text-align: center; padding: 10px 0 20px;">
                    <h2 style="font-size: 24px; background: var(--gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">👑 Unlock TaskHive Premium</h2>
                    <p style="color: var(--muted); margin-top: 6px;">Get the full TaskHive experience</p>
                </div>
                <div class="card" id="premiumStatusCard">
                    <h3>Your Subscription</h3>
                    <div id="premiumInactive" style="text-align: center; padding: 10px 0;">
                        <p style="color: var(--muted);">You are currently on the <strong>Free Plan</strong></p>
                        <div class="countdown-box">
                            <div style="font-size: 24px; font-weight: 700;">₱50.00</div>
                            <div style="font-size: 13px; opacity: 0.9;">per month (30 days)</div>
                        </div>
                    </div>
                    <div id="premiumActive" style="display: none; text-align: center; padding: 10px 0;">
                        <div style="font-size: 22px;">✅</div>
                        <p style="color: var(--success); font-weight: 600;">Premium Activated!</p>
                        <p style="font-size: 13px; color: var(--muted);" id="premiumExpiryText">Valid until: --</p>
                        <div class="countdown-box" id="premiumCountdown">
                            Your Premium expires in: <strong>-- days</strong>
                        </div>
                    </div>
                </div>
                <!-- ========== GCASH PAYMENT: QR + Go to GCash button ========== -->
                <div class="card" id="payCard">
                    <h3>💳 Pay via GCash <span style="font-size:13px; color:var(--success);">₱50.00 auto-set</span></h3>
                    <!-- ⚠️ ILAGAY DITO ANG ORIGINAL NA base64 QR MO: palitan ang __ILAGAY_DITO_ANG_QR_BASE64_MO__
                         ng mahabang base64 string mula sa lumang file (nagsisimula sa /9j/4AAQ... nagtatapos sa ...2Q==) -->
                    <div class="qr-code" style="width:240px;">
                        <img id="gcashQrImg" src="data:image/jpeg;base64,__ILAGAY_DITO_ANG_QR_BASE64_MO__" alt="GCash QR — ₱50.00" style="width:100%; display:block;">
                    </div>
                    <p class="qr-hint">
                        I-scan gamit ang GCash app → <strong>Scan QR</strong>.<br>
                        Ang <strong>₱50.00</strong> ay naka-set na sa QR — hindi na kailangang i-type.
                    </p>
                    <button class="btn btn-primary" style="margin-top:14px;" onclick="openGcashApp()">📱 Go to GCash</button>
                    <p class="qr-hint" style="margin-top:10px;">
                        O manu-manong mag-send: <strong>Send Money → Express Send</strong><br>
                        Number: <span id="gcNumber" style="font-weight:600;">0970-456-XXXX</span> · Name: <span id="gcName">--</span><br>
                        Amount: <strong>₱50.00</strong> (fixed)
                        <br><button class="btn btn-outline btn-sm" style="margin-top:8px; padding:6px 14px;" onclick="copyGcashNumber()">📋 Copy Number</button>
                    </p>
                    <ol style="font-size: 13px; line-height: 1.7; color: var(--muted); padding-left: 20px; margin-top: 16px;">
                        <li>Mag-send ng eksaktong <strong>₱50.00</strong></li>
                        <li>Ilagay ang Reference ID sa message/note ng GCash</li>
                        <li>I-click ang "I Have Sent Payment" — <strong>mag-a-activate agad ang Premium</strong></li>
                    </ol>
                    <div class="form-group" style="margin-top: 16px;">
                        <label>Your Reference ID</label>
                        <input type="text" id="refIdDisplay" readonly style="background: var(--border);">
                        <small style="color: var(--muted); font-size: 12px;">Awtomatikong ginawa. Ilagay ito sa GCash note.</small>
                    </div>
                    <button class="btn btn-success" onclick="submitPaymentConfirmation()">✅ I Have Sent Payment</button>
                    <p id="paymentStatusText" style="text-align: center; margin-top: 12px; font-size: 14px;"></p>
                </div>
                <div class="card">
                    <h3>✨ Premium Features</h3>
                    <div class="premium-features">
                        <p>✅ Deadline Reminders — custom alerts for tasks</p>
                        <p>✅ Missed Task Recovery — reschedule overdue tasks</p>
                        <p>✅ Export Reports — PDF/CSV download</p>
                        <p>✅ Time Estimator — calculate study time needed</p>
                        <p>✅ AI Study Assistant — instant study help</p>
                        <p>✅ Exam Countdown — track exam dates</p>
                        <p>✅ Focus Mode — distraction-free timer</p>
                        <p>✅ Budget Tracker — manage student finances</p>
                    </div>
                </div>
            </div>
            <!-- SETTINGS -->
            <div id="pageSettings" class="page">
                <h2 style="font-size: 20px; margin-bottom: 16px;">⚙️ Settings</h2>
                <div class="card">
                    <h3>🎨 Theme</h3>
                    <label style="display: flex; align-items: center; justify-content: space-between; cursor: pointer;">
                        <span>Dark Mode</span>
                        <input type="checkbox" id="darkModeToggle" onchange="toggleTheme()">
                    </label>
                </div>
                <div class="card">
                    <h3>👤 Account</h3>
                    <p><strong>Name:</strong> <span id="settingsName">--</span></p>
                    <p><strong>Email:</strong> <span id="settingsEmail">--</span></p>
                    <p><strong>Student ID:</strong> <span id="settingsSID">--</span></p>
                    <p><strong>Course:</strong> <span id="settingsCourse">--</span></p>
                    <p><strong>Member Since:</strong> <span id="settingsJoin">--</span></p>
                </div>
                <div class="card">
                    <h3>💎 Subscription</h3>
                    <p><strong>Plan:</strong> <span id="currentPlan">Free</span></p>
                    <p><strong>Status:</strong> <span id="subStatus">Inactive</span></p>
                    <button class="btn btn-primary" style="margin-top: 10px;" onclick="navigateTo('premium')">Upgrade to Premium</button>
                </div>
                <div class="card">
                    <h3>ℹ️ About TaskHive</h3>
                    <p style="font-size: 14px; color: var(--muted);">Version 1.0.0<br>
                    Plan • Study • Achieve<br>
                    Made for Filipino Students 🇵🇭</p>
                </div>
            </div>
        </div>
        <!-- BOTTOM NAVIGATION -->
        <div class="bottom-nav">
            <div class="nav-item active" data-page="dashboard" onclick="navigateTo('dashboard')">
                <span>🏠</span> Home
            </div>
            <div class="nav-item" data-page="tasks" onclick="navigateTo('tasks')">
                <span>✅</span> Tasks
            </div>
            <div class="nav-item" style="transform: translateY(-10px);">
                <button style="width: 44px; height: 44px; border-radius: 50%; background: var(--gradient); border: none; color: white; font-size: 22px; cursor: pointer;" onclick="showQuickAddModal()">+</button>
            </div>
            <div class="nav-item" data-page="schedule" onclick="navigateTo('schedule')">
                <span>📅</span> Schedule
            </div>
            <div class="nav-item" data-page="profile" onclick="navigateTo('settings')">
                <span>👤</span> Profile
            </div>
        </div>
    </div>
    <!-- MODALS -->
    <div class="modal-overlay" id="addTaskModal">
        <div class="modal">
            <h2>➕ Add New Task</h2>
            <div class="form-group">
                <label>Title *</label>
                <input type="text" id="taskTitle" placeholder="e.g. Math Assignment">
            </div>
            <div class="form-group">
                <label>Subject</label>
                <input type="text" id="taskSubject" placeholder="e.g. Mathematics">
            </div>
            <div class="form-group">
                <label>Description</label>
                <textarea id="taskDesc" rows="3" placeholder="Details..."></textarea>
            </div>
            <div class="form-group">
                <label>Due Date *</label>
                <input type="date" id="taskDueDate">
            </div>
            <div class="form-group">
                <label>Due Time</label>
                <input type="time" id="taskDueTime" value="23:59">
            </div>
            <div class="form-group">
                <label>Priority</label>
                <select id="taskPriority">
                    <option value="high">🔴 High</option>
                    <option value="medium" selected>🟡 Medium</option>
                    <option value="low">🟢 Low</option>
                </select>
            </div>
            <label style="display: flex; align-items: center; margin-bottom: 16px;">
                <input type="checkbox" id="taskReminder"> Set Reminder (Premium)
            </label>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('addTaskModal')">Cancel</button>
                <button class="btn btn-primary" onclick="saveTask()">Save Task</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="addScheduleModal">
        <div class="modal">
            <h2>📅 Add Class Schedule</h2>
            <div class="form-group">
                <label>Subject *</label>
                <input type="text" id="schSubject" placeholder="e.g. Computer Programming">
            </div>
            <div class="form-group">
                <label>Day *</label>
                <select id="schDay">
                    <option>Monday</option>
                    <option>Tuesday</option>
                    <option>Wednesday</option>
                    <option>Thursday</option>
                    <option>Friday</option>
                    <option>Saturday</option>
                </select>
            </div>
            <div class="form-group">
                <label>Start Time *</label>
                <input type="time" id="schStart">
            </div>
            <div class="form-group">
                <label>End Time *</label>
                <input type="time" id="schEnd">
            </div>
            <div class="form-group">
                <label>Room</label>
                <input type="text" id="schRoom" placeholder="e.g. Room 302 / Online">
            </div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('addScheduleModal')">Cancel</button>
                <button class="btn btn-primary" onclick="saveSchedule()">Save</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="addNoteModal">
        <div class="modal">
            <h2>📝 Create Note</h2>
            <div class="form-group">
                <label>Title *</label>
                <input type="text" id="noteTitle" placeholder="Note title">
            </div>
            <div class="form-group">
                <label>Folder</label>
                <select id="noteFolder">
                    <option value="General">📁 General</option>
                    <option value="Reviewer">📋 Reviewer</option>
                    <option value="Lecture">📖 Lecture</option>
                    <option value="Personal">✏️ Personal</option>
                </select>
            </div>
            <div class="form-group">
                <label>Content</label>
                <textarea id="noteContent" rows="6" placeholder="Write your notes here..."></textarea>
            </div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('addNoteModal')">Cancel</button>
                <button class="btn btn-primary" onclick="saveNote()">Save Note</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="addProjectModal">
        <div class="modal">
            <h2>👥 New Group Project</h2>
            <div class="form-group">
                <label>Project Name *</label>
                <input type="text" id="projName" placeholder="Project title">
            </div>
            <div class="form-group">
                <label>Members</label>
                <input type="text" id="projMembers" placeholder="Names separated by comma">
            </div>
            <div class="form-group">
                <label>Deadline</label>
                <input type="date" id="projDeadline">
            </div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('addProjectModal')">Cancel</button>
                <button class="btn btn-primary" onclick="saveProject()">Save</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="addGradeModal">
        <div class="modal">
            <h2>📊 Record Grade</h2>
            <div class="form-group">
                <label>Subject *</label>
                <input type="text" id="gradeSubject" placeholder="Subject name">
            </div>
            <div class="form-group">
                <label>Score (0-100) *</label>
                <input type="number" id="gradeScore" min="0" max="100" step="0.1" placeholder="85.5">
            </div>
            <div class="form-group">
                <label>Units</label>
                <input type="number" id="gradeUnits" value="3" min="1" max="6">
            </div>
            <div class="form-group">
                <label>Semester</label>
                <input type="text" id="gradeSem" placeholder="1st Sem, AY 2024-2025">
            </div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('addGradeModal')">Cancel</button>
                <button class="btn btn-primary" onclick="saveGrade()">Save</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="addBudgetModal">
        <div class="modal">
            <h2>💰 Add Transaction</h2>
            <div class="form-group">
                <label>Type</label>
                <select id="budgType">
                    <option value="income">📈 Income / Allowance</option>
                    <option value="expense">📉 Expense</option>
                </select>
            </div>
            <div class="form-group">
                <label>Category</label>
                <input type="text" id="budgCat" placeholder="Food, Transport, School Supplies...">
            </div>
            <div class="form-group">
                <label>Amount (₱) *</label>
                <input type="number" id="budgAmt" step="1" placeholder="500">
            </div>
            <div class="form-group">
                <label>Description</label>
                <input type="text" id="budgDesc" placeholder="Optional note">
            </div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('addBudgetModal')">Cancel</button>
                <button class="btn btn-primary" onclick="saveBudget()">Save</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="addGoalModal">
        <div class="modal">
            <h2>🎯 New Study Goal</h2>
            <div class="form-group">
                <label>Goal *</label>
                <textarea id="goalText" rows="3" placeholder="What do you want to achieve?"></textarea>
            </div>
            <div class="form-group">
                <label>Target Date</label>
                <input type="date" id="goalDate">
            </div>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('addGoalModal')">Cancel</button>
                <button class="btn btn-primary" onclick="saveGoal()">Save</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="premiumLockModal">
        <div class="modal" style="text-align: center;">
            <div style="font-size: 48px; margin-bottom: 16px;">🔒</div>
            <h2>Premium Feature</h2>
            <p style="color: var(--muted); margin-bottom: 20px;">This feature is only available for Premium subscribers.</p>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeModal('premiumLockModal')">Not Now</button>
                <button class="btn btn-primary" onclick="closeModal('premiumLockModal'); navigateTo('premium');">Upgrade — ₱50/mo</button>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="quickAddModal">
        <div class="modal">
            <h2>⚡ Quick Add</h2>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px;">
                <button class="quick-btn" onclick="closeModal('quickAddModal'); showAddTaskModal();">
                    <span>✅</span> Task
                </button>
                <button class="quick-btn" onclick="closeModal('quickAddModal'); showAddScheduleModal();">
                    <span>📅</span> Class
                </button>
                <button class="quick-btn" onclick="closeModal('quickAddModal'); showAddNoteModal();">
                    <span>📝</span> Note
                </button>
                <button class="quick-btn" onclick="closeModal('quickAddModal'); showAddProjectModal();">
                    <span>👥</span> Project
                </button>
            </div>
            <button class="btn btn-outline" style="margin-top: 16px;" onclick="closeModal('quickAddModal')">Cancel</button>
        </div>
    </div>
</div>
<script>
// ========== GLOBAL VARIABLES ==========
let currentUser = null;
let isPremium = false;
let tasks = [];
let schedule = [];
let notes = [];
let projects = [];
let grades = [];
let budget = [];
let goals = [];
let referenceId = null;

// ========== INITIALIZATION ==========
document.addEventListener('DOMContentLoaded', function() {
    checkSession();
    setDailyQuote();
    setGreeting();
});

// AUTO-DETECT: kapag bumalik ang user mula sa GCash app (naging visible ulit ang page),
// i-check agad ang Premium status (sakaling na-activate na).
document.addEventListener('visibilitychange', function() {
    if (!document.hidden && referenceId && !isPremium) {
        setTimeout(loadPremiumStatus, 800);
    }
});

function checkSession() {
    fetch('/api/user')
        .then(res => {
            if (!res.ok) throw new Error('Unauthorized');
            return res.json();
        })
        .then(data => {
            currentUser = data;
            isPremium = data.is_premium;
            showMainApp();
            updateUserUI();
            loadAllData();
        })
        .catch(() => {
            showAuthPage('login');
        });
}

function showAuthPage(page) {
    document.getElementById('authSection').style.display = 'block';
    document.getElementById('mainApp').style.display = 'none';
    document.getElementById('loginPage').style.display = page === 'login' ? 'flex' : 'none';
    document.getElementById('registerPage').style.display = page === 'register' ? 'flex' : 'none';
}

function showPage(pageName) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page${pageName.charAt(0).toUpperCase() + pageName.slice(1)}`).classList.add('active');
    const titles = {
        dashboard: 'Dashboard', tasks: 'My Tasks', schedule: 'Schedule', notes: 'Notes',
        projects: 'Projects', grades: 'Grades', budget: 'Budget Tracker',
        planner: 'Study Planner', premium: '✨ Premium', settings: 'Settings'
    };
    document.getElementById('pageTitle').textContent = titles[pageName] || 'TaskHive';
    document.getElementById('sidebar').classList.remove('show');
    document.getElementById('sidebarOverlay').classList.remove('show');
    updateBottomNav(pageName);
}

function navigateTo(pageName) {
    if (['budget'].includes(pageName) && !isPremium) {
        showModal('premiumLockModal');
        return;
    }
    showPage(pageName);
    if (pageName === 'premium') {
        loadPremiumStatus();
        if (!isPremium && !referenceId) generateReference();
    }
}

function showMainApp() {
    document.getElementById('authSection').style.display = 'none';
    document.getElementById('mainApp').style.display = 'block';
    showPage('dashboard');
    applyTheme(currentUser?.theme || 'light');
}

function updateUserUI() {
    if (!currentUser) return;
    document.getElementById('sidebarName').textContent = currentUser.full_name;
    document.getElementById('sidebarCourse').textContent = currentUser.course_year;
    document.getElementById('settingsName').textContent = currentUser.full_name;
    document.getElementById('settingsEmail').textContent = currentUser.email;
    document.getElementById('settingsSID').textContent = currentUser.student_id;
    document.getElementById('settingsCourse').textContent = currentUser.course_year;
    document.getElementById('settingsJoin').textContent = new Date(currentUser.join_date).toLocaleDateString('en-PH');
    setGreeting();
    updatePremiumUI();
}

function updatePremiumUI() {
    const premiumBadge = document.getElementById('sidebarPremiumBadge');
    const expiryText = document.getElementById('sidebarExpiry');
    const budgetMenu = document.getElementById('menuBudget');
    const planText = document.getElementById('currentPlan');
    const subStatus = document.getElementById('subStatus');
    if (isPremium) {
        premiumBadge.style.display = 'block';
        expiryText.textContent = `Valid until: ${currentUser.premium_expiry ? new Date(currentUser.premium_expiry.replace(' ', 'T')).toLocaleDateString('en-PH') : '--'}`;
        budgetMenu.classList.remove('locked');
        budgetMenu.querySelector('.lock').style.display = 'none';
        planText.textContent = '👑 Premium';
        subStatus.textContent = 'Active ✅';
        subStatus.style.color = 'var(--success)';
    } else {
        premiumBadge.style.display = 'none';
        expiryText.textContent = '';
        budgetMenu.classList.add('locked');
        budgetMenu.querySelector('.lock').style.display = 'inline';
        planText.textContent = 'Free';
        subStatus.textContent = 'Inactive';
        subStatus.style.color = 'var(--muted)';
    }
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('show');
    document.getElementById('sidebarOverlay').classList.toggle('show');
}

function updateBottomNav(page) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.page === page) item.classList.add('active');
    });
}

function resetModal(id) {
    document.getElementById(id).querySelectorAll('input, textarea, select').forEach(el => {
        if (el.type === 'checkbox') el.checked = false;
        else if (el.tagName === 'SELECT') {
            const i = [...el.options].findIndex(o => o.defaultSelected);
            el.selectedIndex = i < 0 ? 0 : i;
        } else el.value = el.defaultValue;
    });
}

// ========== THEME ==========
function toggleTheme() {
    const isDark = document.getElementById('darkModeToggle').checked;
    applyTheme(isDark ? 'dark' : 'light');
    fetch('/api/user/theme', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({theme: isDark ? 'dark' : 'light'})
    });
}

function applyTheme(theme) {
    if (theme === 'dark') {
        document.body.classList.add('dark');
        document.getElementById('darkModeToggle').checked = true;
    } else {
        document.body.classList.remove('dark');
        document.getElementById('darkModeToggle').checked = false;
    }
}

// ========== GREETING & QUOTE ==========
function setGreeting() {
    const hour = new Date().getHours();
    let greeting = 'Good Evening';
    if (hour >= 5 && hour < 12) greeting = 'Good Morning';
    else if (hour >= 12 && hour < 18) greeting = 'Good Afternoon';
    document.getElementById('greeting').textContent = `${greeting}${currentUser ? ', ' + currentUser.full_name.split(' ')[0] : ''}!`;
}

function setDailyQuote() {
    const quotes = [
        '"Your future is created by what you do today, not tomorrow."',
        '"Study now, be proud later."',
        '"Every expert was once a beginner."',
        '"Dream big. Start small. But most importantly, start."',
        '"It always seems impossible until it\'s done."'
    ];
    const today = new Date().getDate();
    document.getElementById('dailyQuote').textContent = quotes[today % quotes.length];
}

// ========== MODALS ==========
function showModal(id) { document.getElementById(id).classList.add('show'); }
function closeModal(id) { document.getElementById(id).classList.remove('show'); }
function showAddTaskModal() { showModal('addTaskModal'); }
function showAddScheduleModal() { showModal('addScheduleModal'); }
function showAddNoteModal() { showModal('addNoteModal'); }
function showAddProjectModal() { showModal('addProjectModal'); }
function showAddGradeModal() { showModal('addGradeModal'); }
function showAddBudgetModal() {
    if (!isPremium) { showModal('premiumLockModal'); return; }
    showModal('addBudgetModal');
}
function showAddGoalModal() { showModal('addGoalModal'); }
function showQuickAddModal() { showModal('quickAddModal'); }
function showPremiumModal() { showModal('premiumLockModal'); }

// ========== AUTH ==========
document.getElementById('loginForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;
    const remember = document.getElementById('rememberMe').checked;
    fetch('/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email, password, remember})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            document.getElementById('loginSuccess').classList.remove('show');
            document.getElementById('loginError').classList.remove('show');
            checkSession();
        } else {
            document.getElementById('loginSuccess').classList.remove('show');
            document.getElementById('loginError').textContent = data.error;
            document.getElementById('loginError').classList.add('show');
        }
    });
});

document.getElementById('registerForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const full_name = document.getElementById('regName').value;
    const email = document.getElementById('regEmail').value;
    const student_id = document.getElementById('regStudentId').value;
    const course_year = document.getElementById('regCourse').value;
    const password = document.getElementById('regPassword').value;
    const confirm_password = document.getElementById('regConfirmPass').value;
    fetch('/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({full_name, email, student_id, course_year, password, confirm_password})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            document.getElementById('registerForm').reset();
            document.getElementById('regError').classList.remove('show');
            showAuthPage('login');
            document.getElementById('loginEmail').value = email.trim().toLowerCase();
            document.getElementById('loginPassword').value = '';
            document.getElementById('loginError').classList.remove('show');
            const ok = document.getElementById('loginSuccess');
            ok.textContent = '✅ Account created! Please log in.';
            ok.classList.add('show');
        } else {
            document.getElementById('regError').textContent = data.error;
            document.getElementById('regError').classList.add('show');
        }
    });
});

function logout() {
    if (confirm('Are you sure you want to log out?')) {
        window.location.href = '/logout';
    }
}

// ========== DATA LOADING ==========
function loadAllData() {
    loadTasks();
    loadSchedule();
    loadNotes();
    loadProjects();
    loadGrades();
    if (isPremium) loadBudget();
    loadGoals();
}

// --- TASKS ---
function loadTasks() {
    fetch('/api/tasks')
        .then(res => res.json())
        .then(data => {
            tasks = data;
            renderDashboardTasks();
            renderAllTasks();
            updateStats();
        });
}

function saveTask() {
    const title = document.getElementById('taskTitle').value.trim();
    if (!title) { alert('Please enter a title!'); return; }
    if (!document.getElementById('taskDueDate').value) { alert('Please pick a due date!'); return; }
    const data = {
        title: title,
        subject: document.getElementById('taskSubject').value,
        description: document.getElementById('taskDesc').value,
        due_date: document.getElementById('taskDueDate').value,
        due_time: document.getElementById('taskDueTime').value,
        priority: document.getElementById('taskPriority').value,
        reminder_set: document.getElementById('taskReminder').checked
    };
    fetch('/api/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => {
        closeModal('addTaskModal');
        resetModal('addTaskModal');
        loadTasks();
    });
}

function toggleTaskComplete(id, currentStatus) {
    fetch('/api/tasks', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, completed: currentStatus ? 0 : 1})
    })
    .then(res => res.json())
    .then(() => loadTasks());
}

function deleteTask(id) {
    if (!confirm('Delete this task?')) return;
    fetch(`/api/tasks?id=${id}`, {method: 'DELETE'})
        .then(res => res.json())
        .then(() => loadTasks());
}

function getDaysRemaining(dueDateStr) {
    const due = new Date(dueDateStr);
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    due.setHours(0, 0, 0, 0);
    return Math.ceil((due - now) / (1000 * 60 * 60 * 24));
}

function renderDashboardTasks() {
    const today = new Date().toISOString().split('T')[0];
    const upcomingList = document.getElementById('upcomingTasksList');
    const upcomingTasks = tasks.filter(t => t.due_date >= today && !t.completed).sort((a, b) => new Date(a.due_date) - new Date(b.due_date)).slice(0, 5);
    renderTodaySchedule();
    if (upcomingTasks.length === 0) {
        upcomingList.innerHTML = '<div class="empty-state"><span>🎉</span>No upcoming deadlines. You\'re all caught up!</div>';
    } else {
        upcomingList.innerHTML = upcomingTasks.map(t => {
            const daysLeft = getDaysRemaining(t.due_date);
            let dueClass = 'due-later';
            let dueText = `${daysLeft} days left`;
            if (daysLeft === 0) { dueClass = 'due-today'; dueText = 'Today!'; }
            else if (daysLeft < 0) { dueClass = 'due-overdue'; dueText = `${Math.abs(daysLeft)} days overdue`; }
            else if (daysLeft <= 2) { dueClass = 'due-today'; }
            return `
                <div class="task-item">
                    <div class="task-priority priority-${t.priority}"></div>
                    <div class="task-text">
                        <div class="task-title">${t.title}</div>
                        <div class="task-meta">${t.subject || 'No subject'} · ${new Date(t.due_date).toLocaleDateString('en-PH')}
                            <span class="task-due ${dueClass}">${dueText}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }
}

function renderAllTasks() {
    const container = document.getElementById('allTasksList');
    if (tasks.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>📋</span>No tasks yet. Click "+ Add Task" to get started!</div>';
        return;
    }
    container.innerHTML = tasks.sort((a, b) => new Date(a.due_date) - new Date(b.due_date)).map(t => {
        const daysLeft = getDaysRemaining(t.due_date);
        let dueClass = 'due-later';
        let dueText = `${daysLeft}d`;
        if (daysLeft === 0) { dueClass = 'due-today'; dueText = 'Today'; }
        else if (daysLeft < 0) { dueClass = 'due-overdue'; dueText = `${Math.abs(daysLeft)}d overdue`; }
        return `
            <div class="card" style="margin-bottom: 10px;">
                <div class="task-item" style="border-bottom: none; padding: 0;">
                    <input type="checkbox" ${t.completed ? 'checked' : ''} onchange="toggleTaskComplete(${t.id}, ${t.completed})" style="flex-shrink: 0;">
                    <div class="task-priority priority-${t.priority}"></div>
                    <div class="task-text">
                        <div class="task-title ${t.completed ? 'completed' : ''}">${t.title}</div>
                        <div class="task-meta">
                            ${t.subject ? `<strong>${t.subject}</strong> · ` : ''}
                            ${new Date(t.due_date).toLocaleDateString('en-PH')} ${t.due_time || ''}
                            <span class="task-due ${dueClass}">${dueText}</span>
                        </div>
                        ${t.description ? `<div style="font-size: 12px; color: var(--muted); margin-top: 4px;">${t.description}</div>` : ''}
                    </div>
                    <button onclick="deleteTask(${t.id})" style="background: none; border: none; color: var(--danger); cursor: pointer;">🗑️</button>
                </div>
            </div>
        `;
    }).join('');
}

function updateStats() {
    const total = tasks.length;
    const done = tasks.filter(t => t.completed).length;
    const pending = total - done;
    const today = new Date().toISOString().split('T')[0];
    const overdue = tasks.filter(t => !t.completed && t.due_date < today).length;
    const percent = total > 0 ? Math.round((done / total) * 100) : 0;
    document.getElementById('statPercent').textContent = `${percent}%`;
    document.getElementById('statDone').textContent = done;
    document.getElementById('statPending').textContent = pending;
    document.getElementById('statOverdue').textContent = overdue;
    document.querySelector('.stat-circle').style.background =
        `conic-gradient(var(--primary) ${percent}%, var(--border) ${percent}% 100%)`;
}

// --- SCHEDULE ---
function loadSchedule() {
    fetch('/api/schedule')
        .then(res => res.json())
        .then(data => {
            schedule = data;
            renderTodaySchedule();
            renderFullSchedule();
        });
}

function saveSchedule() {
    if (!document.getElementById('schSubject').value.trim()) { alert('Please enter a subject!'); return; }
    if (!document.getElementById('schStart').value || !document.getElementById('schEnd').value) { alert('Please set start and end time!'); return; }
    if (document.getElementById('schEnd').value <= document.getElementById('schStart').value) { alert('End time must be after start time!'); return; }
    const data = {
        subject: document.getElementById('schSubject').value,
        day: document.getElementById('schDay').value,
        time_start: document.getElementById('schStart').value,
        time_end: document.getElementById('schEnd').value,
        room: document.getElementById('schRoom').value
    };
    fetch('/api/schedule', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => {
        closeModal('addScheduleModal');
        resetModal('addScheduleModal');
        loadSchedule();
    });
}

function deleteSchedule(id) {
    if (!confirm('Delete this schedule?')) return;
    fetch(`/api/schedule?id=${id}`, {method: 'DELETE'})
        .then(res => res.json())
        .then(() => loadSchedule());
}

function getTodayName() {
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    return days[new Date().getDay()];
}

function renderTodaySchedule() {
    const today = getTodayName();
    const todaySched = schedule.filter(s => s.day === today).sort((a, b) => a.time_start.localeCompare(b.time_start));
    const container = document.getElementById('todayScheduleList');
    if (todaySched.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>📭</span>No classes today. Enjoy your time!</div>';
    } else {
        container.innerHTML = todaySched.map(s => `
            <div class="task-item">
                <div style="width: 4px; background: ${s.color}; border-radius: 2px; flex-shrink: 0;"></div>
                <div class="task-text">
                    <div class="task-title">${s.subject}</div>
                    <div class="task-meta">${formatTime(s.time_start)} - ${formatTime(s.time_end)} · ${s.room || 'No room'}</div>
                </div>
            </div>
        `).join('');
    }
}

function formatTime(t) {
    if (!t) return '';
    const [h, m] = t.split(':');
    const hour = parseInt(h);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const h12 = hour % 12 || 12;
    return `${h12}:${m} ${ampm}`;
}

function renderFullSchedule() {
    const container = document.getElementById('scheduleList');
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    if (schedule.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>📅</span>No schedule yet. Add your first class!</div>';
        return;
    }
    container.innerHTML = days.map(day => {
        const daySched = schedule.filter(s => s.day === day).sort((a, b) => a.time_start.localeCompare(b.time_start));
        if (daySched.length === 0) return '';
        return `
            <div class="card">
                <h4 style="margin-bottom: 10px; color: var(--primary);">${day}</h4>
                ${daySched.map(s => `
                    <div class="task-item" style="border-bottom: 1px solid var(--border); padding: 8px 0;">
                        <div style="width: 4px; background: ${s.color}; border-radius: 2px; flex-shrink: 0; min-height: 40px;"></div>
                        <div class="task-text">
                            <div style="font-weight: 500;">${s.subject}</div>
                            <div style="font-size: 12px; color: var(--muted);">${formatTime(s.time_start)} - ${formatTime(s.time_end)} · ${s.room || 'No room'}</div>
                        </div>
                        <button onclick="deleteSchedule(${s.id})" style="background: none; border: none; color: var(--muted); cursor: pointer; font-size: 14px;">×</button>
                    </div>
                `).join('')}
            </div>
        `;
    }).join('');
}

// --- NOTES ---
function loadNotes() {
    fetch('/api/notes')
        .then(res => res.json())
        .then(data => {
            notes = data;
            renderNotes();
        });
}

function saveNote() {
    const title = document.getElementById('noteTitle').value.trim();
    if (!title) { alert('Please enter a title!'); return; }
    const data = {
        title: title,
        content: document.getElementById('noteContent').value,
        folder_name: document.getElementById('noteFolder').value
    };
    fetch('/api/notes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => {
        closeModal('addNoteModal');
        resetModal('addNoteModal');
        loadNotes();
    });
}

function deleteNote(id) {
    if (!confirm('Delete this note?')) return;
    fetch(`/api/notes?id=${id}`, {method: 'DELETE'})
        .then(res => res.json())
        .then(() => loadNotes());
}

function renderNotes() {
    const container = document.getElementById('notesList');
    const folders = {'General': '📁 General', 'Reviewer': '📋 Reviewer', 'Lecture': '📖 Lecture', 'Personal': '✏️ Personal'};
    if (notes.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>📝</span>No notes yet. Start writing!</div>';
        return;
    }
    container.innerHTML = Object.entries(folders).map(([key, label]) => {
        const folderNotes = notes.filter(n => n.folder_name === key);
        if (folderNotes.length === 0) return '';
        return `
            <div class="card">
                <h4 style="margin-bottom: 12px;">${label}</h4>
                ${folderNotes.map(n => `
                    <div style="padding: 10px 0; border-bottom: 1px solid var(--border);">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <div style="font-weight: 500;">${n.title}</div>
                                ${n.content ? `<div style="font-size: 13px; color: var(--muted); margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px;">${n.content}</div>` : ''}
                                <div style="font-size: 11px; color: var(--muted); margin-top: 4px;">${new Date(n.updated_at).toLocaleDateString('en-PH')}</div>
                            </div>
                            <button onclick="deleteNote(${n.id})" style="background: none; border: none; color: var(--danger); cursor: pointer;">🗑️</button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }).join('');
}

// --- PROJECTS ---
function loadProjects() {
    fetch('/api/projects')
        .then(res => res.json())
        .then(data => {
            projects = data;
            renderProjects();
        });
}

function saveProject() {
    const name = document.getElementById('projName').value.trim();
    if (!name) { alert('Please enter a project name!'); return; }
    const data = {
        name: name,
        members: document.getElementById('projMembers').value,
        deadline: document.getElementById('projDeadline').value
    };
    fetch('/api/projects', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => {
        closeModal('addProjectModal');
        resetModal('addProjectModal');
        loadProjects();
    });
}

function updateProjectStatus(id, status) {
    fetch('/api/projects', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, status: status})
    })
    .then(res => res.json())
    .then(() => loadProjects());
}

function deleteProject(id) {
    if (!confirm('Delete this project?')) return;
    fetch(`/api/projects?id=${id}`, {method: 'DELETE'})
        .then(res => res.json())
        .then(() => loadProjects());
}

function renderProjects() {
    const container = document.getElementById('projectsList');
    if (projects.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>👥</span>No projects yet. Create one for your group!</div>';
        return;
    }
    container.innerHTML = projects.map(p => `
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <h4 style="font-size: 16px;">${p.name}</h4>
                <span style="font-size: 12px; padding: 3px 8px; border-radius: 10px; background: ${p.status === 'Completed' ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)'} ; color: ${p.status === 'Completed' ? 'var(--success)' : 'var(--warning)'};">${p.status}</span>
            </div>
            ${p.members ? `<p style="font-size: 13px; color: var(--muted);"><strong>Members:</strong> ${p.members}</p>` : ''}
            ${p.deadline ? `<p style="font-size: 13px; color: var(--muted);"><strong>Deadline:</strong> ${new Date(p.deadline).toLocaleDateString('en-PH')}</p>` : ''}
            <div style="display: flex; gap: 8px; margin-top: 12px;">
                ${p.status !== 'Completed'
                    ? `<button class="btn btn-success btn-sm" onclick="updateProjectStatus(${p.id}, 'Completed')">✓ Mark Done</button>`
                    : ''}
                <button class="btn btn-danger btn-sm" onclick="deleteProject(${p.id})">🗑️ Delete</button>
            </div>
        </div>
    `).join('');
}

// --- GRADES & GPA ---
function loadGrades() {
    fetch('/api/grades')
        .then(res => res.json())
        .then(data => {
            grades = data;
            renderGrades();
            calculateGPA();
        });
}

function saveGrade() {
    const subject = document.getElementById('gradeSubject').value.trim();
    const score = parseFloat(document.getElementById('gradeScore').value);
    const units = parseFloat(document.getElementById('gradeUnits').value) || 3;
    if (!subject || isNaN(score)) { alert('Please enter subject and score!'); return; }
    if (score < 0 || score > 100) { alert('Score must be between 0 and 100!'); return; }
    const data = {
        subject: subject,
        score: score,
        units: units,
        semester: document.getElementById('gradeSem').value
    };
    fetch('/api/grades', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => {
        closeModal('addGradeModal');
        resetModal('addGradeModal');
        loadGrades();
    });
}

function deleteGrade(id) {
    if (!confirm('Delete this grade entry?')) return;
    fetch(`/api/grades?id=${id}`, {method: 'DELETE'})
        .then(res => res.json())
        .then(() => loadGrades());
}

function toGPAScale(score) {
    if (score >= 97) return 1.00;
    if (score >= 93) return 1.25;
    if (score >= 89) return 1.50;
    if (score >= 85) return 1.75;
    if (score >= 81) return 2.00;
    if (score >= 77) return 2.25;
    if (score >= 73) return 2.50;
    if (score >= 69) return 2.75;
    if (score >= 65) return 3.00;
    return 5.00;
}

function calculateGPA() {
    if (grades.length === 0) {
        document.getElementById('gpaDisplay').textContent = '--';
        return;
    }
    let totalWeight = 0;
    let totalUnits = 0;
    grades.forEach(g => {
        const gpa = toGPAScale(g.score);
        totalWeight += gpa * g.units;
        totalUnits += g.units;
    });
    const gpa = totalWeight / totalUnits;
    document.getElementById('gpaDisplay').textContent = gpa.toFixed(2);
}

function renderGrades() {
    const container = document.getElementById('gradesList');
    if (grades.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>📊</span>No grades recorded yet.</div>';
        return;
    }
    container.innerHTML = grades.map(g => {
        const gpa = toGPAScale(g.score);
        const color = gpa <= 1.5 ? 'var(--success)' : gpa <= 2.5 ? 'var(--warning)' : 'var(--danger)';
        return `
            <div class="card" style="margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: 500;">${g.subject}</div>
                        <div style="font-size: 12px; color: var(--muted);">${g.units} unit${g.units > 1 ? 's' : ''} · ${g.semester || ''}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 20px; font-weight: 700; color: ${color};">${gpa.toFixed(2)}</div>
                        <div style="font-size: 12px; color: var(--muted);">${g.score}/100</div>
                    </div>
                </div>
                <button onclick="deleteGrade(${g.id})" style="margin-top: 8px; background: none; border: none; color: var(--danger); cursor: pointer; font-size: 13px;">🗑️ Delete</button>
            </div>
        `;
    }).join('');
}

// --- BUDGET (PREMIUM ONLY) ---
function loadBudget() {
    fetch('/api/budget')
        .then(res => {
            if (res.status === 403) {
                document.getElementById('budgetList').innerHTML = '<div class="empty-state"><span>🔒</span>Premium feature required</div>';
                return;
            }
            return res.json();
        })
        .then(data => {
            if (!Array.isArray(data)) return;
            budget = data;
            renderBudget();
        });
}

function saveBudget() {
    const type = document.getElementById('budgType').value;
    const category = document.getElementById('budgCat').value.trim() || 'General';
    const amount = parseFloat(document.getElementById('budgAmt').value);
    if (isNaN(amount) || amount <= 0) { alert('Please enter a valid amount!'); return; }
    const data = { type, category, amount, description: document.getElementById('budgDesc').value };
    fetch('/api/budget', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => {
        closeModal('addBudgetModal');
        resetModal('addBudgetModal');
        loadBudget();
    });
}

function deleteBudget(id) {
    if (!confirm('Delete this transaction?')) return;
    fetch(`/api/budget?id=${id}`, {method: 'DELETE'})
        .then(res => res.json())
        .then(() => loadBudget());
}

function renderBudget() {
    let totalIncome = 0, totalExpense = 0;
    budget.forEach(b => {
        if (b.type === 'income') totalIncome += b.amount;
        else totalExpense += b.amount;
    });
    const balance = totalIncome - totalExpense;
    document.getElementById('budgetBalance').textContent = `₱${balance.toFixed(2)}`;
    document.getElementById('totalIncome').textContent = `+₱${totalIncome.toFixed(2)}`;
    document.getElementById('totalExpense').textContent = `-₱${totalExpense.toFixed(2)}`;
    const container = document.getElementById('budgetList');
    if (budget.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>💰</span>No transactions yet.</div>';
        return;
    }
    container.innerHTML = budget.map(b => `
        <div class="card" style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-weight: 500;">${b.category}</div>
                    <div style="font-size: 12px; color: var(--muted);">${b.description || 'No note'} · ${new Date(b.recorded_at).toLocaleDateString('en-PH')}</div>
                </div>
                <div style="font-weight: 600; color: ${b.type === 'income' ? 'var(--success)' : 'var(--danger)'};">
                    ${b.type === 'income' ? '+' : '-'}₱${b.amount.toFixed(2)}
                </div>
            </div>
        </div>
    `).join('');
}

// --- STUDY PLANNER / GOALS ---
function loadGoals() {
    fetch('/api/planner')
        .then(res => res.json())
        .then(data => {
            goals = data;
            renderGoals();
        });
}

function saveGoal() {
    const goal = document.getElementById('goalText').value.trim();
    if (!goal) { alert('Please write your goal!'); return; }
    const data = {
        goal: goal,
        target_date: document.getElementById('goalDate').value
    };
    fetch('/api/planner', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(() => {
        closeModal('addGoalModal');
        document.getElementById('goalText').value = '';
        document.getElementById('goalDate').value = '';
        loadGoals();
    });
}

function updateGoalProgress(id, progress) {
    fetch('/api/planner', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: id, progress: progress})
    })
    .then(res => res.json())
    .then(() => loadGoals());
}

function deleteGoal(id) {
    if (!confirm('Delete this goal?')) return;
    fetch(`/api/planner?id=${id}`, {method: 'DELETE'})
        .then(res => res.json())
        .then(() => loadGoals());
}

function renderGoals() {
    const container = document.getElementById('goalsList');
    if (goals.length === 0) {
        container.innerHTML = '<div class="empty-state"><span>🎯</span>No study goals yet. Set one to stay motivated!</div>';
        return;
    }
    container.innerHTML = goals.map(g => `
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="flex: 1;">
                    <div style="font-weight: 500; font-size: 15px;">${g.goal}</div>
                    ${g.target_date ? `<div style="font-size: 12px; color: var(--muted);">Target: ${new Date(g.target_date).toLocaleDateString('en-PH')}</div>` : ''}
                </div>
                <div style="font-weight: 600; color: var(--primary);">${g.progress}%</div>
            </div>
            <div style="height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; margin-bottom: 10px;">
                <div style="height: 100%; width: ${g.progress}%; background: var(--gradient); border-radius: 4px; transition: width 0.3s;"></div>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
                <button class="btn btn-sm" style="padding: 4px 8px; font-size: 12px;" onclick="updateGoalProgress(${g.id}, Math.max(0, ${g.progress}-10))">-10%</button>
                <button class="btn btn-sm" style="padding: 4px 8px; font-size: 12px;" onclick="updateGoalProgress(${g.id}, Math.min(100, ${g.progress}+10))">+10%</button>
                <button class="btn btn-success btn-sm" style="margin-left: auto; padding: 4px 10px; font-size: 12px;" onclick="updateGoalProgress(${g.id}, 100)">✓ Done!</button>
                <button class="btn btn-danger btn-sm" style="padding: 4px 8px; font-size: 12px;" onclick="deleteGoal(${g.id})">🗑️</button>
            </div>
        </div>
    `).join('');
}

function copyGcashNumber() {
    const raw = (document.getElementById('gcNumber')?.textContent || '').replace(/-/g, '').trim();
    if (!raw) { alert('Walang GCash number na naka-set.'); return; }
    const done = () => alert('✅ Nakopy na ang GCash number: ' + raw + '\nI-paste sa Send Money → Express Send.');
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(raw).then(done).catch(() => fallbackCopy(raw, done));
    } else {
        fallbackCopy(raw, done);
    }
}

function fallbackCopy(text, cb) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch(e) {}
    document.body.removeChild(ta);
    if (cb) cb();
}

function openGcashApp() {
    const raw = (document.getElementById('gcNumber')?.textContent || '').replace(/-/g, '').trim();
    if (raw) { try { navigator.clipboard && navigator.clipboard.writeText(raw); } catch(e) {} }
    const ua = navigator.userAgent || '';
    const isAndroid = /Android/i.test(ua);
    const isIOS = /iPhone|iPad|iPod/i.test(ua);
    const stepsMsg = (raw ? '✅ Number nakopy na: ' + raw + '\n' : '') +
        'Amount: ₱50.00 (FIXED — huwag palitan)\n\n' +
        'Sa GCash app:\n' +
        '1. Send Money → Express Send\n' +
        '2. I-paste ang number (kung hindi pa)\n' +
        '3. Amount: ₱50.00\n' +
        '4. Ilagay ang Reference ID sa message';
    const start = Date.now();
    const fallbackTimer = setTimeout(() => {
        if (!document.hidden && Date.now() - start < 3500) {
            if (confirm('📱 Hindi bumukas ang GCash app.\n\n' + stepsMsg + '\n\nI-download ang GCash mula sa store?')) {
                if (isAndroid) window.location.href = 'https://play.google.com/store/apps/details?id=com.globe.gcash.android';
                else if (isIOS) window.location.href = 'https://apps.apple.com/ph/app/gcash/id520010805';
            }
        }
    }, 2500);
    const visHandler = () => { if (document.hidden) { clearTimeout(fallbackTimer); document.removeEventListener('visibilitychange', visHandler); } };
    document.addEventListener('visibilitychange', visHandler);
    if (isAndroid) {
        try { window.location.href = 'intent://#Intent;scheme=gcash;package=com.globe.gcash.android;end'; } catch(e) {}
    } else {
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        document.body.appendChild(iframe);
        try { iframe.src = 'gcash://'; } catch(e) {}
        setTimeout(() => {
            if (!document.hidden) { try { window.location.href = 'gcash://'; } catch(e) {} }
        }, 150);
        setTimeout(() => { try { document.body.removeChild(iframe); } catch(e) {} }, 4000);
    }
}

// --- PREMIUM & PAYMENT SYSTEM (AUTO-UNLOCK) ---
function loadPremiumStatus() {
    fetch('/api/premium/status')
        .then(res => res.json())
        .then(data => {
            const wasPremium = isPremium;
            isPremium = data.is_premium;
            if (currentUser) currentUser.premium_expiry = data.expiry_date;
            updatePremiumUI();
            if (isPremium && !wasPremium) loadBudget();
            if (isPremium) {
                document.getElementById('premiumInactive').style.display = 'none';
                document.getElementById('premiumActive').style.display = 'block';
                const exp = data.expiry_date ? data.expiry_date.replace(' ', 'T') : null;
                const expText = exp ? new Date(exp).toLocaleDateString('en-PH', {year:'numeric', month:'long', day:'numeric'}) : '--';
                document.getElementById('premiumExpiryText').textContent = 'Premium Activated — Valid until ' + expText;
                document.getElementById('premiumCountdown').innerHTML = 'Your Premium expires in: <strong>' + data.days_left + ' days</strong>';
                const payCard = document.getElementById('payCard');
                if (payCard) payCard.style.display = 'none';
            } else {
                document.getElementById('premiumInactive').style.display = 'block';
                document.getElementById('premiumActive').style.display = 'none';
                const payCard = document.getElementById('payCard');
                if (payCard) payCard.style.display = 'block';
            }
        });
}

function generateReference() {
    fetch('/api/premium/request', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            if (!data.success) return;
            referenceId = data.reference_id;
            document.getElementById('refIdDisplay').value = referenceId;
            document.getElementById('gcNumber').textContent = data.gcash_number;
            document.getElementById('gcName').textContent = data.gcash_name;
            const st = document.getElementById('paymentStatusText');
            st.textContent = `Send ₱${data.amount} via GCash. Ref: ${data.reference_id}`;
            st.style.color = 'var(--success)';
        });
}

function submitPaymentConfirmation() {
    const refVal = document.getElementById('refIdDisplay').value.trim();
    if (!refVal) { alert('Please wait for your Reference ID to load, then try again.'); return; }
    fetch('/api/premium/confirm-payment', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({reference_id: refVal})
    })
    .then(res => res.json())
    .then(data => {
        const st = document.getElementById('paymentStatusText');
        if (data.success && data.activated) {
            // === INSTANT AUTO-UNLOCK ===
            isPremium = true;
            if (currentUser) currentUser.premium_expiry = data.expiry_date;
            updatePremiumUI();
            loadBudget(); // unlock Budget Tracker agad
            const exp = data.expiry_date ? data.expiry_date.replace(' ', 'T') : null;
            const expText = exp ? new Date(exp).toLocaleDateString('en-PH', {year:'numeric', month:'long', day:'numeric'}) : '--';
            document.getElementById('premiumInactive').style.display = 'none';
            document.getElementById('premiumActive').style.display = 'block';
            document.getElementById('premiumExpiryText').textContent = 'Premium Activated — Valid until ' + expText;
            document.getElementById('premiumCountdown').innerHTML = 'Your Premium expires in: <strong>' + (data.days_left || 30) + ' days</strong>';
            const payCard = document.getElementById('payCard');
            if (payCard) payCard.style.display = 'none';
            st.textContent = '✅ Premium Activated! All features unlocked.';
            st.style.color = 'var(--success)';
            loadPremiumStatus(); // i-verify mula sa server
        } else if (data.success) {
            st.textContent = '✅ ' + (data.message || 'Payment submitted!');
            st.style.color = 'var(--success)';
            loadPremiumStatus();
        } else {
            st.textContent = '❌ ' + (data.error || 'Something went wrong.');
            st.style.color = 'var(--danger)';
        }
    })
    .catch(() => {
        const st = document.getElementById('paymentStatusText');
        st.textContent = '❌ Network error. Please try again.';
        st.style.color = 'var(--danger)';
    });
}
</script>
</body>
</html>
'''

# ==================== RUN APP ====================
init_db()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
