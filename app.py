from __future__ import annotations

import os
import uuid
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

import bcrypt
import requests
from flask import (
    Flask, flash, jsonify, redirect, render_template,
    request, session, url_for
)
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "solace-dev-secret")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MAIL_HOST      = os.getenv("MAIL_HOST", "smtp.gmail.com")
MAIL_PORT      = int(os.getenv("MAIL_PORT", 587))
MAIL_USER      = os.getenv("MAIL_USER", "")
MAIL_PASSWORD  = os.getenv("MAIL_PASSWORD", "")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                email      TEXT NOT NULL,
                password   TEXT NOT NULL,
                is_admin   INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS mood_logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL REFERENCES users(id),
                mood      TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS journals (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                date       TEXT,
                title      TEXT,
                mood       TEXT,
                morning    TEXT,
                evening    TEXT,
                night      TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id),
                title       TEXT NOT NULL,
                description TEXT,
                task_date   TEXT,
                task_time   TEXT,
                task_type   TEXT DEFAULT 'daily',
                status      INTEGER DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT,
                user_id      INTEGER REFERENCES users(id),
                user_message TEXT,
                ai_response  TEXT,
                timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS otp_store (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT NOT NULL,
                otp        TEXT NOT NULL,
                expires_at DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS posts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                body       TEXT NOT NULL,
                author_id  INTEGER REFERENCES users(id),
                published  INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS admin_tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                status      TEXT DEFAULT 'pending',
                created_by  INTEGER REFERENCES users(id),
                assigned_to INTEGER REFERENCES users(id),
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        exists = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not exists:
            hashed = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
                ("admin", "admin@solace.com", hashed, 1),
            )


