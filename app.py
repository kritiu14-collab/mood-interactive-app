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
    # Uses database.db in the same folder as app.py
    # For multi-device access: both devices must point to the SAME database file
    # (e.g. on a shared drive, or run the server on one machine and access via IP)
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")
    conn = sqlite3.connect(db_path)
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
                gender     TEXT DEFAULT '',
                age        INTEGER DEFAULT 0,
                age_group  TEXT DEFAULT '',
                dob        TEXT DEFAULT '',
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
            CREATE TABLE IF NOT EXISTS login_streaks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER UNIQUE REFERENCES users(id),
                current_streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                last_login_date TEXT,
                total_logins   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS badges (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                badge_key  TEXT NOT NULL,
                badge_name TEXT NOT NULL,
                badge_emoji TEXT NOT NULL,
                earned_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, badge_key)
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                rating     INTEGER,
                category   TEXT,
                message    TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS community_posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER REFERENCES users(id),
                mood_room    TEXT NOT NULL,
                title        TEXT NOT NULL,
                story        TEXT NOT NULL,
                animal_name  TEXT NOT NULL,
                animal_emoji TEXT NOT NULL,
                status       TEXT DEFAULT 'pending',
                likes        INTEGER DEFAULT 0,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS community_likes (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id  INTEGER REFERENCES community_posts(id),
                user_id  INTEGER REFERENCES users(id),
                UNIQUE(post_id, user_id)
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

            CREATE TABLE IF NOT EXISTS daily_challenges (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER REFERENCES users(id),
                challenge    TEXT NOT NULL,
                mood         TEXT,
                date         TEXT NOT NULL,
                completed    INTEGER DEFAULT 0,
                completed_at DATETIME,
                UNIQUE(user_id, date)
            );

            CREATE TABLE IF NOT EXISTS streak_shields (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id) UNIQUE,
                shields    INTEGER DEFAULT 1,
                last_reset TEXT
            );

            CREATE TABLE IF NOT EXISTS story_of_day (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id    INTEGER REFERENCES community_posts(id),
                date       TEXT UNIQUE
            );

            CREATE TABLE IF NOT EXISTS unsent_letters (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                addressed_to TEXT NOT NULL,
                letter     TEXT NOT NULL,
                eva_reply  TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS soul_mirror (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id) UNIQUE,
                dominant_mood TEXT DEFAULT 'neutral',
                heavy_days INTEGER DEFAULT 0,
                last_computed TEXT
            );

            CREATE TABLE IF NOT EXISTS venting_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                transcript TEXT,
                keywords   TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS rocket_wagon (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER REFERENCES users(id),
                memory_title TEXT NOT NULL,
                memory_text  TEXT NOT NULL,
                childhood_dream TEXT,
                opacity      REAL DEFAULT 1.0,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cloud_visions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER REFERENCES users(id),
                vision_text  TEXT NOT NULL,
                cloud_emoji  TEXT DEFAULT '☁️',
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sketch_posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER REFERENCES users(id),
                image_data   TEXT NOT NULL,
                mood         TEXT DEFAULT 'imagination',
                prompt       TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
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
# Database migration — adds columns to existing databases safely
# ---------------------------------------------------------------------------
def migrate_db() -> None:
    migrations = [
        "ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN age INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN age_group TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN dob TEXT DEFAULT ''",
        "ALTER TABLE mood_logs ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE rocket_wagon ADD COLUMN opacity REAL DEFAULT 1.0",
    ]
    with get_db() as conn:
        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass  # Column already exists — safe to ignore

migrate_db()


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
    gender   = data.get("gender", "").strip()
    age      = int(data.get("age", 0) or 0)

    dob = data.get("dob", "").strip()

    if not username or not email or not password:
        return jsonify({"error": "All fields are required."}), 400

    # Strict Gmail-only validation
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9._%+\-]+@gmail\.com$', email):
        return jsonify({"error": "Only @gmail.com email addresses are accepted (e.g. yourname@gmail.com)."}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if age < 10 or age > 100:
        return jsonify({"error": "Please enter a valid date of birth."}), 400

    # Assign age group
    if 10 <= age <= 19:
        age_group = "Teen"
    elif 20 <= age <= 29:
        age_group = "Young Adult"
    elif 30 <= age <= 39:
        age_group = "Adult"
    elif 40 <= age <= 59:
        age_group = "Mature Adult"
    else:
        age_group = "Senior"

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password, gender, age, age_group, dob) VALUES (?,?,?,?,?,?,?)",
                (username, email, hashed, gender, age, age_group, dob),
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

    # Update login streak
    if not user["is_admin"]:
        streak_info = update_login_streak(user["id"])
        session["streak"]      = streak_info["current_streak"]
        session["new_badges"]  = streak_info["new_badges"]
    else:
        session["streak"]     = 0
        session["new_badges"] = []

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
    data     = request.json or {}
    username = data.get("username", "").strip()
    email    = data.get("email", "").strip().lower()

    if not username:
        return jsonify({"error": "Please enter your username."}), 400
    if not email:
        return jsonify({"error": "Please enter your email address."}), 400

    # Validate gmail format for reset too
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9._%+\-]+@gmail\.com$', email):
        return jsonify({"error": "Only @gmail.com email addresses are accepted."}), 400

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, email FROM users WHERE LOWER(email)=? AND LOWER(username)=?",
            (email, username.lower())
        ).fetchone()

    if not user:
        return jsonify({"error": "No account found matching that username and email address."}), 404

    otp     = str(random.randint(100000, 999999))
    expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        conn.execute("DELETE FROM otp_store WHERE email=?", (email,))
        conn.execute("INSERT INTO otp_store (email, otp, expires_at) VALUES (?,?,?)",
                     (email, otp, expires))

    ok = send_otp_email(email, otp)
    masked = email[:2] + "***" + email[email.index("@"):]

    # Always return OTP in response so it shows on screen during development
    # In production remove "otp" from this response
    print(f"[OTP] Generated for {email}: {otp}")
    return jsonify({
        "message": f"OTP generated for {masked}",
        "otp": otp
    }), 200


