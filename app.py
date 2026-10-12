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

                <!-- ========== GCASH PAYMENT: QR + Go to GCash button ========== -->
                <div class="card" id="payCard">
                    <h3>💳 Pay via GCash <span style="font-size:13px; color:var(--success);">₱50.00 auto-set</span></h3>

                    <!-- QR lang mismo -->
                    <div class="qr-code" style="width:240px;">
                        <img id="gcashQrImg" src="data:image/jpeg;base64,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" alt="GCash QR — ₱50.00" style="width:100%; display:block;">
                    </div>
                    <p class="qr-hint">
                        I-scan gamit ang GCash app → <strong>Scan QR</strong>.<br>
                        Ang <strong>₱50.00</strong> ay naka-set na sa QR — hindi na kailangang i-type.
                    </p>

                    <!-- Go to GCash button -->
                    <button class="btn btn-primary" style="margin-top:14px;" onclick="openGcashApp()">📱 Go to GCash</button>
                    <p class="qr-hint" style="margin-top:10px;">
                        O manu-manong mag-send: <strong>Send Money → Express Send</strong><br>
                        Number: <span id="gcNumber" style="font-weight:600;">0930-132-9437</span> · Name: <span id="gcName">--</span><br>
                        Amount: <strong>₱50.00</strong> (fixed)
                        <br><button class="btn btn-outline btn-sm" style="margin-top:8px; padding:6px 14px;" onclick="copyGcashNumber()">📋 Copy Number</button>
                    </p>

                    <!-- Reference ID + confirm -->
                    <ol style="font-size: 13px; line-height: 1.7; color: var(--muted); padding-left: 20px; margin-top: 16px;">
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
    // Auto-copy ang number sa clipboard, subukang buksan ang GCash app.
    // Ang ₱50.00 ay fixed — ipinapaalala sa user.
    const raw = (document.getElementById('gcNumber')?.textContent || '').replace(/-/g, '').trim();
    if (raw) {
        try { navigator.clipboard && navigator.clipboard.writeText(raw); } catch(e) {}
    }
    try {
        window.location.href = 'gcash://';
    } catch(e) {}
    setTimeout(() => {
        if (!document.hidden) {
            alert('📱 GCash — ₱50.00 (fixed)\n\n' +
                  (raw ? '✅ Number nakopy na: ' + raw + '\n' : '') +
                  '1. Sa GCash: Send Money → Express Send\n' +
                  '2. I-paste ang number (kung hindi pa)\n' +
                  '3. Amount: ₱50.00 (eksakto — huwag palitan)\n' +
                  '4. Ilagay ang Reference ID sa message');
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
