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

# ✅ NGAYON: iisa na lang ang number — tugma na sa QR mo (+63 970 456 ••••, JE***N V.)
#    ⚠️ PALITAN LANG ANG "XXXX" sa GCASH_NUMBER ng huling 4 digits ng number mo.
GCASH_NUMBER = "0970-456-XXXX"   # ⚠️ PALITAN ANG "XXXX" ng HULING 4 DIGITS ng number mo (nasa QR: +63 970 456 ••••)
GCASH_NAME = "JE***N V."         # Pangalan na naka-register sa QR (JE***N V.)

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
                        Number: <span id="gcNumber" style="font-weight:600;">0970-456-XXXX</span> · Name: <span id="gcName">--</span><br>
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