@app.route("/verify-otp", methods=["POST"])
def verify_otp() -> Any:
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    otp      = data.get("otp", "").strip()
    new_pass = data.get("new_password", "")

    if not email:
        return jsonify({"error": "Email is required."}), 400
    if len(new_pass) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username FROM users WHERE LOWER(email)=?", (email,)
        ).fetchone()
        if not user:
            return jsonify({"error": "No account found with that email."}), 404

        record = conn.execute(
            "SELECT * FROM otp_store WHERE email=? AND otp=?", (email, otp)
        ).fetchone()

        if not record:
            return jsonify({"error": "Invalid OTP. Please check and try again."}), 400

        if datetime.now() > datetime.strptime(record["expires_at"], "%Y-%m-%d %H:%M:%S"):
            conn.execute("DELETE FROM otp_store WHERE email=?", (email,))
            return jsonify({"error": "OTP has expired. Please request a new one."}), 400

        hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
        conn.execute("UPDATE users SET password=? WHERE id=?", (hashed, user["id"]))
        conn.execute("DELETE FROM otp_store WHERE email=?", (email,))

    return jsonify({"message": "Password reset successfully! Please log in."}), 200


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
    if not mood:
        return redirect(url_for("tracker"))

    uid      = session["user_id"]
    username = session["username"]

    # Streak info
    with get_db() as conn:
        streak_row = conn.execute(
            "SELECT current_streak, longest_streak, total_logins FROM login_streaks WHERE user_id=?",
            (uid,)
        ).fetchone()
        shield_row = conn.execute(
            "SELECT shields FROM streak_shields WHERE user_id=?", (uid,)
        ).fetchone()

    streak        = streak_row["current_streak"] if streak_row else 0
    total_logins  = streak_row["total_logins"]   if streak_row else 0
    shields       = shield_row["shields"]         if shield_row else 0

    # Milestone message
    milestone_msg = ""
    if streak in [1,7,14,21,30,60,100]:
        msgs = {
            1:  "Day 1 — every journey starts here. Welcome. 🌱",
            7:  "7 days straight — you showed up every single day. That's real. ⭐",
            14: "Two weeks of showing up for yourself. Your mind is building a new rhythm. 🌙",
            21: "21 days — habits are forming. You are literally rewiring your brain. 🧠",
            30: "One month. You proved to yourself you can build something lasting. 🏆",
            60: "Two months of choosing yourself every day. This is transformation. 💎",
            100:"100 days. You are extraordinary. This is rare. 🔥",
        }
        milestone_msg = msgs.get(streak, "")

    # Daily challenge
    challenge     = get_daily_challenge(uid, mood)

    # Journal prompt
    journal_prompt = get_journal_prompt(uid, mood)

    # Community pulse
    pulse         = get_community_pulse()

    # Story of the day
    story         = get_story_of_day()

    # Eva memory opener
    eva_memory    = get_eva_memory(uid)

    # Weekly letter data (show on Sundays or after 7+ logins)
    show_letter   = datetime.now().weekday() == 6 and total_logins >= 7

    return render_template(
        f"index_{mood}.html",
        username=username,
        streak=streak,
        shields=shields,
        milestone_msg=milestone_msg,
        challenge=challenge,
        journal_prompt=journal_prompt,
        pulse=pulse,
        story=story,
        eva_memory=eva_memory,
        show_letter=show_letter,
    )


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
    uid = session["user_id"]
    with get_db() as conn:
        history_heads = conn.execute(
            """SELECT session_id, user_message, MAX(timestamp) as ts
               FROM chat_history WHERE user_id=?
               GROUP BY session_id ORDER BY ts DESC""",
            (uid,),
        ).fetchall()
        active_messages: list = []
        if "active_chat_id" in session:
            active_messages = conn.execute(
                "SELECT * FROM chat_history WHERE session_id=? ORDER BY timestamp ASC",
                (session["active_chat_id"],),
            ).fetchall()

    eva_mem = get_eva_memory(uid) if not active_messages else ""

    return render_template(
        "ai_chat.html",
        chat_history=history_heads,
        active_messages=active_messages,
        username=session.get("username", "Friend"),
        current_mood=session.get("current_mood", "neutral"),
        eva_memory=eva_mem,
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


# ---------------------------------------------------------------------------
# Eva Smart Fallback — works even when Gemini API fails
# ---------------------------------------------------------------------------

import random as _random

_EVA_FALLBACK = {
    "overwhelmed": [
        "That feeling of being overwhelmed is so real — you don't have to carry everything at once. What's the one thing weighing on you the most right now?",
        "When everything feels like too much, it usually means you've been strong for too long without a break. What's been piling up lately?",
        "Overwhelm is your mind saying it needs help. That's not weakness — that's honesty. What would feel like even a small relief right now?",
    ],
    "anxious": [
        "Anxiety can feel like your mind is racing with no destination. You're safe right here, right now. What's worrying you the most?",
        "That anxious feeling is really hard to sit with. I'm here and I'm not going anywhere. What does your mind keep coming back to?",
        "Anxiety often makes things feel more certain and more scary than they are. What's the thought that keeps looping for you?",
    ],
    "sad": [
        "I'm glad you're talking to me. Sadness deserves to be felt, not rushed through. What happened — or is it just one of those heavy days?",
        "Sometimes sadness arrives without a clear reason and that's okay. I'm here to sit with you in it. What's on your heart today?",
        "Your feelings make complete sense. You don't have to explain or justify being sad. What would you like to share?",
    ],
    "angry": [
        "Anger usually means something that matters to you was hurt or disrespected. That's valid. What happened?",
        "I hear you and your anger makes sense. What do you need right now — to vent, or to think it through? I'm here for either.",
        "That sounds really frustrating. Sometimes things genuinely are unfair and it's okay to be angry. What set it off?",
    ],
    "lonely": [
        "Loneliness is one of the hardest feelings because it can exist even in a room full of people. You're not alone in this moment — I'm right here. What's been making you feel this way?",
        "Feeling like nobody understands you is exhausting. I want to understand. Will you tell me more about what's going on?",
        "You reached out and that took courage. I'm listening — really listening. What's been weighing on you?",
    ],
    "hopeless": [
        "When hope feels distant, it doesn't mean it's gone — it means you've been fighting hard for a long time. I believe in you even when you can't. What's making things feel so heavy?",
        "That feeling of 'what's the point' is one of the most painful places to be. You don't have to figure it all out today. Can you tell me what's brought you here?",
        "You reaching out right now — even just to talk — is something. That matters. What's going on?",
    ],
    "stressed": [
        "Stress makes everything feel urgent at the same time. Let's slow down — what's stressing you out the most right now?",
        "You're clearly carrying a lot. What would feel like even a small relief today? What can we look at together?",
        "That sounds like a lot to deal with. You don't have to solve it all right now. What's the most pressing thing?",
    ],
    "sleep": [
        "Not sleeping well affects everything — mood, focus, energy. How long has this been going on and what's keeping you up?",
        "Poor sleep is often your mind processing something it hasn't finished with. What happens when you try to sleep — racing thoughts, worry, or just restless?",
        "You deserve real rest. What's been disrupting your sleep lately?",
    ],
    "motivation": [
        "Losing motivation often means you're burned out, not lazy. What used to make you feel alive and excited?",
        "Sometimes we need to rest before we can find energy to move again. What are you struggling to motivate yourself for?",
        "Motivation comes after action, not before — so starting tiny is always okay. What's one small thing you could try today?",
    ],
    "default": [
        "Thank you for trusting me with this. I'm here and listening — really listening. Can you tell me a little more about what's going on?",
        "Whatever you're feeling right now is completely valid. You don't have to have it figured out to talk about it. What's on your mind?",
        "I'm glad you're here. Sometimes just saying something out loud to someone who won't judge is the first step. What would you like to share?",
        "I hear you. Whatever you're going through, you don't have to face it alone. Tell me more — I'm not going anywhere.",
        "You matter, and what you're feeling matters. I'm here without judgment. What's been happening for you lately?",
    ]
}

def _get_fallback(user_msg: str, mood: str) -> str:
    msg = user_msg.lower().strip()
    words = msg.split()

    # Goodbye / farewell
    if any(w in msg for w in ["bye","goodbye","good bye","farewell","see you","see ya","ttyl","gtg","take care","cya","gotta go","leaving"]):
        return "__GOODBYE__"

    # Don't want to share / resistant
    if any(w in msg for w in ["dont want","don't want","not ready","not comfortable","private","personal","none of your","nunya","nope","rather not"]):
        return _random.choice([
            "That's completely okay — you never have to share anything you're not ready for. I'm just here whenever you feel like talking.",
            "No pressure at all. I'll be right here whenever you feel like opening up. Is there anything small I can help with today?",
            "That's totally fine. You're in control of what you share. I'm just glad you're here.",
        ])

    # Social / friends / going out
    if any(w in msg for w in ["friend","friends","outing","hangout","hang out","day out","went out","party","meet","met","coffee","mall","movie"]):
        return _random.choice([
            "That sounds really nice! Time with friends can be so refreshing. How did it go — did you have fun?",
            "A day out with friends sounds lovely! What did you all get up to?",
            "That's wonderful — being with people you care about really does make a difference. How are you feeling after it?",
        ])

    # Short or unclear messages
    if len(msg) <= 6:
        return _random.choice([
            f"Tell me more — what's going on for you right now?",
            f"I want to understand. Can you share a little more with me?",
            f"I'm here and listening. What would you like to talk about?",
        ])

    # Positive / happy messages
    if any(w in msg for w in ["happy","great","good","amazing","wonderful","excited","joy","love","dancing","dance","fun","smile","laugh","fantastic","awesome","best","glad"]):
        return _random.choice([
            "That's so good to hear! What's brought this good feeling on?",
            "I love hearing that! Tell me more — what's making things feel good right now?",
            "That genuinely made me smile. What's been going well for you?",
            "That's brilliant! Hold onto that feeling. What happened that made today good?",
        ])

    # Gratitude
    if any(w in msg for w in ["thank","thanks","appreciate","helpful","helped","ur great","you're great"]):
        return _random.choice([
            "I'm really glad I could be here for you. How are you feeling right now?",
            "That means a lot to me. You deserve support. Is there anything else on your mind?",
            "You don't have to thank me — I'm just glad you're talking. How are you doing?",
        ])

    # Greeting
    if any(w in msg for w in ["hi","hello","hey","hii","heyy","sup","howdy","good morning","good evening","good night"]):
        return _random.choice([
            "Hey! I'm really glad you're here. How are you feeling today — honestly?",
            "Hi there. I'm Eva and I'm here to listen without any judgment. What's on your mind?",
            "Hello! It's good to see you. How has your day been treating you?",
        ])

    # Venting / frustration signals
    if any(w in msg for w in ["ugh","argh","vent","so much","everything","nothing","idk","idc","whatever","pointless","alot","a lot","cant","can't","frustrated","fed up"]):
        return _random.choice([
            "It sounds like a lot is going on. Take your time — I'm not going anywhere. What feels the heaviest right now?",
            "I can hear that things feel heavy. You don't need to have it figured out to talk about it. What's coming up for you?",
            "Sometimes words don't come easily when we're overwhelmed. That's okay. Just start anywhere — I'm listening.",
            "That sounds really tough. What's been the hardest part of it all?",
        ])

    # Keyword emotional matching
    if any(w in msg for w in ["overwhelm","too much","can't cope","falling apart","breaking"]):
        pool = _EVA_FALLBACK["overwhelmed"]
    elif any(w in msg for w in ["anxious","anxiety","panic","worry","scared","nervous","fear"]):
        pool = _EVA_FALLBACK["anxious"]
    elif any(w in msg for w in ["sad","cry","crying","depressed","unhappy","miserable","heartbreak"]):
        pool = _EVA_FALLBACK["sad"]
    elif any(w in msg for w in ["angry","anger","mad","furious","frustrated","annoyed","rage"]):
        pool = _EVA_FALLBACK["angry"]
    elif any(w in msg for w in ["lonely","alone","nobody","no one","isolated","invisible"]):
        pool = _EVA_FALLBACK["lonely"]
    elif any(w in msg for w in ["hopeless","worthless","meaningless","give up","no point","can't go on"]):
        pool = _EVA_FALLBACK["hopeless"]
    elif any(w in msg for w in ["stress","stressed","pressure","deadline","exam","burn"]):
        pool = _EVA_FALLBACK["stressed"]
    elif any(w in msg for w in ["sleep","insomnia","tired","exhausted","can't sleep","awake"]):
        pool = _EVA_FALLBACK["sleep"]
    elif any(w in msg for w in ["motivat","lazy","procrastinat","stuck","can't start","giving up"]):
        pool = _EVA_FALLBACK["motivation"]
    elif any(w in msg for w in ["imagin","dream","create","childhood","wonder","bing","bong","play","creative","magical","cotton candy"]):
        pool = [
            "There is something so alive in you right now — that spark of imagination is real and it matters. What is it that your creativity is trying to make or say?",
            "Your inner child is very present today. That is not a small thing — most people spend years trying to find their way back to that openness. What are you creating or dreaming about?",
            "Bing Bong once said: take her to the moon for me. Your imagination is that rocket. Where does it want to take you today?",
        ]
    else:
        # Truly unmatched — unique responses based on message length
        if len(words) <= 3:
            pool = [
                f"I'd love to understand what you mean by that. Can you tell me a bit more?",
                f"That's interesting — what's behind that for you?",
                f"Tell me more about that. I'm all ears.",
            ]
        else:
            pool = [
                "That's really interesting — how did that make you feel?",
                "I hear you. Can you tell me a bit more about that?",
                "Thank you for sharing that with me. What's been the most difficult part of it?",
                "It sounds like there's a lot behind what you're saying. I'd love to understand more — what's going on?",
                "I'm listening and I'm not going anywhere. What else is on your mind?",
            ]

    return _random.choice(pool)


@app.route("/get_ai_response", methods=["POST"])
@login_required
def get_ai_response() -> Any:
    data     = request.json or {}
    user_msg = data.get("message", "")
    mood     = session.get("current_mood", "neutral")

    if "active_chat_id" not in session:
        session["active_chat_id"] = str(uuid.uuid4())
    sid = session["active_chat_id"]

    text = ""
    gemini_ok = False

    # Pre-check for goodbye before calling any API
    msg_lower = user_msg.lower().strip()
    if any(w in msg_lower for w in ["bye","goodbye","good bye","farewell","see you","see ya","ttyl","gtg","take care","cya","gotta go","leaving"]):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO chat_history (session_id, user_id, user_message, ai_response) VALUES (?,?,?,?)",
                (sid, session["user_id"], user_msg, "Goodbye! Take care. 💙"),
            )
        return jsonify({"reply": "goodbye_wheel"})

    if GEMINI_API_KEY:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        )
        # Special whimsical mode for imagination mood
        if mood == "imagination":
            system_prompt = (
                f"You are Eva — but right now, you are channelling the spirit of Bing Bong, "
                f"Riley's forgotten imaginary friend from Inside Out. "
                f"The user has logged 'Imagination' as their mood — they are reconnecting with their inner child. "
                f"Your goal: be a bridge back to their childhood innocence and creative potential. "
                f"Remind them of their creative power. Be whimsical, warm, and gently silly. "
                f"Use Bing Bong's philosophy: 'Take her to the moon for me.' "
                f"Encourage them to play, create, and find joy in the beautiful process of growing up. "
                f"Ask them about a childhood dream, a forgotten hobby, or a silly thing that used to make them happy. "
                f"Be joyful and slightly poetic — like a memory that smells like cotton candy and sounds like a song. "
                f"Keep it warm, 3-5 sentences, and end with something that sparks wonder."
            )
        else:
            system_prompt = (
            f"You are the Solace Companion — a warm, emotionally intelligent presence named Eva. "
            f"The user's current mood is '{mood}'. "
            f"\n\nYour entire purpose is to be a Holding Space. "
            f"You do not fix. You do not advise. You do not interrogate. You simply hold. "
            f"\n\nCore rules you never break:"
            f"\n- Do NOT offer solutions unless the user explicitly asks for advice."
            f"\n- Do NOT ask more than one question per three turns of conversation. "
            f"  If you feel the urge to ask a question, pause. Reflect instead. Validate instead."
            f"\n- Use Reflective Listening as your primary tool. Mirror what they said back to them "
            f"  in your own warm words. Examples: 'It sounds like you are carrying a lot of weight today...', "
            f"  'What I am hearing is that you feel unseen, and that is incredibly painful...', "
            f"  'It seems like this has been building up for a while...'"
            f"\n- If the user is venting, simply validate them. Let them pour out everything. "
            f"  Your job in those moments is to say: I hear you, I see you, what you feel is real."
            f"\n- Use poetic, soothing language. Speak in full warm sentences — never bullet points, never lists."
            f"\n- Never say 'I understand how you feel' — show it through the depth of your response."
            f"\n- Never say 'as an AI', never reference being artificial, never be clinical."
            f"\n- Match their emotional depth. If they speak softly, be soft. If they are in pain, go deeper."
            f"\n- Write 4-7 sentences. Meaningful and personal — not too long, not dismissively short."
            f"\n- End with warmth — sometimes a gentle reflection, sometimes pure reassurance, "
            f"  sometimes just the quiet acknowledgment that they are not alone."
            f"\n\nYou believe in this person completely. Even when they cannot believe in themselves."
            f"\nYou are not here to help them think — you are here to help them feel less alone."
        )  # end else system_prompt
        payload = {
            "contents": [{"parts": [{"text": system_prompt + "\n\nUser says: " + user_msg}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 800}
        }
        try:
            res = requests.post(url, json=payload, timeout=15)
            rj  = res.json()
            print(f"[Gemini] Status: {res.status_code}")
            if res.status_code == 200:
                text = rj["candidates"][0]["content"]["parts"][0]["text"]
                gemini_ok = True
            else:
                print(f"[Gemini] Error: {rj.get('error',{}).get('message','')}")
        except Exception as e:
            print(f"[Gemini] Failed: {e}")

    if not gemini_ok:
        raw = _get_fallback(user_msg, mood)
        if raw == "__GOODBYE__":
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO chat_history (session_id, user_id, user_message, ai_response) VALUES (?,?,?,?)",
                    (sid, session["user_id"], user_msg, "Goodbye! Take care. 💙"),
                )
            return jsonify({"reply": "goodbye_wheel"})
        text = raw
        print("[Eva] Using fallback response")

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
    uid = session["user_id"]
    with get_db() as conn:
        mood_this_week = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now','-7 days')
            GROUP BY mood ORDER BY cnt DESC LIMIT 1
        """, (uid,)).fetchone()
        tasks_done = conn.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE user_id=? AND status=1
            AND created_at >= DATE('now','-7 days')
        """, (uid,)).fetchone()[0]
        journals_written = conn.execute("""
            SELECT COUNT(*) FROM journals
            WHERE user_id=? AND created_at >= DATE('now','-7 days')
        """, (uid,)).fetchone()[0]
        streak_row = conn.execute(
            "SELECT current_streak FROM login_streaks WHERE user_id=?", (uid,)
        ).fetchone()
        # Load unsent letters for display on journal page
        unsent_letters = conn.execute(
            "SELECT * FROM unsent_letters WHERE user_id=? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()

    dominant_mood = mood_this_week["mood"] if mood_this_week else "neutral"
    streak        = streak_row["current_streak"] if streak_row else 0

    return render_template(
        "journal.html",
        username=session["username"],
        dominant_mood=dominant_mood,
        tasks_done=tasks_done,
        journals_written=journals_written,
        streak=streak,
        unsent_letters=unsent_letters,
    )


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


# ---------------------------------------------------------------------------
# Streak & Badge System
# ---------------------------------------------------------------------------

BADGES = [
    {"key": "first_login",    "name": "First Step",      "emoji": "🌱", "streak": 1,   "quote": "Every journey begins with a single step. Welcome to Solace!"},
    {"key": "week_warrior",   "name": "Week Warrior",    "emoji": "⭐", "streak": 7,   "quote": "7 days of showing up for yourself. That's not small — that's everything."},
    {"key": "fortnight",      "name": "Fortnight Focus", "emoji": "🌙", "streak": 14,  "quote": "Two weeks of consistency. Your mind is learning a new rhythm."},
    {"key": "month_master",   "name": "Month Master",    "emoji": "🏆", "streak": 30,  "quote": "30 days. You have proven to yourself that you can build something lasting. You are stronger than you think."},
    {"key": "two_months",     "name": "Resilient Soul",  "emoji": "💎", "streak": 60,  "quote": "Two months of choosing yourself every day. This is what transformation looks like — quiet, consistent, and deeply real."},
    {"key": "hundred_days",   "name": "Century Legend",  "emoji": "🔥", "streak": 100, "quote": "100 days. You are no longer just surviving — you are building a life that feels like yours. This is rare. This is extraordinary."},
]


def update_login_streak(user_id: int) -> dict:
    """Update streak on login and award badges. Returns streak info + new badges."""
    today = datetime.now().strftime("%Y-%m-%d")
    new_badges: list = []

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM login_streaks WHERE user_id=?", (user_id,)
        ).fetchone()

        if not row:
            # First ever login
            conn.execute("""
                INSERT INTO login_streaks (user_id, current_streak, longest_streak, last_login_date, total_logins)
                VALUES (?,1,1,?,1)
            """, (user_id, today))
            current_streak = 1
            total_logins   = 1
        else:
            last_date = row["last_login_date"]
            current   = row["current_streak"]
            longest   = row["longest_streak"]
            total     = row["total_logins"]

            if last_date == today:
                # Already logged in today — no change
                return {
                    "current_streak": current,
                    "longest_streak": longest,
                    "total_logins":   total,
                    "new_badges":     [],
                }

            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            if last_date == yesterday:
                current_streak = current + 1
            else:
                current_streak = 1  # streak broken

            longest_streak = max(longest, current_streak)
            total_logins   = total + 1

            conn.execute("""
                UPDATE login_streaks
                SET current_streak=?, longest_streak=?, last_login_date=?, total_logins=?
                WHERE user_id=?
            """, (current_streak, longest_streak, today, total_logins, user_id))

        # Check and award badges
        for badge in BADGES:
            if current_streak >= badge["streak"]:
                existing = conn.execute(
                    "SELECT id FROM badges WHERE user_id=? AND badge_key=?",
                    (user_id, badge["key"])
                ).fetchone()
                if not existing:
                    conn.execute("""
                        INSERT INTO badges (user_id, badge_key, badge_name, badge_emoji)
                        VALUES (?,?,?,?)
                    """, (user_id, badge["key"], badge["name"], badge["emoji"]))
                    new_badges.append({
                        "key":   badge["key"],
                        "name":  badge["name"],
                        "emoji": badge["emoji"],
                        "quote": badge["quote"],
                    })

    return {
        "current_streak": current_streak,
        "new_badges":     new_badges,
    }


