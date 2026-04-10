from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import sqlite3
import bcrypt
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_college_project'

# Initialize Database with three tables (added admin fields)
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Table 1: Users (ADDED is_admin column)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    # Table 2: Mood Logs (unchanged)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mood_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            mood TEXT,
            timestamp DATETIME
        )
    ''')
    
    # Table 3: Tasks (NEW for admin panel)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            user_id INTEGER,
            created_at DATETIME
        )
    ''')
    
    # Create default admin user
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        hashed = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode('utf-8')
        cursor.execute("INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
                      ('admin', 'admin@solace.com', hashed, 1))
    
    conn.commit()
    conn.close()

init_db()

# Helper function: check if user is admin
def is_admin(username):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1

# --- YOUR EXISTING ROUTES (UNCHANGED) ---
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/tracker')
def tracker_page():
    if 'user' in session:
        return render_template('tracker.html', username=session['user'])
    return redirect(url_for('index'))

@app.route('/mood/<mood_type>')
def set_mood(mood_type):
    if 'user' not in session:
        return redirect(url_for('index'))
    
    username = session['user']
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO mood_logs (username, mood, timestamp) VALUES (?, ?, ?)', 
                   (username, mood_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    return render_template(f'index_{mood_type}.html', username=username)

@app.route('/history')
def history():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    username = session['user']
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT mood, timestamp FROM mood_logs WHERE username = ? ORDER BY timestamp DESC', (username,))
    user_logs = cursor.fetchall()
    
    mood_counts = {}
    for mood, time in user_logs:
        mood_counts[mood] = mood_counts.get(mood, 0) + 1
    
    top_mood = max(mood_counts, key=mood_counts.get) if mood_counts else "New User"
    
    conn.close()
    return render_template('history.html', logs=user_logs, username=username, top_mood=top_mood)

# --- YOUR EXISTING API ROUTES (UNCHANGED) ---
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT password FROM users WHERE username = ?', (data['username'],))
    user = cursor.fetchone()
    conn.close()

    if user and bcrypt.checkpw(data['password'].encode('utf-8'), user[0]):
        session['user'] = data['username']
        return jsonify({"message": "Login successful"}), 200
    
    return jsonify({"error": "Invalid username or password"}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/ai-solace')
def ai_page():
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('ai_chat.html', username=session['user'])

@app.route('/get_ai_response', methods=['POST'])
def get_ai_response():
    data = request.get_json()
    user_msg = data.get('message', '').lower()

    if "always" in user_msg or "never" in user_msg:
        reply = "<b>Cognitive Check:</b> 'Always' and 'Never' are often over-generalizations. Let's look at the facts: When was the last time this <i>wasn't</i> true?"
    elif "fail" in user_msg or "stupid" in user_msg:
        reply = "<b>Identity vs. Action:</b> You might have failed at a task, but that doesn't make you a 'failure.' What's one thing you learned from this experience?"
    elif "no one" in user_msg or "everyone" in user_msg:
        reply = "<b>Reframing Assumption:</b> You're using 'Universal Quantifiers.' It's unlikely that everyone feels that way. Can you name one person who might have a different perspective?"
    else:
        reply = "That's a valid thing to feel. However, let's challenge the narrative your overthinking is creating. If you were viewing this from a year in the future, how important would this moment be?"

    return jsonify({"reply": reply})

# --- NEW ADMIN ROUTES ---
@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or not is_admin(session['user']):
        flash('Admin access required!')
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Dashboard stats
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM mood_logs')
    total_moods = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tasks')
    total_tasks = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM tasks WHERE status="done"')
    done_tasks = cursor.fetchone()[0]
    
    # Recent activity
    cursor.execute('SELECT username, mood, timestamp FROM mood_logs ORDER BY timestamp DESC LIMIT 5')
    recent_moods = cursor.fetchall()
    
    cursor.execute('SELECT title, status FROM tasks ORDER BY created_at DESC LIMIT 5')
    recent_tasks = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin/dashboard.html', 
                         total_users=total_users, total_moods=total_moods,
                         total_tasks=total_tasks, done_tasks=done_tasks,
                         recent_moods=recent_moods, recent_tasks=recent_tasks)

@app.route('/admin/tasks')
def admin_tasks():
    if 'user' not in session or not is_admin(session['user']):
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks ORDER BY created_at DESC')
    tasks = cursor.fetchall()
    conn.close()
    
    return render_template('admin/tasks.html', tasks=tasks)

@app.route('/admin/tasks/new', methods=['POST'])
def new_task():
    if 'user' not in session or not is_admin(session['user']):
        return redirect(url_for('index'))
    
    title = request.form['title']
    status = request.form.get('status', 'pending')
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO tasks (title, status, user_id, created_at) VALUES (?, ?, ?, ?)',
                  (title, status, session['user'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    flash('Task created!')
    return redirect(url_for('admin_tasks'))

@app.route('/admin/tasks/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    if 'user' not in session or not is_admin(session['user']):
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    
    flash('Task deleted!')
    return redirect(url_for('admin_tasks'))

if __name__ == '__main__':
    app.run(debug=True)