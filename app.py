from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import bcrypt
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_college_project' # Required for sessions

# Initialize Database with two tables
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Table 1: Users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL
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
    conn.commit()
    conn.close()

init_db()

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
    
    # Save the mood to the database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO mood_logs (username, mood, timestamp) VALUES (?, ?, ?)', 
                   (username, mood_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    # IMPORTANT: Pass username here so the dashboard can greet the user
    return render_template(f'index_{mood_type}.html', username=username)

@app.route('/history')
def history():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    username = session['user']
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Fetch mood logs for the logged-in user
    cursor.execute('SELECT mood, timestamp FROM mood_logs WHERE username = ? ORDER BY timestamp DESC', (username,))
    user_logs = cursor.fetchall()
    
    # --- INNOVATION: Calculate Top Mood for Insights ---
    mood_counts = {}
    for mood, time in user_logs:
        mood_counts[mood] = mood_counts.get(mood, 0) + 1
    
    # Get the most frequent mood string, or "None" if empty
    top_mood = max(mood_counts, key=mood_counts.get) if mood_counts else "New User"
    
    conn.close()
    return render_template('history.html', logs=user_logs, username=username, top_mood=top_mood)

# --- API ROUTES ---

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
    session.clear() # Better than session.pop for a full logout
    return redirect(url_for('index'))

# 1. Route to open the AI page
@app.route('/ai-solace')
def ai_page():
    if 'user' not in session:
        return redirect(url_for('index')) # Redirect to login if not logged in
    return render_template('ai_chat.html', username=session['user'])

# 2. Route to process the AI messages
@app.route('/get_ai_response', methods=['POST'])
def get_ai_response():
    data = request.get_json()
    user_msg = data.get('message', '').lower()

    # --- Psychology-Based Logic ---
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