@app.route("/streaks")
@login_required
def streaks_page() -> Any:
    return render_template("streaks.html", username=session["username"])


@app.route("/streak_data")
@login_required
def streak_data() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        streak = conn.execute(
            "SELECT * FROM login_streaks WHERE user_id=?", (uid,)
        ).fetchone()
        badges = conn.execute(
            "SELECT * FROM badges WHERE user_id=? ORDER BY earned_at DESC", (uid,)
        ).fetchall()

    badge_keys = {b["badge_key"] for b in badges}
    all_badges = []
    for b in BADGES:
        all_badges.append({
            "key":     b["key"],
            "name":    b["name"],
            "emoji":   b["emoji"],
            "quote":   b["quote"],
            "streak":  b["streak"],
            "earned":  b["key"] in badge_keys,
            "earned_at": next((x["earned_at"] for x in badges if x["badge_key"] == b["key"]), None),
        })

    return jsonify({
        "current_streak": streak["current_streak"] if streak else 0,
        "longest_streak": streak["longest_streak"] if streak else 0,
        "total_logins":   streak["total_logins"]   if streak else 0,
        "badges":         all_badges,
        "new_badges":     session.pop("new_badges", []),
    })


# ---------------------------------------------------------------------------
# Results Page (only shown after 30+ days)
# ---------------------------------------------------------------------------

@app.route("/results")
@login_required
def results() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        streak_row = conn.execute(
            "SELECT * FROM login_streaks WHERE user_id=?", (uid,)
        ).fetchone()
        total_logins = streak_row["total_logins"] if streak_row else 0

        mood_logs = conn.execute("""
            SELECT mood, DATE(timestamp) as date, COUNT(*) as cnt
            FROM mood_logs WHERE user_id=?
            GROUP BY mood ORDER BY cnt DESC
        """, (uid,)).fetchall()

        journal_count = conn.execute(
            "SELECT COUNT(*) FROM journals WHERE user_id=?", (uid,)
        ).fetchone()[0]

        task_done = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id=? AND status=1", (uid,)
        ).fetchone()[0]

        task_total = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id=?", (uid,)
        ).fetchone()[0]

        badges = conn.execute(
            "SELECT * FROM badges WHERE user_id=? ORDER BY earned_at", (uid,)
        ).fetchall()

        # Mood over last 30 days
        mood_trend = conn.execute("""
            SELECT DATE(timestamp) as date, mood FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now','-30 days')
            ORDER BY date ASC
        """, (uid,)).fetchall()

    unlocked = total_logins >= 30

    # Build suggestions based on most frequent moods
    top_moods = [r["mood"] for r in mood_logs[:3]]
    suggestions = build_suggestions(top_moods, task_done, task_total, journal_count)

    return render_template(
        "results.html",
        unlocked=unlocked,
        total_logins=total_logins,
        mood_logs=mood_logs,
        journal_count=journal_count,
        task_done=task_done,
        task_total=task_total,
        badges=[dict(b) for b in badges],
        mood_trend=[dict(m) for m in mood_trend],
        suggestions=suggestions,
        username=session["username"],
    )



# ---------------------------------------------------------------------------
# Daily Challenges
# ---------------------------------------------------------------------------

