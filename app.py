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

# ⚠️ PAKITANDA: Ang QR image mo ay naka-register sa number na 0970-456-xxxx (JE***N V.)
#    I-update ang GCASH_NUMBER sa ibaba para tumugma sa tunay mong GCash number.
GCASH_NUMBER = "0930-132-9437"   # <-- PALITAN MO ITO sa number na nasa QR mo (0970-...)
GCASH_NAME = "Pangalan Mo Dito"  # <-- Ilagay ang pangalang nakarehistro sa GCash mo

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")  # Para sa pag-activate ng Premium (/api/premium/approve)

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
        # FIX: hindi na auto-login. Babalik muna sa Login page ang user.
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

# ==================== PREMIUM & PAYMENT SYSTEM ====================
@app.route('/api/premium/request', methods=['POST'])
def request_premium():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    # FIX: kung may pending/waiting na reference ang user, ibalik ito (hindi gumagawa ng bago tuwing bubuksan ang page)
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
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    reference_id = data.get('reference_id', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE reference_id = ? AND user_id = ?",
                (reference_id, session['user_id']))
    payment = cur.fetchone()
    if not payment:
        conn.close()
        return jsonify({'success': False, 'error': 'Reference ID not found'})
    if payment['status'] == 'activated':
        conn.close()
        return jsonify({'success': True, 'message': 'Already activated'})
    cur.execute("UPDATE payments SET status = 'waiting' WHERE reference_id = ?", (reference_id,))
    conn.commit()
    conn.close()
    return jsonify({
        'success': True,
        'message': 'Payment submitted! Please wait for admin confirmation (usually within 24 hours).'
    })

# Tawagin ito ng admin (o ng payment webhook) kapag nakumpirma na ang bayad:
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
            start = old  # renewal: dagdag sa natitirang araw
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
/* Auth Pages */
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
/* Main Layout */
.header {background: var(--card); padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: var(--shadow); position: sticky; top: 0; z-index: 100;}
.header h2 {font-size: 18px; font-weight: 600;}
.menu-btn {background: none; border: none; font-size: 24px; color: var(--text); cursor: pointer;}
/* Sidebar */
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
/* Content */
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
/* Bottom Nav */
.bottom-nav {position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); max-width: 480px; width: 100%; background: var(--card); display: flex; justify-content: space-around; padding: 10px 0; box-shadow: 0 -2px 10px rgba(0,0,0,0.05); z-index: 150;}
.nav-item {display: flex; flex-direction: column; align-items: center; gap: 2px; color: var(--muted); text-decoration: none; font-size: 11px; cursor: pointer;}
.nav-item.active {color: var(--primary);}
.nav-item span {font-size: 20px;}
/* Modal */
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
/* Payment tabs */
.pay-tabs {display: flex; gap: 8px; margin-bottom: 16px;}
.pay-tab {flex: 1; padding: 10px 6px; border: 1px solid var(--border); background: transparent; color: var(--muted); border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s;}
.pay-tab.active {background: var(--gradient); color: white; border-color: transparent;}
.pay-panel {display: none;}
.pay-panel.active {display: block; animation: fadeIn 0.25s ease;}
.gcash-num-box {text-align: center; padding: 16px; background: rgba(59, 130, 246, 0.08); border: 1px dashed var(--secondary); border-radius: 12px; margin-bottom: 12px;}
.gcash-num-box .num-label {font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px;}
.gcash-num-box .num-value {font-size: 24px; font-weight: 700; letter-spacing: 1px; margin: 4px 0; color: var(--text);}
.gcash-num-box .num-name {font-size: 13px; color: var(--muted);}
.gcash-num-box .num-amount {font-size: 15px; font-weight: 700; color: var(--success); margin-top: 6px;}
.pay-actions-row {display: flex; gap: 8px;}
.pay-actions-row button {flex: 1; padding: 10px; font-size: 13px;}
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
        <!-- Header -->
        <div class="header">
            <button class="menu-btn" onclick="toggleSidebar()">☰</button>
            <h2 id="pageTitle">Dashboard</h2>
            <span></span>
        </div>
        <!-- Sidebar Overlay -->
        <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
        <!-- Sidebar -->
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
        <!-- Content -->
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

                <!-- ========== GCASH PAYMENT CARD (two options) ========== -->
                <div class="card" id="payCard">
                    <h3>💳 Pay via GCash <span style="font-size:13px; color:var(--success);">₱50.00 auto-set</span></h3>

                    <!-- Tab switcher -->
                    <div class="pay-tabs">
                        <button class="pay-tab active" id="tabQr" onclick="switchPayTab('qr')">📷 Scan QR Code</button>
                        <button class="pay-tab" id="tabNum" onclick="switchPayTab('num')">📱 Send via Number</button>
                    </div>

                    <!-- OPTION 1: Scan QR (tunay mong GCash QR, naka-embed, ₱50 pre-set) -->
                    <div class="pay-panel active" id="payQrPanel">
                        <div class="qr-code">
                            <img id="gcashQrImg" src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAOSAeADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDzSiiiv6FPyIKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACjFJkUuCegoHYDx3p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ACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAP/Z" alt="GCash QR — ₱50.00">
                        </div>
                        <p class="qr-hint">
                            Buksan ang GCash app → <strong>Scan QR</strong> → itapat sa code sa itaas.<br>
                            Ang <strong>₱50.00</strong> ay naka-set na sa QR — hindi na kailangang i-type.
                        </p>
                    </div>

                    <!-- OPTION 2: Send via GCash Number / Open GCash App -->
                    <div class="pay-panel" id="payNumPanel">
                        <div class="gcash-num-box">
                            <div class="num-label">GCash Number</div>
                            <div class="num-value" id="gcNumberBig">0930-132-9437</div>
                            <div class="num-name">Name: <span id="gcNameBig">--</span></div>
                            <div class="num-amount">Amount: ₱50.00 (fixed)</div>
                        </div>
                        <div class="pay-actions-row">
                            <button class="btn btn-outline" onclick="copyGcashNumber()">📋 Copy Number</button>
                            <button class="btn btn-primary" onclick="openGcashApp()">📱 Open GCash App</button>
                        </div>
                        <p class="qr-hint" style="margin-top:12px;">
                            Sa GCash app: <strong>Send Money → Express Send</strong><br>
                            i-paste ang number → ilagay ang eksaktong <strong>₱50.00</strong>
                        </p>
                    </div>

                    <!-- Common: Reference ID + confirm -->
                    <ol style="font-size: 13px; line-height: 1.7; color: var(--muted); padding-left: 20px; margin-top: 16px;">
                        <li>Pumili ng paraan: i-scan ang QR o mag-send via number</li>
                        <li>Mag-send ng eksaktong <strong>₱50.00</strong></li>
                        <li>Ilagay ang Reference ID sa message/note ng GCash</li>
                        <li>I-click ang "I Have Sent Payment"</li>
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
        // Auto-generate ang Reference ID (₱50 auto-set) kapag hindi pa Premium
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
        expiryText.textContent = `Valid until: ${currentUser.premium_expiry ? new Date(currentUser.premium_expiry).toLocaleDateString('en-PH') : '--'}`;
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

