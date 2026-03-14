from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import bcrypt
import smtplib
from email.message import EmailMessage
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_college_project' 

# Initialize Database with updated schema
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Table 1: Users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    ''')
    
    # Table 2: Mood Logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mood_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            mood TEXT,
            timestamp DATETIME
        )
    ''')
    
    # Table 3: To-Do List (Updated with task_time)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            task_text TEXT,
            task_time TEXT,
            status TEXT DEFAULT 'Pending'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- EMAIL REMINDER FUNCTION ---
def send_solace_reminder(target_email, task_name, task_time):
    msg = EmailMessage()
    # Updated content to include the time
    msg.set_content(f"Hello from Solace!\n\nThis is a friendly reminder for your task: '{task_name}' scheduled for {task_time}.\n\nStay focused, you've got this!")
    msg['Subject'] = '✨ Solace Task Reminder'
    msg['From'] = "solacemoodinteractive@gmail.com"
    msg['To'] = target_email

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        # Using the App Password you provided
        server.login("solacemoodinteractive@gmail.com", "hinx ccwp ewer baty") 
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# --- PAGE ROUTES ---

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

# --- TO-DO LIST ROUTES (UPDATED) ---

@app.route('/todo')
def todo_page():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Fetching task_text and task_time
    cursor.execute("SELECT id, task_text, task_time FROM tasks WHERE username = ?", (session['user'],))
    user_tasks = cursor.fetchall()
    conn.close()
    return render_template('todo.html', tasks=user_tasks, username=session['user'])

@app.route('/add_task', methods=['POST'])
def add_task():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    task_text = request.form.get('task')
    task_time = request.form.get('time') # Capturing the time from the UI
    send_email = request.form.get('send_email') 
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (username, task_text, task_time) VALUES (?, ?, ?)", 
                   (session['user'], task_text, task_time))
    conn.commit()

    if send_email:
        cursor.execute("SELECT email FROM users WHERE username = ?", (session['user'],))
        user_data = cursor.fetchone()
        if user_data:
            # Passing time to the email function
            send_solace_reminder(user_data[0], task_text, task_time)

    conn.close()
    return redirect(url_for('todo_page'))

@app.route('/delete_task/<int:task_id>')
def delete_task(task_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ? AND username = ?", (task_id, session['user']))
    conn.commit()
    conn.close()
    return redirect(url_for('todo_page'))

# --- ADMIN ROUTE ---

@app.route('/admin')
def admin_page():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, role FROM users')
    all_users = cursor.fetchall()
    conn.close()
    return render_template('admin.html', users=all_users)

# --- HISTORY & AI ROUTES ---

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

if __name__ == '__main__':
    app.run(debug=True)