init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login_required(f: Any) -> Any:
    @wraps(f)
    def dec(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return dec


def admin_required(f: Any) -> Any:
    @wraps(f)
    def dec(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session or not session.get("is_admin"):
            flash("Admin access required.")
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return dec


def send_otp_email(to_email: str, otp: str) -> bool:
    try:
        msg = MIMEText(
            f"Your Solace password reset OTP is: {otp}\n\nExpires in 10 minutes.", "plain"
        )
        msg["Subject"] = "Solace – Password Reset OTP"
        msg["From"]    = MAIL_USER
        msg["To"]      = to_email
        with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as s:
            s.starttls()
            s.login(MAIL_USER, MAIL_PASSWORD)
            s.sendmail(MAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Mail error: {e}")
        return False


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.route("/")
def home() -> Any:
    return render_template("home.html")


@app.route("/auth")
def login_page() -> Any:
    if "user_id" in session:
        return redirect(url_for("tracker"))
    return render_template("login.html")


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------

@app.route("/signup", methods=["POST"])
def signup() -> Any:
    data     = request.json or {}
    username = data.get("username", "").strip()
    email    = data.get("email", "").strip()
    password = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"error": "All fields are required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password) VALUES (?,?,?)",
                (username, email, hashed),
            )
        return jsonify({"message": "Account created! Please log in."}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists. Please choose another."}), 409


@app.route("/login", methods=["POST"])
def login() -> Any:
    data     = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role     = data.get("role", "user")

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    if not user or not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error": "Invalid username or password."}), 401

    if role == "admin" and not user["is_admin"]:
        return jsonify({"error": "You do not have admin privileges."}), 403

    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])

    if user["is_admin"] and role == "admin":
        return jsonify({"redirect": url_for("admin_dashboard")}), 200
    return jsonify({"redirect": url_for("tracker")}), 200


@app.route("/logout")
def logout() -> Any:
    session.clear()
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# OTP Password Reset
# ---------------------------------------------------------------------------

@app.route("/request-otp", methods=["POST"])
def request_otp() -> Any:
    data  = request.json or {}
    uname = data.get("username", "").strip()

    with get_db() as conn:
        user = conn.execute("SELECT email FROM users WHERE username=?", (uname,)).fetchone()

    if not user:
        return jsonify({"error": "No account found with that username."}), 404

    otp     = str(random.randint(100000, 999999))
    expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    email   = user["email"]

    with get_db() as conn:
        conn.execute("DELETE FROM otp_store WHERE email=?", (email,))
        conn.execute("INSERT INTO otp_store (email, otp, expires_at) VALUES (?,?,?)",
                     (email, otp, expires))

    ok = send_otp_email(email, otp)
    masked = email[:3] + "***" + email[email.index("@"):]
    if not ok:
        # Dev fallback — remove before going live
        return jsonify({"message": f"(Dev) OTP is {otp} — email failed.", "email": masked}), 200
    return jsonify({"message": f"OTP sent to {masked}"}), 200


@app.route("/verify-otp", methods=["POST"])
def verify_otp() -> Any:
    data     = request.json or {}
    username = data.get("username", "").strip()
    otp      = data.get("otp", "").strip()
    new_pass = data.get("new_password", "")

    if len(new_pass) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    with get_db() as conn:
        user = conn.execute("SELECT email FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            return jsonify({"error": "User not found."}), 404

        record = conn.execute(
            "SELECT * FROM otp_store WHERE email=? AND otp=?", (user["email"], otp)
        ).fetchone()

        if not record:
            return jsonify({"error": "Invalid OTP."}), 400
        if datetime.now() > datetime.strptime(record["expires_at"], "%Y-%m-%d %H:%M:%S"):
            conn.execute("DELETE FROM otp_store WHERE email=?", (user["email"],))
            return jsonify({"error": "OTP expired. Please request a new one."}), 400

        hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
        conn.execute("UPDATE users SET password=? WHERE username=?", (hashed, username))
        conn.execute("DELETE FROM otp_store WHERE email=?", (user["email"],))

    return jsonify({"message": "Password reset! Please log in."}), 200


# ---------------------------------------------------------------------------
# Mood tracker
# ---------------------------------------------------------------------------

@app.route("/tracker")
@login_required
def tracker() -> Any:
    return render_template("tracker.html", username=session["username"])


@app.route("/mood/<mood_type>")
@login_required
def set_mood(mood_type: str) -> Any:
    session["current_mood"] = mood_type
    with get_db() as conn:
        conn.execute("INSERT INTO mood_logs (user_id, mood) VALUES (?,?)",
                     (session["user_id"], mood_type))
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard() -> Any:
    mood = session.get("current_mood")
    if mood:
        return render_template(f"index_{mood}.html", username=session["username"])
    return redirect(url_for("tracker"))


@app.route("/history")
@login_required
def history() -> Any:
    with get_db() as conn:
        logs = conn.execute(
            "SELECT mood, timestamp FROM mood_logs WHERE user_id=? ORDER BY timestamp DESC",
            (session["user_id"],),
        ).fetchall()
    mood_counts: dict[str, int] = {}
    for r in logs:
        mood_counts[r["mood"]] = mood_counts.get(r["mood"], 0) + 1
    top_mood = max(mood_counts, key=mood_counts.get) if mood_counts else "New User"
    return render_template("history.html", logs=logs, username=session["username"], top_mood=top_mood)


# ---------------------------------------------------------------------------
# AI Chat
# ---------------------------------------------------------------------------

@app.route("/ai_chat")
@login_required
def ai_chat_page() -> Any:
    with get_db() as conn:
        history_heads = conn.execute(
            """SELECT session_id, user_message, MAX(timestamp) as ts
               FROM chat_history WHERE user_id=?
               GROUP BY session_id ORDER BY ts DESC""",
            (session["user_id"],),
        ).fetchall()
        active_messages: list = []
        if "active_chat_id" in session:
            active_messages = conn.execute(
                "SELECT * FROM chat_history WHERE session_id=? ORDER BY timestamp ASC",
                (session["active_chat_id"],),
            ).fetchall()
    return render_template(
        "ai_chat.html",
        chat_history=history_heads,
        active_messages=active_messages,
        username=session.get("username", "Friend"),
        current_mood=session.get("current_mood", "neutral"),
    )


@app.route("/new_chat")
@login_required
def new_chat() -> Any:
    session.pop("active_chat_id", None)
    return redirect(url_for("ai_chat_page"))


@app.route("/load_chat/<sid>")
@login_required
def load_chat(sid: str) -> Any:
    session["active_chat_id"] = sid
    return redirect(url_for("ai_chat_page"))


@app.route("/delete_chat/<sid>")
@login_required
def delete_chat(sid: str) -> Any:
    with get_db() as conn:
        conn.execute("DELETE FROM chat_history WHERE session_id=? AND user_id=?",
                     (sid, session["user_id"]))
    if session.get("active_chat_id") == sid:
        session.pop("active_chat_id", None)
    return redirect(url_for("ai_chat_page"))


@app.route("/get_ai_response", methods=["POST"])
@login_required
def get_ai_response() -> Any:
    data     = request.json or {}
    user_msg = data.get("message", "")
    mood     = session.get("current_mood", "neutral")

    if "active_chat_id" not in session:
        session["active_chat_id"] = str(uuid.uuid4())
    sid = session["active_chat_id"]

    if not GEMINI_API_KEY:
        return jsonify({"reply": "⚠️ Gemini API key is missing. Please add GEMINI_API_KEY to your .env file."}), 200

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )

    system_prompt = (
        f"You are Eva, a compassionate AI mental wellness companion built into Solace app. "
        f"The user is currently feeling '{mood}'. "
        f"Respond with empathy, warmth and gentle CBT techniques. "
        f"Keep responses concise (2-4 sentences). Never give medical advice. "
        f"Always validate the user's feelings first before offering perspective."
    )

    payload = {
        "contents": [
            {
                "parts": [{"text": f"{system_prompt}\n\nUser message: {user_msg}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 400,
        }
    }

    text = ""
    try:
        res      = requests.post(url, json=payload, timeout=30)
        res_json = res.json()

        # Print full response to terminal for debugging
        print(f"[Gemini] Status: {res.status_code}")
        print(f"[Gemini] Response: {res_json}")

        if res.status_code != 200:
            error_msg = res_json.get("error", {}).get("message", "Unknown API error")
            text = f"⚠️ API Error: {error_msg}"
        else:
            text = res_json["candidates"][0]["content"]["parts"][0]["text"]

    except requests.exceptions.Timeout:
        text = "Eva took too long to respond. Please try again."
    except requests.exceptions.ConnectionError:
        text = "Cannot reach Eva right now. Check your internet connection."
    except KeyError as e:
        print(f"[Gemini] KeyError: {e} — Full response: {res_json}")
        text = "Eva received an unexpected response. Please try again."
    except Exception as e:
        print(f"[Gemini] Unexpected error: {e}")
        text = f"Something went wrong: {str(e)}"

    with get_db() as conn:
        conn.execute(
            "INSERT INTO chat_history (session_id, user_id, user_message, ai_response) VALUES (?,?,?,?)",
            (sid, session["user_id"], user_msg, text),
        )
    return jsonify({"reply": text})


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

@app.route("/journal")
@login_required
def journal_page() -> Any:
    return render_template("journal.html", username=session["username"])


@app.route("/save_journal", methods=["POST"])
@login_required
def save_journal() -> Any:
    d = request.json or {}
    with get_db() as conn:
        conn.execute(
            "INSERT INTO journals (user_id, date, title, mood, morning, evening, night) VALUES (?,?,?,?,?,?,?)",
            (session["user_id"], d.get("date"), d.get("title"), d.get("mood"),
             d.get("morning"), d.get("evening"), d.get("night")),
        )
    return jsonify({"message": "Saved"}), 200


@app.route("/get_journals")
@login_required
def get_journals() -> Any:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM journals WHERE user_id=? ORDER BY date DESC", (session["user_id"],)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/delete_journal/<int:jid>")
@login_required
def delete_journal(jid: int) -> Any:
    with get_db() as conn:
        conn.execute("DELETE FROM journals WHERE id=? AND user_id=?", (jid, session["user_id"]))
    return jsonify({"message": "Deleted"}), 200


# ---------------------------------------------------------------------------
# To-Do
# ---------------------------------------------------------------------------

@app.route("/todo")
@login_required
def todo_page() -> Any:
    return render_template("todo.html", username=session["username"])


@app.route("/todo_data")
@login_required
def todo_data() -> Any:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC", (session["user_id"],)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/add_task", methods=["POST"])
@login_required
def add_task() -> Any:
    d = request.json or {}
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (user_id, title, description, task_date, task_time, task_type) VALUES (?,?,?,?,?,?)",
            (session["user_id"], d.get("title"), d.get("description", ""),
             d.get("date"), d.get("time"), d.get("type", "daily")),
        )
    return jsonify({"message": "Added"}), 201


@app.route("/toggle_task/<int:tid>", methods=["PUT"])
@login_required
def toggle_task(tid: int) -> Any:
    with get_db() as conn:
        t = conn.execute("SELECT status FROM tasks WHERE id=? AND user_id=?",
                         (tid, session["user_id"])).fetchone()
        if t:
            conn.execute("UPDATE tasks SET status=? WHERE id=?",
                         (0 if t["status"] else 1, tid))
    return jsonify({"message": "Toggled"}), 200


@app.route("/delete_task/<int:tid>", methods=["DELETE"])
@login_required
def delete_task_user(tid: int) -> Any:
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (tid, session["user_id"]))
    return jsonify({"message": "Deleted"}), 200


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------