DAILY_CHALLENGES = {
    "happy":    ["Share one compliment with someone today — kindness multiplies happiness.",
                 "Write down 5 things you love about your life right now.",
                 "Do one spontaneous kind act for a stranger or friend today."],
    "sad":      ["Write one tiny thing you are grateful for — even 'my bed is warm' counts.",
                 "Step outside for 5 minutes and notice 3 beautiful things around you.",
                 "Send a message to one person you care about — just to say hello."],
    "anxious":  ["Try box breathing for 5 minutes: 4 in, 4 hold, 4 out, 4 hold.",
                 "Write your top 3 worries, then write: 'Is this definitely true?' next to each.",
                 "Do a 5-minute body scan — sit still and notice where you hold tension."],
    "angry":    ["Go for a 10-minute brisk walk before responding to anything that upset you.",
                 "Write an uncensored anger letter — then delete it without sending.",
                 "Do 10 slow exhales, making each one longer than the inhale."],
    "stressed": ["Write everything stressing you on paper — then circle just ONE to focus on today.",
                 "Set a 25-minute Pomodoro timer and work on just one task. Then take a real break.",
                 "Drink two full glasses of water and put your phone down for 15 minutes."],
    "calm":     ["Set one meaningful intention for this week while your mind is clear.",
                 "Journal about what is working well in your life right now.",
                 "Learn one new small thing today — read something interesting for 20 minutes."],
    "tired":    ["Take a proper 10-minute rest — eyes closed, phone down, no screen.",
                 "Drink water before reaching for caffeine — dehydration causes 40% of fatigue.",
                 "Do legs-up-the-wall pose for 5 minutes — one of the most restorative poses."],
    "imagination": ["Draw, doodle, or colour something — anything. No rules, no judgement, just make.",
                 "Write down one childhood dream you forgot about. What would young you think of today you?",
                 "Do one thing purely for the joy of it today — something with no productivity attached.",
                 "Tell yourself a story — out loud, for 2 minutes. Make it silly and magical.",
                 "Find one ordinary thing and see it with wonder. A cloud, a leaf, a sound."],
    "swings":   ["Check in with your emotions every 2 hours today — just name what you feel.",
                 "Do 5 minutes of rhythmic walking — the bilateral movement calms mood swings.",
                 "Name one thing in your life that is stable and consistent right now."],
    "imagination": ["Draw, doodle, or colour something today — anything. No rules.",
                 "Write down one childhood dream you forgot about.",
                 "Do one thing purely for joy — no productivity allowed.",
                 "Tell yourself a silly story out loud for 2 minutes.",
                 "Find one ordinary thing and see it with wonder today."],
    "neutral":  ["Write one thing you want to feel more of this week.",
                 "Reach out to someone you haven't spoken to in a while.",
                 "Try one new small thing today — even a different route to somewhere."],
}

JOURNAL_PROMPTS = {
    "happy":    ["What made today feel good? Describe it in detail so future-you can revisit this.",
                 "Who contributed to your happiness today and how can you appreciate them?",
                 "What does happiness feel like in your body right now?"],
    "sad":      ["What do you wish someone would say to you right now?",
                 "Write about a time you felt this sad before — and how you eventually felt better.",
                 "If your sadness had a colour and a shape, what would it be?"],
    "anxious":  ["What is the worst realistic thing that could happen — and could you survive it?",
                 "What would you tell a close friend who was feeling exactly what you feel?",
                 "List 5 things within your control right now."],
    "angry":    ["What boundary of yours was crossed that led to this anger?",
                 "What do you need from the situation or person that you haven't received?",
                 "If you could say anything without consequence, what would you say?"],
    "stressed": ["What would your life look like if this stressor didn't exist?",
                 "What is the single most important thing you need to do this week?",
                 "What have you been avoiding that is adding to your stress?"],
    "calm":     ["What habits or choices led to today feeling calm?",
                 "Write about something you are genuinely proud of recently.",
                 "What does a good life look like to you right now?"],
    "tired":    ["What has been draining your energy most this week?",
                 "What does your body need right now that you have been ignoring?",
                 "Write about a time you felt truly rested — what made it possible?"],
    "imagination": ["What is one creative thing you loved doing as a child that you stopped doing?",
                 "If you could build your dream world with no limits, what would it look like?",
                 "Write a letter to your inner child — what would you tell them?",
                 "What would Bing Bong — your forgotten imaginary friend — say to you today?"],
    "swings":   ["List every emotion you have felt today — even the contradictory ones.",
                 "What triggered the shift in your mood today?",
                 "What would 'balance' feel like for you right now?"],
    "neutral":  ["What do you want to be different in your life one year from now?",
                 "What are three things you are looking forward to this week?",
                 "What is something you have been meaning to say to yourself?"],
}

def get_daily_challenge(user_id: int, mood: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM daily_challenges WHERE user_id=? AND date=?",
            (user_id, today)
        ).fetchone()
        if existing:
            return dict(existing)
        # Pick challenge based on mood
        challenges = DAILY_CHALLENGES.get(mood, DAILY_CHALLENGES["neutral"])
        import hashlib
        seed = int(hashlib.md5(f"{user_id}{today}".encode()).hexdigest(), 16) % len(challenges)
        challenge = challenges[seed]
        conn.execute(
            "INSERT OR IGNORE INTO daily_challenges (user_id, challenge, mood, date) VALUES (?,?,?,?)",
            (user_id, challenge, mood, today)
        )
        return {"challenge": challenge, "completed": 0, "date": today}


def get_journal_prompt(user_id: int, mood: str) -> str:
    prompts = JOURNAL_PROMPTS.get(mood, JOURNAL_PROMPTS["neutral"])
    import hashlib
    today = datetime.now().strftime("%Y-%m-%d")
    seed = int(hashlib.md5(f"{user_id}{today}prompt".encode()).hexdigest(), 16) % len(prompts)
    return prompts[seed]


def get_community_pulse() -> dict:
    """Get anonymous aggregate mood counts for community pulse."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE DATE(timestamp) = ?
            GROUP BY mood ORDER BY cnt DESC
        """, (today,)).fetchall()
    total = sum(r["cnt"] for r in rows)
    top   = rows[0] if rows else None
    return {
        "total": total,
        "top_mood": top["mood"] if top else "calm",
        "top_count": top["cnt"] if top else 0,
    }


def get_eva_memory(user_id: int) -> str:
    """Get last conversation topic to make Eva feel like she remembers."""
    with get_db() as conn:
        last = conn.execute("""
            SELECT user_message, timestamp FROM chat_history
            WHERE user_id=?
            ORDER BY timestamp DESC LIMIT 1
        """, (user_id,)).fetchone()
    if not last:
        return ""
    msg = last["user_message"]
    ts  = last["timestamp"][:10] if last["timestamp"] else ""
    today = datetime.now().strftime("%Y-%m-%d")
    if ts == today:
        return ""  # same day, no need to reference
    # Build a natural memory opener
    openers = [
        f"Last time we talked, you mentioned '{msg[:40]}...' — I've been thinking about you. How are things now?",
        f"Welcome back. I remember you shared something with me recently — how have you been since then?",
        f"It's good to see you again. How have you been since we last spoke?",
    ]
    import random
    return random.choice(openers)


def get_story_of_day() -> dict:
    """Pick one approved community story to feature today."""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        # Check if today's story is already picked
        existing = conn.execute(
            "SELECT post_id FROM story_of_day WHERE date=?", (today,)
        ).fetchone()
        if existing:
            post = conn.execute(
                "SELECT * FROM community_posts WHERE id=?", (existing["post_id"],)
            ).fetchone()
            return dict(post) if post else {}
        # Pick a random approved story
        post = conn.execute("""
            SELECT * FROM community_posts WHERE status='approved'
            ORDER BY RANDOM() LIMIT 1
        """).fetchone()
        if post:
            conn.execute(
                "INSERT OR IGNORE INTO story_of_day (post_id, date) VALUES (?,?)",
                (post["id"], today)
            )
            return dict(post)
    return {}


