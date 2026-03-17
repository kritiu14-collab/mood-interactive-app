import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Delete the old table if it exists
cursor.execute("DROP TABLE IF EXISTS tasks")

# Create the table with the EXACT names your code expects
cursor.execute('''
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        task_text TEXT NOT NULL,
        task_time TEXT NOT NULL,
        task_date TEXT NOT NULL,
        category TEXT NOT NULL,
        status INTEGER DEFAULT 0
    )
''')

conn.commit()
conn.close()
print("Database reset successful! Your columns now match your code.")