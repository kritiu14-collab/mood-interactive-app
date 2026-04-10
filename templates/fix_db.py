import sqlite3

# Replace 'database.db' with your actual database filename
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    conn.commit()
    print("Column added successfully!")
except sqlite3.OperationalError:
    print("Column might already exist.")

conn.close()