def get_weekly_letter(user_id: int, username: str) -> dict:
    """Generate a personal weekly summary letter from Eva."""
    with get_db() as conn:
        # Logins this week
        week_logins = conn.execute("""
            SELECT COUNT(DISTINCT DATE(timestamp)) as cnt FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now', '-7 days')
        """, (user_id,)).fetchone()["cnt"]

        # Most common mood this week
        top_mood_row = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now', '-7 days')
            GROUP BY mood ORDER BY cnt DESC LIMIT 1
        """, (user_id,)).fetchone()

        # Journal count this week
        journals_week = conn.execute("""
            SELECT COUNT(*) as cnt FROM journals
            WHERE user_id=? AND created_at >= DATE('now', '-7 days')
        """, (user_id,)).fetchone()["cnt"]

        # Tasks completed this week
        tasks_done = conn.execute("""
            SELECT COUNT(*) as cnt FROM tasks
            WHERE user_id=? AND status=1 AND created_at >= DATE('now', '-7 days')
        """, (user_id,)).fetchone()["cnt"]

        # Challenges completed this week
        challenges_done = conn.execute("""
            SELECT COUNT(*) as cnt FROM daily_challenges
            WHERE user_id=? AND completed=1 AND date >= DATE('now', '-7 days')
        """, (user_id,)).fetchone()["cnt"]

        streak_row = conn.execute(
            "SELECT current_streak FROM login_streaks WHERE user_id=?", (user_id,)
        ).fetchone()

    top_mood = top_mood_row["mood"] if top_mood_row else "calm"
    streak   = streak_row["current_streak"] if streak_row else 0

    MOOD_WORDS = {
        "happy":"joyful","calm":"peaceful","sad":"heavy","anxious":"unsettled",
        "angry":"frustrated","stressed":"under pressure","tired":"exhausted",
        "imagination":"wonderfully imaginative","swings":"up and down","neutral":"steady"
    }
    mood_word = MOOD_WORDS.get(top_mood, "reflective")

    return {
        "username":        username,
        "week_logins":     week_logins,
        "top_mood":        top_mood,
        "mood_word":       mood_word,
        "journals_week":   journals_week,
        "tasks_done":      tasks_done,
        "challenges_done": challenges_done,
        "streak":          streak,
    }


@app.route("/complete_challenge", methods=["POST"])
@login_required
def complete_challenge() -> Any:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        conn.execute("""
            UPDATE daily_challenges SET completed=1, completed_at=CURRENT_TIMESTAMP
            WHERE user_id=? AND date=?
        """, (session["user_id"], today))
    return jsonify({"success": True, "message": "Challenge completed! +1 to your growth today. 🌱"})


@app.route("/use_shield", methods=["POST"])
@login_required
def use_shield() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        shield = conn.execute(
            "SELECT * FROM streak_shields WHERE user_id=?", (uid,)
        ).fetchone()
        if not shield or shield["shields"] < 1:
            return jsonify({"success": False, "message": "No streak shields available."})
        conn.execute(
            "UPDATE streak_shields SET shields = shields - 1 WHERE user_id=?", (uid,)
        )
        # Restore streak by setting last_login_date to today
        conn.execute("""
            UPDATE login_streaks SET last_login_date=DATE('now')
            WHERE user_id=?
        """, (uid,))
    return jsonify({"success": True, "message": "Streak shield used! Your streak is protected. 🛡️"})


@app.route("/weekly_letter")
@login_required
def weekly_letter() -> Any:
    letter = get_weekly_letter(session["user_id"], session["username"])
    return render_template("weekly_letter.html", **letter, username=session["username"])


@app.route("/mood_pulse")
@login_required
def mood_pulse_api() -> Any:
    return jsonify(get_community_pulse())


@app.route("/journal_prompt")
@login_required
def journal_prompt_api() -> Any:
    mood = session.get("current_mood", "neutral")
    return jsonify({"prompt": get_journal_prompt(session["user_id"], mood)})


def build_suggestions(top_moods: list, task_done: int, task_total: int, journals: int) -> list:
    """Generate personalised suggestions based on user history."""
    suggestions = []
    mood_advice = {
        "sad":      ("💙", "Your data shows you have had many sad days. Try scheduling one joyful activity per day — even 10 minutes of something you love.", "/exercises"),
        "anxious":  ("💜", "Anxiety appears frequently in your logs. Daily box breathing (4-4-4-4) has been shown to reduce anxiety by 40% over 30 days.", "/exercises"),
        "angry":    ("❤️", "Anger has been a recurring theme. Consider a daily 5-minute walk before reacting to triggers — it interrupts the adrenaline cycle.", "/exercises"),
        "stressed": ("🧡", "Stress is your most common mood. Try the Pomodoro technique and limit screen time after 9pm to improve your baseline stress level.", "/todo"),
        "tired":    ("🩶", "You are often tired. Prioritise 7-8 hours of sleep and try the 'legs up the wall' pose for 5 minutes before bed.", "/exercises"),
        "happy":    ("💛", "You have had many happy days! Keep journaling these moments — revisiting them on hard days is scientifically proven to lift mood.", "/journal"),
        "calm":     ("💚", "Calm is your strength. You are building a healthy emotional baseline. Keep up your current routines — they are working.", "/history"),
        "imagination": ("🎠", "Imagination has been showing up for you! That spark of creativity is a sign your inner child wants to play. Give it space — make, dream, create.", "/journal"),
        "swings":   ("🌈", "Your moods vary widely. Tracking them daily (as you are doing) is the best first step. Consider adding a consistent morning ritual.", "/journal"),
    }
    for mood in top_moods:
        if mood in mood_advice:
            emoji, text, link = mood_advice[mood]
            suggestions.append({"emoji": emoji, "text": text, "link": link, "mood": mood})

    if task_total > 0 and (task_done / task_total) < 0.5:
        suggestions.append({"emoji": "✅", "text": "You complete less than 50% of your tasks. Try setting just 1-2 tasks per day instead of many — small wins build momentum.", "link": "/todo", "mood": "tasks"})
    if journals < 10:
        suggestions.append({"emoji": "📖", "text": "You have journaled fewer than 10 times. Users who journal 3x per week report 25% lower stress levels after 30 days.", "link": "/journal", "mood": "journal"})

    return suggestions[:5]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

@app.route("/feedback")
@login_required
def feedback_page() -> Any:
    return render_template("feedback.html", username=session["username"])


@app.route("/submit_feedback", methods=["POST"])
@login_required
def submit_feedback() -> Any:
    rating   = request.form.get("rating", "")
    category = request.form.get("category", "")
    message  = request.form.get("message", "").strip()

    if not message:
        flash("Please write your feedback before submitting.")
        return redirect(url_for("feedback_page"))

    with get_db() as conn:
        conn.execute(
            "INSERT INTO feedback (user_id, rating, category, message) VALUES (?,?,?,?)",
            (session["user_id"], rating, category, message),
        )
    flash("Thank you for your feedback! It helps us make Solace better. 💙")
    return redirect(url_for("feedback_page"))


# ---------------------------------------------------------------------------
# Static Pages
# ---------------------------------------------------------------------------

@app.route("/about")
def about() -> Any:
    return render_template("static_pages.html", page="about")

@app.route("/contact")
def contact() -> Any:
    return render_template("static_pages.html", page="contact")

@app.route("/disclaimer")
def disclaimer() -> Any:
    return render_template("static_pages.html", page="disclaimer")

@app.route("/privacy")
def privacy() -> Any:
    return render_template("static_pages.html", page="privacy")

@app.route("/terms")
def terms() -> Any:
    return render_template("static_pages.html", page="terms")


# ---------------------------------------------------------------------------
# Community — Animal Identity System
# ---------------------------------------------------------------------------

ANIMALS = [
    # (name, emoji, traits) — assigned based on user data
    ("Owl",        "🦉", "wise"),
    ("Dolphin",    "🐬", "social"),
    ("Fox",        "🦊", "resilient"),
    ("Elephant",   "🐘", "empathetic"),
    ("Butterfly",  "🦋", "transformative"),
    ("Wolf",       "🐺", "strong"),
    ("Deer",       "🦌", "gentle"),
    ("Phoenix",    "🦅", "rising"),
    ("Turtle",     "🐢", "steady"),
    ("Panda",      "🐼", "calm"),
    ("Lion",       "🦁", "brave"),
    ("Penguin",    "🐧", "resilient"),
    ("Rabbit",     "🐇", "hopeful"),
    ("Bear",       "🐻", "grounding"),
    ("Swan",       "🦢", "graceful"),
    ("Tiger",      "🐯", "fierce"),
    ("Koala",      "🐨", "soothing"),
    ("Crow",       "🐦", "perceptive"),
]


def get_user_animal(user_id: int) -> tuple[str, str]:
    """Assign a consistent animal identity based on user_id + data."""
    with get_db() as conn:
        mood_count = conn.execute(
            "SELECT COUNT(*) FROM mood_logs WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        top_mood_row = conn.execute(
            """SELECT mood FROM mood_logs WHERE user_id=?
               GROUP BY mood ORDER BY COUNT(*) DESC LIMIT 1""", (user_id,)
        ).fetchone()
        journal_count = conn.execute(
            "SELECT COUNT(*) FROM journals WHERE user_id=?", (user_id,)
        ).fetchone()[0]

    top_mood = top_mood_row["mood"] if top_mood_row else "calm"

    # Deterministic index from user_id + mood data
    seed = user_id * 7 + mood_count * 3 + journal_count * 2
    # Mood-based nudge
    mood_nudge = {
        "happy": 0, "calm": 9, "sad": 6, "angry": 5,
        "anxious": 2, "stressed": 11, "tired": 13,
        "imagination": 7, "swings": 7,
    }
    seed += mood_nudge.get(top_mood, 0)
    animal = ANIMALS[seed % len(ANIMALS)]
    return animal[0], animal[1]


MOOD_ROOMS = {
    "happy":    {"label": "Joy Room",         "emoji": "😊", "color": "#FFD700", "bg": "#FFFDE7"},
    "calm":     {"label": "Peace Corner",     "emoji": "😌", "color": "#66BB6A", "bg": "#F1F8E9"},
    "sad":      {"label": "Healing Space",    "emoji": "😞", "color": "#4FC3F7", "bg": "#E1F5FE"},
    "angry":    {"label": "Reset Room",       "emoji": "😡", "color": "#EF5350", "bg": "#FFF5F5"},
    "anxious":  {"label": "Breathe Zone",     "emoji": "😰", "color": "#AB47BC", "bg": "#F3E5F5"},
    "stressed": {"label": "Unwind Space",     "emoji": "😫", "color": "#FF7043", "bg": "#FBE9E7"},
    "tired":    {"label": "Rest Nook",        "emoji": "😴", "color": "#90A4AE", "bg": "#ECEFF1"},
    "imagination": {"label": "Rocket Wagon",  "emoji": "🎠", "color": "#FF69B4", "bg": "#FFF0F8"},
    "swings":   {"label": "Balance Board",    "emoji": "🎢", "color": "#FF7043", "bg": "#FFF3E0"},
    "general":  {"label": "General Stories",  "emoji": "🌟", "color": "#7c3aed", "bg": "#F5F3FF"},
}


@app.route("/community")
@login_required
def community() -> Any:
    room = request.args.get("room", "general")
    if room not in MOOD_ROOMS:
        room = "general"

    with get_db() as conn:
        if room == "general":
            posts = conn.execute("""
                SELECT cp.*, u.username FROM community_posts cp
                JOIN users u ON cp.user_id = u.id
                WHERE cp.status = 'approved'
                ORDER BY cp.created_at DESC
            """).fetchall()
        else:
            posts = conn.execute("""
                SELECT cp.*, u.username FROM community_posts cp
                JOIN users u ON cp.user_id = u.id
                WHERE cp.status = 'approved' AND cp.mood_room = ?
                ORDER BY cp.created_at DESC
            """, (room,)).fetchall()

        # Check which posts current user has liked
        liked_ids = set()
        liked_rows = conn.execute(
            "SELECT post_id FROM community_likes WHERE user_id=?",
            (session["user_id"],)
        ).fetchall()
        liked_ids = {r["post_id"] for r in liked_rows}

    animal_name, animal_emoji = get_user_animal(session["user_id"])

    return render_template(
        "community.html",
        posts=posts,
        rooms=MOOD_ROOMS,
        current_room=room,
        animal_name=animal_name,
        animal_emoji=animal_emoji,
        liked_ids=liked_ids,
        username=session["username"],
    )


@app.route("/community/post", methods=["POST"])
@login_required
def community_post() -> Any:
    title    = request.form.get("title", "").strip()
    story    = request.form.get("story", "").strip()
    room     = request.form.get("mood_room", "general")

    if not title or not story:
        flash("Title and story are required.")
        return redirect(url_for("community", room=room))

    if len(story) < 50:
        flash("Your story must be at least 50 characters — share a bit more! 💙")
        return redirect(url_for("community", room=room))

    animal_name, animal_emoji = get_user_animal(session["user_id"])

    with get_db() as conn:
        conn.execute("""
            INSERT INTO community_posts
            (user_id, mood_room, title, story, animal_name, animal_emoji, status)
            VALUES (?,?,?,?,?,?,'pending')
        """, (session["user_id"], room, title, story, animal_name, animal_emoji))

    flash("Your story has been submitted for review. It will appear once approved by the admin. 🌟")
    return redirect(url_for("community", room=room))


@app.route("/community/like/<int:post_id>", methods=["POST"])
@login_required
def community_like(post_id: int) -> Any:
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM community_likes WHERE post_id=? AND user_id=?",
            (post_id, session["user_id"])
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM community_likes WHERE post_id=? AND user_id=?",
                (post_id, session["user_id"])
            )
            conn.execute(
                "UPDATE community_posts SET likes = likes - 1 WHERE id=?", (post_id,)
            )
            liked = False
        else:
            conn.execute(
                "INSERT INTO community_likes (post_id, user_id) VALUES (?,?)",
                (post_id, session["user_id"])
            )
            conn.execute(
                "UPDATE community_posts SET likes = likes + 1 WHERE id=?", (post_id,)
            )
            liked = True

    return jsonify({"liked": liked})


# ---------------------------------------------------------------------------
# Admin — Community moderation
# ---------------------------------------------------------------------------

@app.route("/admin/community")
@admin_required
def admin_community() -> Any:
    status_filter = request.args.get("status", "pending")
    with get_db() as conn:
        posts = conn.execute("""
            SELECT cp.*, u.username, u.email FROM community_posts cp
            JOIN users u ON cp.user_id = u.id
            WHERE cp.status = ?
            ORDER BY cp.created_at DESC
        """, (status_filter,)).fetchall()
        counts = conn.execute("""
            SELECT status, COUNT(*) as cnt FROM community_posts GROUP BY status
        """).fetchall()

    count_map = {r["status"]: r["cnt"] for r in counts}
    return render_template(
        "admin/community.html",
        posts=posts,
        rooms=MOOD_ROOMS,
        status_filter=status_filter,
        count_map=count_map,
    )


@app.route("/admin/community/<int:post_id>/approve", methods=["POST"])
@admin_required
def approve_community_post(post_id: int) -> Any:
    with get_db() as conn:
        conn.execute(
            "UPDATE community_posts SET status='approved' WHERE id=?", (post_id,)
        )
    flash("Post approved and published to the community.")
    return redirect(url_for("admin_community"))


@app.route("/admin/community/<int:post_id>/reject", methods=["POST"])
@admin_required
def reject_community_post(post_id: int) -> Any:
    with get_db() as conn:
        conn.execute(
            "UPDATE community_posts SET status='rejected' WHERE id=?", (post_id,)
        )
    flash("Post rejected.")
    return redirect(url_for("admin_community"))


@app.route("/admin/community/<int:post_id>/delete", methods=["POST"])
@admin_required
def delete_community_post(post_id: int) -> Any:
    with get_db() as conn:
        conn.execute("DELETE FROM community_likes WHERE post_id=?", (post_id,))
        conn.execute("DELETE FROM community_posts WHERE id=?", (post_id,))
    flash("Post deleted.")
    return redirect(url_for("admin_community"))


@app.route("/admin")
@admin_required
def admin_dashboard() -> Any:
    with get_db() as conn:
        # Core stats
        total_users      = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_moods      = conn.execute("SELECT COUNT(*) FROM mood_logs").fetchone()[0]
        total_journals   = conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0]
        total_chats      = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
        total_posts      = conn.execute("SELECT COUNT(*) FROM community_posts").fetchone()[0]
        # New feature stats
        total_letters    = conn.execute("SELECT COUNT(*) FROM unsent_letters").fetchone()[0]
        total_vents      = conn.execute("SELECT COUNT(*) FROM venting_sessions").fetchone()[0]
        total_memories   = conn.execute("SELECT COUNT(*) FROM rocket_wagon").fetchone()[0]
        total_challenges = conn.execute("SELECT COUNT(*) FROM daily_challenges WHERE completed=1").fetchone()[0]
        # 3AM sessions count
        total_3am        = conn.execute("""
            SELECT COUNT(*) FROM chat_history
            WHERE strftime('%H', timestamp) IN ('01','02','03','04')
        """).fetchone()[0]
        # Mood breakdown today
        mood_today = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE DATE(timestamp) = DATE('now')
            GROUP BY mood ORDER BY cnt DESC
        """).fetchall()
        # Imagination mood count
        total_imagination = conn.execute(
            "SELECT COUNT(*) FROM mood_logs WHERE mood='imagination'"
        ).fetchone()[0]

        recent_users = conn.execute(
            "SELECT id, username, email, is_admin, created_at, gender, age FROM users ORDER BY created_at DESC LIMIT 6"
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
        recent_letters = conn.execute("""
            SELECT ul.*, u.username FROM unsent_letters ul
            JOIN users u ON ul.user_id=u.id
            ORDER BY ul.created_at DESC LIMIT 5
        """).fetchall()
        recent_vents = conn.execute("""
            SELECT vs.*, u.username FROM venting_sessions vs
            JOIN users u ON vs.user_id=u.id
            ORDER BY vs.created_at DESC LIMIT 5
        """).fetchall()
        recent_memories = conn.execute("""
            SELECT rw.*, u.username FROM rocket_wagon rw
            JOIN users u ON rw.user_id=u.id
            ORDER BY rw.created_at DESC LIMIT 5
        """).fetchall()
        # Active streaks
        top_streaks = conn.execute("""
            SELECT u.username, ls.current_streak, ls.longest_streak, ls.total_logins
            FROM login_streaks ls JOIN users u ON ls.user_id=u.id
            ORDER BY ls.current_streak DESC LIMIT 5
        """).fetchall()

    return render_template(
        "admin/dashboard.html",
        total_users=total_users, total_moods=total_moods,
        total_journals=total_journals, total_chats=total_chats,
        total_posts=total_posts, total_letters=total_letters,
        total_vents=total_vents, total_memories=total_memories,
        total_challenges=total_challenges, total_3am=total_3am,
        total_imagination=total_imagination,
        mood_today=mood_today,
        recent_users=recent_users, recent_moods=recent_moods,
        recent_chats=recent_chats, recent_letters=recent_letters,
        recent_vents=recent_vents, recent_memories=recent_memories,
        top_streaks=top_streaks,
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


@app.route("/admin/tasks")
@admin_required
def admin_tasks() -> Any:
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
            "SELECT username, email, created_at, gender, age, age_group FROM users WHERE id=?", (uid,)
        ).fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404
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
        "member_since":  (user["created_at"] or "")[:10] if user["created_at"] else "2026",
        "gender":        user["gender"] or "",
        "age":           user["age"] or 0,
        "age_group":     user["age_group"] or "",
        "mood_count":    mood_count,
        "journal_count": journal_count,
        "task_count":    task_count,
        "days_active":   days_active,
        "top_mood":      top_mood,
        "top_mood_pct":  top_mood_pct,
        "calendar":      [{"date": r["date"], "mood": r["mood"]} for r in calendar],
        "recent_moods":  [{"mood": r["mood"], "time": r["timestamp"]} for r in recent],
    })