@app.route("/music")
@login_required
def music_page() -> Any:
    mood = session.get("current_mood", "happy")
    return render_template("musicapp.html", username=session["username"], mood=mood)


@app.route("/exercises")
@login_required
def exercises_page() -> Any:
    mood = request.args.get("mood", session.get("current_mood", "happy"))
    return render_template("exercises.html", mood=mood, username=session["username"])


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
# ADMIN ROUTES — Admin only sees user data, no mood/task selection for admin
# ---------------------------------------------------------------------------

@app.route("/exercises")
@login_required
def exercises() -> Any:
    mood = session.get("current_mood", "")
    return render_template("exercises.html", mood=mood, username=session["username"])



    with get_db() as conn:
        total_users   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_moods   = conn.execute("SELECT COUNT(*) FROM mood_logs").fetchone()[0]
        total_journals= conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0]
        total_chats   = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
        total_posts   = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

        recent_users = conn.execute(
            "SELECT id, username, email, is_admin, created_at FROM users ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

        recent_moods = conn.execute("""
            SELECT u.username, ml.mood, ml.timestamp
            FROM mood_logs ml JOIN users u ON ml.user_id=u.id
            ORDER BY ml.timestamp DESC LIMIT 8
        """).fetchall()

        recent_chats = conn.execute("""
            SELECT u.username, ch.user_message, ch.ai_response, ch.timestamp
            FROM chat_history ch JOIN users u ON ch.user_id=u.id
            ORDER BY ch.timestamp DESC LIMIT 5
        """).fetchall()

    return render_template(
        "admin/dashboard.html",
        total_users=total_users, total_moods=total_moods,
        total_journals=total_journals, total_chats=total_chats,
        total_posts=total_posts,
        recent_users=recent_users, recent_moods=recent_moods,
        recent_chats=recent_chats,
    )


@app.route("/admin/users")
@admin_required
def admin_users() -> Any:
    with get_db() as conn:
        users = conn.execute("""
            SELECT u.id, u.username, u.email, u.is_admin, u.created_at,
                   COUNT(DISTINCT ml.id) AS mood_count,
                   COUNT(DISTINCT j.id)  AS journal_count,
                   COUNT(DISTINCT t.id)  AS task_count
            FROM users u
            LEFT JOIN mood_logs ml ON ml.user_id=u.id
            LEFT JOIN journals j   ON j.user_id=u.id
            LEFT JOIN tasks t      ON t.user_id=u.id
            GROUP BY u.id ORDER BY u.created_at DESC
        """).fetchall()
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/<int:uid>")
@admin_required
def admin_user_detail(uid: int) -> Any:
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            flash("User not found.")
            return redirect(url_for("admin_users"))
        moods    = conn.execute("SELECT mood, timestamp FROM mood_logs WHERE user_id=? ORDER BY timestamp DESC", (uid,)).fetchall()
        journals = conn.execute("SELECT date, title, mood FROM journals WHERE user_id=? ORDER BY date DESC", (uid,)).fetchall()
        tasks    = conn.execute("SELECT title, status, task_date FROM tasks WHERE user_id=? ORDER BY created_at DESC", (uid,)).fetchall()
        ai_chats = conn.execute("SELECT user_message, ai_response, timestamp FROM chat_history WHERE user_id=? ORDER BY timestamp DESC LIMIT 20", (uid,)).fetchall()
    mood_counts: dict[str, int] = {}
    for r in moods:
        mood_counts[r["mood"]] = mood_counts.get(r["mood"], 0) + 1
    return render_template("admin/user_detail.html",
                           user=user, moods=moods, mood_counts=mood_counts,
                           journals=journals, tasks=tasks, ai_chats=ai_chats)


@app.route("/admin/users/<int:uid>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(uid: int) -> Any:
    if uid == session["user_id"]:
        flash("Cannot change your own admin status.")
        return redirect(url_for("admin_users"))
    with get_db() as conn:
        u = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if u:
            conn.execute("UPDATE users SET is_admin=? WHERE id=?", (0 if u["is_admin"] else 1, uid))
    flash("Permission updated.")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@admin_required
def delete_user(uid: int) -> Any:
    if uid == session["user_id"]:
        flash("Cannot delete your own account.")
        return redirect(url_for("admin_users"))
    with get_db() as conn:
        for tbl in ["mood_logs", "journals", "tasks", "chat_history"]:
            conn.execute(f"DELETE FROM {tbl} WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
    flash("User deleted.")
    return redirect(url_for("admin_users"))


@app.route("/admin/chats")
@admin_required
def admin_chats() -> Any:
    """Admin can view all users' AI conversations with Eva."""
    uid_filter = request.args.get("user_id", "")
    with get_db() as conn:
        users = conn.execute(
            "SELECT id, username FROM users WHERE is_admin=0 ORDER BY username"
        ).fetchall()

        if uid_filter:
            chats = conn.execute("""
                SELECT ch.id, u.username, ch.user_message, ch.ai_response,
                       ch.session_id, ch.timestamp
                FROM chat_history ch JOIN users u ON ch.user_id=u.id
                WHERE ch.user_id=?
                ORDER BY ch.timestamp DESC
            """, (uid_filter,)).fetchall()
        else:
            chats = conn.execute("""
                SELECT ch.id, u.username, ch.user_message, ch.ai_response,
                       ch.session_id, ch.timestamp
                FROM chat_history ch JOIN users u ON ch.user_id=u.id
                ORDER BY ch.timestamp DESC LIMIT 50
            """).fetchall()

    return render_template(
        "admin/chats.html",
        chats=chats, users=users,
        selected_user=uid_filter,
    )



    with get_db() as conn:
        tasks = conn.execute("""
            SELECT t.*, u.username AS assignee
            FROM admin_tasks t LEFT JOIN users u ON t.assigned_to=u.id
            ORDER BY t.created_at DESC
        """).fetchall()
        users = conn.execute("SELECT id, username FROM users ORDER BY username").fetchall()
    return render_template("admin/tasks.html", tasks=tasks, users=users)


@app.route("/admin/tasks/new", methods=["POST"])
@admin_required
def new_admin_task() -> Any:
    title = request.form.get("title", "").strip()
    if not title:
        flash("Title required.")
        return redirect(url_for("admin_tasks"))
    with get_db() as conn:
        conn.execute(
            "INSERT INTO admin_tasks (title, description, status, created_by, assigned_to) VALUES (?,?,?,?,?)",
            (title, request.form.get("description", ""), request.form.get("status", "pending"),
             session["user_id"], request.form.get("assigned_to") or None),
        )
    flash("Task created.")
    return redirect(url_for("admin_tasks"))


@app.route("/admin/tasks/<int:tid>/update-status", methods=["POST"])
@admin_required
def update_task_status(tid: int) -> Any:
    with get_db() as conn:
        conn.execute("UPDATE admin_tasks SET status=? WHERE id=?",
                     (request.form.get("status", "pending"), tid))
    return redirect(url_for("admin_tasks"))


@app.route("/admin/tasks/<int:tid>/delete", methods=["POST"])
@admin_required
def delete_admin_task(tid: int) -> Any:
    with get_db() as conn:
        conn.execute("DELETE FROM admin_tasks WHERE id=?", (tid,))
    flash("Task deleted.")
    return redirect(url_for("admin_tasks"))


@app.route("/admin/posts")
@admin_required
def admin_posts() -> Any:
    with get_db() as conn:
        posts = conn.execute("""
            SELECT p.*, u.username AS author FROM posts p
            JOIN users u ON p.author_id=u.id ORDER BY p.created_at DESC
        """).fetchall()
    return render_template("admin/posts.html", posts=posts)


@app.route("/admin/posts/new", methods=["GET", "POST"])
@admin_required
def new_post() -> Any:
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body  = request.form.get("body", "").strip()
        if not title or not body:
            flash("Title and body required.")
            return redirect(url_for("new_post"))
        with get_db() as conn:
            conn.execute(
                "INSERT INTO posts (title, body, author_id, published) VALUES (?,?,?,?)",
                (title, body, session["user_id"], 1 if request.form.get("published") else 0),
            )
        flash("Post published.")
        return redirect(url_for("admin_posts"))
    return render_template("admin/post_new.html")


@app.route("/admin/posts/<int:pid>/toggle", methods=["POST"])
@admin_required
def toggle_post(pid: int) -> Any:
    with get_db() as conn:
        p = conn.execute("SELECT published FROM posts WHERE id=?", (pid,)).fetchone()
        if p:
            conn.execute("UPDATE posts SET published=? WHERE id=?", (0 if p["published"] else 1, pid))
    return redirect(url_for("admin_posts"))


@app.route("/admin/posts/<int:pid>/delete", methods=["POST"])
@admin_required
def delete_post(pid: int) -> Any:
    with get_db() as conn:
        conn.execute("DELETE FROM posts WHERE id=?", (pid,))
    return redirect(url_for("admin_posts"))


@app.route("/account_data")
@login_required
def account_data() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        user = conn.execute(
            "SELECT username, email, created_at FROM users WHERE id=?", (uid,)
        ).fetchone()
        mood_count    = conn.execute("SELECT COUNT(*) FROM mood_logs WHERE user_id=?", (uid,)).fetchone()[0]
        journal_count = conn.execute("SELECT COUNT(*) FROM journals  WHERE user_id=?", (uid,)).fetchone()[0]
        task_count    = conn.execute("SELECT COUNT(*) FROM tasks     WHERE user_id=?", (uid,)).fetchone()[0]
        days_active   = conn.execute(
            "SELECT COUNT(DISTINCT DATE(timestamp)) FROM mood_logs WHERE user_id=?", (uid,)
        ).fetchone()[0]
        top = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE user_id=? GROUP BY mood ORDER BY cnt DESC LIMIT 1
        """, (uid,)).fetchone()
        calendar = conn.execute("""
            SELECT DATE(timestamp) as date, mood FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now','-28 days')
            GROUP BY DATE(timestamp) ORDER BY date ASC
        """, (uid,)).fetchall()
        recent = conn.execute("""
            SELECT mood, timestamp FROM mood_logs
            WHERE user_id=? ORDER BY timestamp DESC LIMIT 5
        """, (uid,)).fetchall()

    top_mood     = top["mood"]                             if top else None
    top_mood_pct = round((top["cnt"] / mood_count) * 100) if top and mood_count else 0

    return jsonify({
        "username":      user["username"],
        "email":         user["email"],
        "member_since":  (user["created_at"] or "")[:10],
        "mood_count":    mood_count,
        "journal_count": journal_count,
        "task_count":    task_count,
        "days_active":   days_active,
        "top_mood":      top_mood,
        "top_mood_pct":  top_mood_pct,
        "calendar":      [{"date": r["date"], "mood": r["mood"]} for r in calendar],
        "recent_moods":  [{"mood": r["mood"], "time": r["timestamp"]} for r in recent],
    })


if __name__ == "__main__":
    app.run(debug=True)