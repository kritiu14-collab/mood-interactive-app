from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_college_project' 

# --- DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user'
    )''')
    
    # Mood logs
    cursor.execute('''CREATE TABLE IF NOT EXISTS mood_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, mood TEXT, timestamp DATETIME
    )''')
    
    # Journals
    cursor.execute('''CREATE TABLE IF NOT EXISTS journals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL, date TEXT NOT NULL, title TEXT,
        mood TEXT, morning TEXT, evening TEXT, night TEXT
    )''')

    # FINALIZED Tasks Table (Matches the new UI)
    cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        task_date TEXT,
        task_time TEXT,
        task_type TEXT, 
        priority TEXT, 
        reminder_enabled INTEGER DEFAULT 0,
        reminder_time TEXT,
        status INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

init_db()

# --- EMAIL REMINDER LOGIC ---
def check_reminders():
    with app.app_context():
        now_date = datetime.now().strftime('%Y-%m-%d')
        now_time = datetime.now().strftime('%H:%M')
        
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Join with users to get the email address
        cursor.execute("""
            SELECT t.*, u.email FROM tasks t 
            JOIN users u ON t.username = u.username 
            WHERE t.reminder_enabled = 1 AND t.status = 0 
            AND t.task_date = ? AND t.reminder_time = ?
        """, (now_date, now_time))
        
        reminders = cursor.fetchall()
        for r in reminders:
            send_solace_reminder(r['email'], r['title'], r['reminder_time'], r['task_date'])
        
        conn.close()

def send_solace_reminder(target_email, task_name, task_time, task_date):
    msg = EmailMessage()
    msg.set_content(f"Hello from Solace!\n\nReminder for your task: '{task_name}'\nScheduled for: {task_date} at {task_time}.\n\nStay productive!")
    msg['Subject'] = '✨ Solace Task Reminder'
    msg['From'] = "solacemoodinteractive@gmail.com"
    msg['To'] = target_email
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login("solacemoodinteractive@gmail.com", "hinx ccwp ewer baty") 
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Email Error: {e}")

# Background Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_reminders, trigger="interval", seconds=60)
scheduler.start()

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/todo')
def todo_page():
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('todo.html')

@app.route('/get_tasks')
def get_tasks():
    if 'user' not in session: return jsonify([])
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Fetch all tasks for the user
    cursor.execute("SELECT * FROM tasks WHERE username = ? ORDER BY status ASC, task_date ASC", (session['user'],))
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(tasks)

@app.route('/add_task', methods=['POST'])
def add_task():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    if request.is_json:
        data = request.json
        title = data.get('title')
        description = data.get('description', '')
        task_date = data.get('task_date')
        task_time = data.get('reminder_time') # Using reminder time as task time
        task_type = data.get('task_type', 'Daily')
        priority = data.get('priority', 'Medium')
        reminder_enabled = 1 if data.get('reminder_enabled') else 0
        reminder_time = data.get('reminder_time')
    else:
        title = request.form.get('task')
        description = ""
        task_date = request.form.get('date')
        task_time = request.form.get('time')
        task_type = request.form.get('task_type', 'Daily')
        priority = "Medium"
        reminder_enabled = 1 if request.form.get('reminder_enabled') else 0
        reminder_time = request.form.get('reminder_time')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks (username, title, description, task_date, task_time, task_type, priority, reminder_enabled, reminder_time, status) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (session['user'], title, description, task_date, task_time, task_type, priority, reminder_enabled, reminder_time))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Task added"}), 201

@app.route('/toggle_task/<int:task_id>', methods=['PUT', 'GET'])
def toggle_task(task_id):
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Flips status between 0 and 1
    cursor.execute("UPDATE tasks SET status = 1 - status WHERE id = ? AND username = ?", (task_id, session['user']))
    conn.commit()
    conn.close()
    return jsonify({"message": "Status updated"})

@app.route('/delete_task/<int:task_id>', methods=['DELETE', 'GET'])
def delete_task(task_id):
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ? AND username = ?", (task_id, session['user']))
    conn.commit()
    conn.close()
    return jsonify({"message": "Deleted"})

# --- AUTH ROUTES ---

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
    user = cursor.fetchone()
    conn.close()
    if user:
        session['user'] = username
        return jsonify({"message": "Login successful"}), 200
    return jsonify({"error": "Invalid username or password"}), 401

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, password))
        conn.commit()
        conn.close()
        return jsonify({"message": "User created"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 400

@app.route('/logout')
def logout():
    session.clear() 
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)