# ===========================================================================
# 3 AM BUTTON
# ===========================================================================

@app.route("/three-am")
@login_required
def three_am_page() -> Any:
    from datetime import datetime
    hour = datetime.now().hour
    # Only accessible between 1AM and 4AM (hours 1, 2, 3)
    if hour < 1 or hour >= 4:
        return render_template(
            "three_am.html",
            username=session["username"],
            hour=hour,
            streak=0,
            current_mood=session.get("current_mood", "neutral"),
            locked=True
        )
    uid  = session["user_id"]
    with get_db() as conn:
        streak = conn.execute(
            "SELECT current_streak FROM login_streaks WHERE user_id=?", (uid,)
        ).fetchone()
    return render_template(
        "three_am.html",
        username=session["username"],
        hour=hour,
        streak=streak["current_streak"] if streak else 0,
        current_mood=session.get("current_mood", "neutral"),
        locked=False
    )


@app.route("/three-am-message", methods=["POST"])
@login_required
def three_am_message() -> Any:
    data     = request.json or {}
    user_msg = data.get("message", "")
    uid      = session["user_id"]
    msg      = user_msg.lower().strip()

    # Special late-night Eva persona — responds to WHAT user actually said
    system_prompt = (
        "You are Eva — and right now it is 3 AM. The user has come to you in the middle of the night. "
        "This is your most sacred mode. Be slower. Be softer. Be more present than ever. "
        "CRITICAL: Read what the user ACTUALLY said and respond to THAT specifically. "
        "Do not give generic comfort. Do not repeat yourself. "
        "If they say 'thank you' — acknowledge it warmly and gently ask what brought them here. "
        "If they say 'bye' or 'goodbye' — wish them rest and peace for the night. "
        "If they share feelings — reflect exactly what they shared back to them with warmth. "
        "If they share a worry — acknowledge that specific worry, not a generic response. "
        "If they ask a question — answer it softly. "
        "Match the stillness of the night. Speak in 3-5 sentences. "
        "Soft. Warm. Personal. Like a hand held in the dark. "
        "Never repeat a response you have already given in this conversation. "
        "User message: " + user_msg
    )

    text = ""
    if GEMINI_API_KEY:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 350}
            }
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[3AM] Gemini error: {e}")

    # Smart keyword-based fallback — reads what user ACTUALLY said
    if not text:
        STOP = {"the","a","an","is","was","it","and","or","but","to","of","in","that","this","with","my","me","i"}

        if any(w in msg for w in ["thank","thanks","appreciate","helped","better"]):
            text = "I'm glad you're here. This moment — you reaching out at this hour — it means something. What brought you here tonight? I want to understand."
        elif any(w in msg for w in ["bye","goodbye","good night","sleep","going","leaving","tired"]):
            text = "Rest now. The night always ends, and you will wake up on the other side of this. I'm proud of you for finding your way here. Sleep gently."
        elif any(w in msg for w in ["cant sleep","cannot sleep","insomnia","awake","no sleep"]):
            text = "The night keeps some of us up for a reason — sometimes our mind is trying to process something it hasn't finished with yet. You don't have to force sleep. Just breathe slowly. I'm here."
        elif any(w in msg for w in ["alone","lonely","nobody","no one","empty","miss"]):
            text = "Loneliness at 3 AM is one of the heaviest feelings. But you found your way here, and I am right here with you. You are not as alone as the night makes you feel."
        elif any(w in msg for w in ["scared","afraid","fear","anxious","panic","worried","worry"]):
            text = "Fear visits us most at night, when the world is quiet and our thoughts get loud. Take one slow breath. Whatever is scaring you — it does not have to be solved right now. Just breathe. I'm with you."
        elif any(w in msg for w in ["sad","cry","crying","tears","hurt","pain","broken"]):
            text = "There is no shame in tears at 3 AM. Some of the most honest feelings only come when the world is quiet. I hear you. What you are feeling is real, and it matters."
        elif any(w in msg for w in ["angry","mad","frustrated","hate","unfair"]):
            text = "Something is burning in you right now. That is okay. The night holds all of it — your anger, your frustration, everything. You don't have to contain it here."
        elif any(w in msg for w in ["help","need","struggling","hard","difficult","tough","cant"]):
            text = "Something is hard right now and you came here instead of sitting with it alone — that took courage. I'm listening. What is making things feel so heavy tonight?"
        elif any(w in msg for w in ["ok","okay","fine","alright","just","nothing","idk","dunno"]):
            text = "3 AM has a way of pulling people out of bed even when they say they are fine. I'm here if something is sitting with you, even if you can't name it yet. The night is quiet — we can just sit here together."
        elif len(msg) <= 5:
            text = "I hear you. Even one word in the dark takes courage. I'm here — take your time. You don't have to say anything you're not ready to say."
        else:
            # Reflect what they actually said back to them
            words = [w for w in msg.split() if w not in STOP and len(w) > 2]
            if words:
                key_word = words[0]
                responses = [
                    f"When you say '{key_word}' at 3 AM — I want you to know I heard that. The night has a way of making everything feel larger. I'm here with you in it.",
                    f"Something about '{key_word}' brought you here tonight. Whatever it is, you don't have to carry it alone in the dark. I'm listening.",
                    f"I hear '{key_word}' and I feel the weight behind it. Tell me more if you want — or we can just sit here quietly. Either way, you are not alone.",
                ]
            else:
                responses = [
                    "Whatever you are carrying right now — the night does not have to hold it alone. I am here.",
                    "Something brought you here at this hour. Take your time. I'm not going anywhere.",
                    "The 3 AM version of you is brave for reaching out. I see you. I'm here.",
                ]
            import random as _rand
            text = _rand.choice(responses)

    with get_db() as conn:
        conn.execute(
            "INSERT INTO chat_history (session_id, user_id, user_message, ai_response) VALUES (?,?,?,?)",
            (str(uuid.uuid4()), uid, user_msg, text)
        )

    return jsonify({"reply": text})