// Helper para ma-reset nang tama ang mga form pagkatapos mag-save
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
            // Pagkatapos mag-register, bumalik muna sa Login page
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

// ========== PAYMENT TABS (Scan QR / Send via Number) ==========
function switchPayTab(tab) {
    document.getElementById('tabQr').classList.toggle('active', tab === 'qr');
    document.getElementById('tabNum').classList.toggle('active', tab === 'num');
    document.getElementById('payQrPanel').classList.toggle('active', tab === 'qr');
    document.getElementById('payNumPanel').classList.toggle('active', tab === 'num');
}

function copyGcashNumber() {
    const raw = (document.getElementById('gcNumber')?.textContent || document.getElementById('gcNumberBig')?.textContent || '').replace(/-/g, '').trim();
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
    // Best-effort deep link. Walang public GCash deep link na nag pre-fill ng amount/number,
    // kaya bubuksan lang ang app; nandoon na ang copy button para sa number.
    const raw = (document.getElementById('gcNumber')?.textContent || document.getElementById('gcNumberBig')?.textContent || '').replace(/-/g, '').trim();
    try {
        window.location.href = 'gcash://';
    } catch(e) {}
    setTimeout(() => {
        if (!document.hidden) {
            alert('📱 Kung hindi bumukas ang GCash app:\n\n' +
                  '1. Buksan nang manual ang GCash\n' +
                  '2. Send Money → Express Send\n' +
                  '3. Number: ' + (raw || '(tingnan sa app)') + '\n' +
                  '4. Amount: ₱50.00 (eksakto)\n' +
                  '5. Ilagay ang Reference ID sa message');
        }
    }, 1500);
}

// --- PREMIUM & PAYMENT SYSTEM ---
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
                document.getElementById('premiumExpiryText').textContent = `Valid until: ${data.expiry_date ? new Date(data.expiry_date).toLocaleDateString('en-PH') : '--'}`;
                document.getElementById('premiumCountdown').innerHTML = `Your Premium expires in: <strong>${data.days_left} days</strong>`;
            } else {
                document.getElementById('premiumInactive').style.display = 'block';
                document.getElementById('premiumActive').style.display = 'none';
            }
        });
}

// Awtomatikong ginagawa ang Reference ID at ipinapakita ang GCash number at pangalan (₱50 auto-set)
function generateReference() {
    fetch('/api/premium/request', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            if (!data.success) return;
            referenceId = data.reference_id;
            document.getElementById('refIdDisplay').value = referenceId;
            document.getElementById('gcNumber').textContent = data.gcash_number;
            document.getElementById('gcName').textContent = data.gcash_name;
            // Set din sa Send-via-Number panel
            const gcBig = document.getElementById('gcNumberBig');
            if (gcBig) gcBig.textContent = data.gcash_number;
            const gcNameBig = document.getElementById('gcNameBig');
            if (gcNameBig) gcNameBig.textContent = data.gcash_name;
            const st = document.getElementById('paymentStatusText');
            st.textContent = `Send ₱${data.amount} via GCash. Ref: ${data.reference_id}`;
            st.style.color = 'var(--success)';
        });
}

function submitPaymentConfirmation() {
    const refVal = document.getElementById('refIdDisplay').value.trim();
    if (!refVal) {
        alert('Please wait for your Reference ID to load, then try again.');
        return;
    }
    fetch('/api/premium/confirm-payment', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({reference_id: refVal})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            document.getElementById('paymentStatusText').textContent = '✅ Payment submitted! Waiting for Admin approval...';
            document.getElementById('paymentStatusText').style.color = 'var(--success)';
        } else {
            document.getElementById('paymentStatusText').textContent = '❌ ' + data.error;
            document.getElementById('paymentStatusText').style.color = 'var(--danger)';
        }
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