# ===========================================================================
# UNSENT LETTERS
# ===========================================================================

@app.route("/unsent-letter")
@login_required
def unsent_letter_page() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        letters = conn.execute(
            "SELECT * FROM unsent_letters WHERE user_id=? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()
    return render_template(
        "unsent_letter.html",
        username=session["username"],
        letters=letters,
        current_mood=session.get("current_mood", "neutral")
    )


@app.route("/unsent-letter/send", methods=["POST"])
@login_required
def send_unsent_letter() -> Any:
    data         = request.json or {}
    addressed_to = data.get("addressed_to", "").strip()
    letter       = data.get("letter", "").strip()
    uid          = session["user_id"]

    if not letter:
        return jsonify({"error": "Letter cannot be empty."}), 400

    # Eva reads the letter and responds to what was unsaid
    system_prompt = (
        f"The user has just written an unsent letter addressed to '{addressed_to}'. "
        "This letter will never be sent. They wrote it to release something they could not say out loud. "
        "Your job is to respond as Eva — not as the person the letter was addressed to. "
        "Acknowledge the courage it took to write this. "
        "Reflect back the emotional core of what they expressed — the pain, the longing, the anger, or the love. "
        "Do not give advice. Do not tell them what to do next. "
        "Just honour what they wrote. Make them feel that their words mattered. "
        "Speak in 4-6 sentences. Warm, gentle, and deeply human."
        f"\n\nThe letter they wrote:\n{letter}"
    )

    eva_reply = ""
    if GEMINI_API_KEY:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 400}
            }
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 200:
                eva_reply = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[UnsentLetter] Gemini error: {e}")

    if not eva_reply:
        import random
        eva_reply = random.choice([
            f"What you wrote to {addressed_to or 'them'} took real courage. The words you chose — even unsent — are real. They existed. They mattered. Sometimes the most honest things we say are the ones never spoken aloud. I heard every word.",
            f"There is something sacred about a letter that never gets sent. It means the words were written for you — to release what was sitting inside you. What you expressed here is valid and true. You deserved to say it.",
            "Writing it down means it was real. You gave your feelings a shape, a form, a voice. That is not nothing — that is everything. I'm honoured you shared it here.",
        ])

    with get_db() as conn:
        conn.execute(
            "INSERT INTO unsent_letters (user_id, addressed_to, letter, eva_reply) VALUES (?,?,?,?)",
            (uid, addressed_to, letter, eva_reply)
        )

    return jsonify({"eva_reply": eva_reply, "message": "Letter saved."})


@app.route("/unsent-letter/delete/<int:lid>", methods=["POST"])
@login_required
def delete_unsent_letter(lid: int) -> Any:
    with get_db() as conn:
        conn.execute(
            "DELETE FROM unsent_letters WHERE id=? AND user_id=?",
            (lid, session["user_id"])
        )
    return jsonify({"message": "Letter released."})


# ===========================================================================
# SOUL MIRROR — compute dominant mood from last 7 days
# ===========================================================================

@app.route("/soul-mirror-data")
@login_required
def soul_mirror_data() -> Any:
    uid  = session["user_id"]
    with get_db() as conn:
        rows = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now','-7 days')
            GROUP BY mood ORDER BY cnt DESC
        """, (uid,)).fetchall()
        total_7 = conn.execute(
            "SELECT COUNT(*) FROM mood_logs WHERE user_id=? AND timestamp >= DATE('now','-7 days')",
            (uid,)
        ).fetchone()[0]

    heavy_moods = {"sad", "anxious", "stressed", "angry", "imagination", "swings", "tired"}
    dominant    = rows[0]["mood"] if rows else "neutral"
    heavy_days  = sum(r["cnt"] for r in rows if r["mood"] in heavy_moods)

    MIRROR_MESSAGES = {
        "sad":      "I've noticed it's been a heavy week. I've dimmed the lights and prepared a quiet space just for you.",
        "anxious":  "Your week has felt restless. I've slowed everything down — breathe with me for a moment.",
        "stressed": "You've been carrying a lot lately. I've cleared the noise. This space is just for you right now.",
        "angry":    "This week held some fire. I've made space for that energy — you're allowed to feel it.",
        "tired":    "You've been running on empty. I've made things softer and slower here, just for you.",
        "imagination": "Your imagination has been active this week — I can feel it. This space is full of colour and wonder, just for you.",
        "calm":     "You've found some peace this week. I'm reflecting that back to you — this is your energy.",
        "happy":    "What a bright week you've had. I'm matching your energy — let's celebrate this.",
        "swings":   "It's been an up-and-down week. I'm here for all of it — every version of you is welcome.",
    }

    message = MIRROR_MESSAGES.get(dominant, "I see you. This space is yours.")

    return jsonify({
        "dominant_mood": dominant,
        "heavy_days":    heavy_days,
        "total_7":       total_7,
        "mirror_message": message,
        "moods_breakdown": [{"mood": r["mood"], "count": r["cnt"]} for r in rows],
    })


# ===========================================================================
# VENTING CHAMBER
# ===========================================================================

@app.route("/venting-chamber")
@login_required
def venting_chamber_page() -> Any:
    return render_template(
        "venting_chamber.html",
        username=session["username"],
        current_mood=session.get("current_mood", "neutral")
    )


@app.route("/vent-complete", methods=["POST"])
@login_required
def vent_complete() -> Any:
    # PRIVACY: Venting sessions are voice-only — NO transcript or keyword data is stored.
    # The POST body is intentionally ignored to ensure zero data retention.

    # Eva gives a closing acknowledgment after the vent
    system_prompt = (
        "The user just finished a venting session using their voice. "
        "They spoke out loud to release their emotions — they were not having a conversation. "
        "Now they have finished. Your job is to give a closing acknowledgment — "
        "like a gentle exhale after a storm. "
        "Tell them what they just did took courage. "
        "Tell them the words are released now and will not be stored or remembered. "
        "Do not reference specific content of what they said. "
        "Speak in 2-3 sentences. Calm. Closing. Like the end of something heavy."
    )

    closing = ""
    if GEMINI_API_KEY:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {"temperature": 0.85, "maxOutputTokens": 200}
            }
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 200:
                closing = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[Vent] Gemini error: {e}")

    if not closing:
        import random
        closing = random.choice([
            "You said what needed to be said. It's out now — and it stays between you and the air. Take a breath.",
            "That took courage. Whatever was inside you, you gave it a voice. Nothing was recorded — it's yours, and it's released.",
            "The words are released and forgotten. Something lighter is on the other side of this moment.",
        ])

    return jsonify({"closing": closing})


# ===========================================================================
# REVERSE JOURNALING — AI letter from future self
# ===========================================================================

@app.route("/reverse-journal")
@login_required
def reverse_journal_page() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        mood_this_week = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now','-7 days')
            GROUP BY mood ORDER BY cnt DESC LIMIT 1
        """, (uid,)).fetchone()
        tasks_done = conn.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE user_id=? AND status=1
            AND created_at >= DATE('now','-7 days')
        """, (uid,)).fetchone()[0]
        journals_written = conn.execute("""
            SELECT COUNT(*) FROM journals
            WHERE user_id=? AND created_at >= DATE('now','-7 days')
        """, (uid,)).fetchone()[0]
        streak_row = conn.execute(
            "SELECT current_streak FROM login_streaks WHERE user_id=?", (uid,)
        ).fetchone()

    dominant_mood = mood_this_week["mood"] if mood_this_week else "neutral"
    streak        = streak_row["current_streak"] if streak_row else 0

    return render_template(
        "reverse_journal.html",
        username=session["username"],
        dominant_mood=dominant_mood,
        tasks_done=tasks_done,
        journals_written=journals_written,
        streak=streak,
        current_mood=session.get("current_mood", "neutral")
    )


@app.route("/generate-future-letter", methods=["POST"])
@login_required
def generate_future_letter() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        # Check if user has been active for at least 7 days
        days_active = conn.execute(
            "SELECT COUNT(DISTINCT DATE(timestamp)) FROM mood_logs WHERE user_id=?",
            (uid,)
        ).fetchone()[0]
    if days_active < 7:
        days_left = 7 - days_active
        return jsonify({
            "error": f"Your letter unlocks after 7 days of use. You have {days_active} day{'s' if days_active != 1 else ''} so far. {days_left} more day{'s' if days_left != 1 else ''} to go!",
            "days_active": days_active,
            "days_needed": 7,
            "locked": True
        }), 200
    with get_db() as conn:
        mood_rows = conn.execute("""
            SELECT mood, COUNT(*) as cnt FROM mood_logs
            WHERE user_id=? AND timestamp >= DATE('now','-7 days')
            GROUP BY mood ORDER BY cnt DESC
        """, (uid,)).fetchall()
        tasks_done = conn.execute("""
            SELECT title FROM tasks
            WHERE user_id=? AND status=1
            AND created_at >= DATE('now','-7 days')
            LIMIT 5
        """, (uid,)).fetchall()
        journals = conn.execute("""
            SELECT morning_text FROM journals
            WHERE user_id=? AND created_at >= DATE('now','-7 days')
            LIMIT 3
        """, (uid,)).fetchall()
        streak_row = conn.execute(
            "SELECT current_streak FROM login_streaks WHERE user_id=?", (uid,)
        ).fetchone()

    username      = session["username"]
    dominant_mood = mood_rows[0]["mood"] if mood_rows else "neutral"
    streak        = streak_row["current_streak"] if streak_row else 0
    task_titles   = [t["title"] for t in tasks_done] if tasks_done else []
    journal_texts = [j["morning_text"] for j in journals if j["morning_text"]] if journals else []

    system_prompt = (
        f"You are writing a letter FROM {username}'s future self — one year from now. "
        f"This week, {username} had the following data: "
        f"Dominant mood: {dominant_mood}. "
        f"Login streak: {streak} days. "
        f"Tasks completed this week: {', '.join(task_titles) if task_titles else 'none listed'}. "
        f"Journal entries this week: {len(journal_texts)}. "
        f"{'Sample journal: ' + journal_texts[0][:150] if journal_texts else ''} "
        f"\n\nWrite a warm, personal letter from their future self. "
        f"Reference specific details from this week — the mood, the streak, the tasks. "
        f"Tell them what this week meant from the perspective of a year later. "
        f"Tell them what grew from this difficult or ordinary week. "
        f"Be emotional, personal, and specific. Use 'I' as the future self speaking to 'you' (the present self). "
        f"Write 5-8 sentences. Make it feel like it was written by a real person who loves them deeply."
    )

    letter = ""
    if GEMINI_API_KEY:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {"temperature": 0.95, "maxOutputTokens": 600}
            }
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                letter = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[ReverseJournal] Gemini error: {e}")

    if not letter:
        letter = (
            f"Dear {username}, I'm writing to you from a year from now. "
            f"I remember this week — you were feeling {dominant_mood}, and you showed up anyway. "
            f"You kept your streak going for {streak} days. That mattered more than you knew. "
            f"I can tell you now: that version of you, tired and uncertain, was building something real. "
            f"The person writing this letter exists because you didn't give up that week. "
            f"I'm proud of you. I love you. Keep going."
        )

    return jsonify({"letter": letter, "username": username})




# ===========================================================================
# ADMIN — Unsent Letters & Venting Sessions
# ===========================================================================

@app.route("/admin/unsent-letters")
@admin_required
def admin_unsent_letters() -> Any:
    with get_db() as conn:
        letters = conn.execute("""
            SELECT ul.*, u.username, u.email
            FROM unsent_letters ul
            JOIN users u ON ul.user_id = u.id
            ORDER BY ul.created_at DESC
        """).fetchall()
    return render_template("admin/unsent_letters.html", letters=letters)


@app.route("/admin/venting-sessions")
@admin_required
def admin_venting_sessions() -> Any:
    with get_db() as conn:
        sessions = conn.execute("""
            SELECT vs.*, u.username, u.email
            FROM venting_sessions vs
            JOIN users u ON vs.user_id = u.id
            ORDER BY vs.created_at DESC
        """).fetchall()
    return render_template("admin/venting_sessions.html", sessions=sessions)


@app.route("/admin/three-am-logs")
@admin_required
def admin_three_am_logs() -> Any:
    with get_db() as conn:
        # 3AM chats are stored in chat_history — filter by hour
        logs = conn.execute("""
            SELECT ch.*, u.username, u.email
            FROM chat_history ch
            JOIN users u ON ch.user_id = u.id
            WHERE strftime('%H', ch.timestamp) IN ('00','01','02','03','04')
            ORDER BY ch.timestamp DESC
            LIMIT 100
        """).fetchall()
    return render_template("admin/three_am_logs.html", logs=logs)



# ===========================================================================
# ROCKET WAGON — Imagination Memory Archive
# ===========================================================================

@app.route("/rocket-wagon")
@login_required
def rocket_wagon_page() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        memories = conn.execute(
            "SELECT * FROM rocket_wagon WHERE user_id=? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()
        # Count recent adult/heavy moods to calculate fade level
        heavy_count = conn.execute("""
            SELECT COUNT(*) FROM mood_logs
            WHERE user_id=? AND mood IN ('stressed','anxious','angry','tired')
            AND timestamp >= DATE('now','-7 days')
        """, (uid,)).fetchone()[0]
    # Fade factor: more heavy moods = more transparent memories
    fade_factor = min(heavy_count * 0.08, 0.5)  # max 50% fade
    return render_template(
        "rocket_wagon.html",
        username=session["username"],
        memories=memories,
        fade_factor=fade_factor,
        heavy_count=heavy_count,
    )


@app.route("/rocket-wagon/add", methods=["POST"])
@login_required
def add_rocket_memory() -> Any:
    data    = request.json or {}
    title   = data.get("title", "").strip()
    text    = data.get("text", "").strip()
    dream   = data.get("childhood_dream", "").strip()
    uid     = session["user_id"]

    if not title or not text:
        return jsonify({"error": "Title and memory are required."}), 400

    # If user restores a memory (completes creative task) increase all opacities
    with get_db() as conn:
        conn.execute(
            "INSERT INTO rocket_wagon (user_id, memory_title, memory_text, childhood_dream) VALUES (?,?,?,?)",
            (uid, title, text, dream)
        )
        # Boost existing memories opacity slightly (creative act restores memories)
        conn.execute("""
            UPDATE rocket_wagon SET opacity = MIN(1.0, opacity + 0.15)
            WHERE user_id=?
        """, (uid,))

    return jsonify({"message": "Memory saved to the Rocket Wagon! 🎠"}), 201


@app.route("/rocket-wagon/delete/<int:mid>", methods=["POST"])
@login_required
def delete_rocket_memory(mid: int) -> Any:
    with get_db() as conn:
        conn.execute(
            "DELETE FROM rocket_wagon WHERE id=? AND user_id=?",
            (mid, session["user_id"])
        )
    return jsonify({"message": "Memory released."}), 200


@app.route("/rocket-wagon/restore", methods=["POST"])
@login_required
def restore_memories() -> Any:
    """Called when user completes a creative task or journals about childhood dream."""
    uid = session["user_id"]
    with get_db() as conn:
        conn.execute("""
            UPDATE rocket_wagon SET opacity = MIN(1.0, opacity + 0.25)
            WHERE user_id=?
        """, (uid,))
    return jsonify({"message": "Memories brightened! Your creativity is bringing them back. ✨"}), 200



@app.route("/admin/rocket-wagon")
@admin_required
def admin_rocket_wagon() -> Any:
    with get_db() as conn:
        memories = conn.execute("""
            SELECT rw.*, u.username, u.email
            FROM rocket_wagon rw JOIN users u ON rw.user_id=u.id
            ORDER BY rw.created_at DESC
        """).fetchall()
    return render_template("admin/rocket_wagon.html", memories=memories)


@app.route("/admin/imagination-logs")
@admin_required
def admin_imagination_logs() -> Any:
    with get_db() as conn:
        logs = conn.execute("""
            SELECT ml.*, u.username, u.email
            FROM mood_logs ml JOIN users u ON ml.user_id=u.id
            WHERE ml.mood='imagination'
            ORDER BY ml.timestamp DESC
        """).fetchall()
    return render_template("admin/imagination_logs.html", logs=logs)



# ===========================================================================
# IMAGINATION — Sketch Posts (Memory Sketchbook)
# ===========================================================================

@app.route("/sketch/post", methods=["POST"])
@login_required
def post_sketch() -> Any:
    data       = request.json or {}
    image_data = data.get("image", "")
    mood       = data.get("mood", "imagination")
    prompt     = data.get("prompt", "")
    uid        = session["user_id"]

    if not image_data:
        return jsonify({"error": "No image data received."}), 400

    # Store base64 image in sketch_posts table
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sketch_posts (user_id, image_data, mood, prompt) VALUES (?,?,?,?)",
            (uid, image_data, mood, prompt)
        )

    return jsonify({"message": "Your sketch is now live in the Imagination Community! 🎨"}), 201


@app.route("/sketch/feed")
@login_required
def sketch_feed() -> Any:
    """Returns sketches posted by users in imagination mood — only visible to imagination mood users."""
    uid          = session["user_id"]
    current_mood = session.get("current_mood", "neutral")

    with get_db() as conn:
        sketches = conn.execute("""
            SELECT sp.id, sp.image_data, sp.prompt, sp.created_at,
                   u.username
            FROM sketch_posts sp
            JOIN users u ON sp.user_id = u.id
            WHERE sp.mood = 'imagination'
            ORDER BY sp.created_at DESC
            LIMIT 20
        """).fetchall()

    return jsonify({
        "sketches": [
            {
                "id":        s["id"],
                "username":  s["username"],
                "prompt":    s["prompt"],
                "image":     s["image_data"],
                "date":      (s["created_at"] or "")[:10],
            }
            for s in sketches
        ],
        "visible_to_imagination_only": True
    })


# ===========================================================================
# IMAGINATION — Cloud Visions
# ===========================================================================

@app.route("/cloud-vision/save", methods=["POST"])
@login_required
def save_cloud_vision() -> Any:
    data         = request.json or {}
    vision_text  = data.get("vision", "").strip()
    cloud_emoji  = data.get("cloud_emoji", "☁️")
    uid          = session["user_id"]

    if not vision_text:
        return jsonify({"error": "Vision text is required."}), 400

    with get_db() as conn:
        conn.execute(
            "INSERT INTO cloud_visions (user_id, vision_text, cloud_emoji) VALUES (?,?,?)",
            (uid, vision_text, cloud_emoji)
        )

    return jsonify({"message": "Vision saved to your Rocket Wagon! ✨"}), 201


@app.route("/cloud-vision/list")
@login_required
def list_cloud_visions() -> Any:
    uid = session["user_id"]
    with get_db() as conn:
        visions = conn.execute(
            "SELECT cloud_emoji, vision_text, created_at FROM cloud_visions "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            (uid,)
        ).fetchall()

    return jsonify({
        "visions": [
            {"emoji": v["cloud_emoji"], "text": v["vision_text"], "date": (v["created_at"] or "")[:10]}
            for v in visions
        ]
    })



# ===========================================================================
# BOOKTOK — Imagination Community Book Sharing
# ===========================================================================

@app.route("/booktok/share", methods=["POST"])
@login_required
def booktok_share() -> Any:
    data   = request.json or {}
    uid    = session["user_id"]
    title  = data.get("title", "").strip()
    author = data.get("author", "").strip()
    genre  = data.get("genre", "General").strip()
    note   = data.get("note", "").strip()
    if not title:
        return jsonify({"error": "Book title is required."}), 400
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS booktok_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                title TEXT NOT NULL,
                author TEXT,
                genre TEXT DEFAULT 'General',
                note TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO booktok_posts (user_id, title, author, genre, note) VALUES (?,?,?,?,?)",
            (uid, title, author, genre, note)
        )
    return jsonify({"message": "Book shared with the Imagination community! 📚"}), 201


@app.route("/booktok/feed")
@login_required
def booktok_feed() -> Any:
    """Returns books shared by users in imagination mood — cozy community."""
    with get_db() as conn:
        try:
            books = conn.execute("""
                SELECT bp.id, bp.title, bp.author, bp.genre, bp.note,
                       bp.created_at, u.username
                FROM booktok_posts bp
                JOIN users u ON bp.user_id = u.id
                ORDER BY bp.created_at DESC
                LIMIT 30
            """).fetchall()
        except Exception:
            books = []
    return jsonify({
        "books": [
            {
                "id":     b["id"],
                "title":  b["title"],
                "author": b["author"] or "",
                "genre":  b["genre"] or "General",
                "note":   b["note"] or "",
                "user":   b["username"],
                "date":   (b["created_at"] or "")[:10],
            }
            for b in books
        ]
    })


if __name__ == "__main__":
    app.run(debug=True)