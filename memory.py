import sqlite3

db = "memory.db"


def init_memory():
    conn = sqlite3.connect(db)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS memories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT,
        value TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_memory(key, value):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    # Hapus memory lama dengan kategori/key yang sama
    c.execute(
        "DELETE FROM memories WHERE key=?",
        (key,)
    )

    # Simpan versi terbaru
    c.execute(
        "INSERT INTO memories (key, value) VALUES (?, ?)",
        (key, value)
    )

    conn.commit()
    conn.close()


def get_memory(key):
    conn = sqlite3.connect(db)
    c = conn.cursor()

    c.execute(
        "SELECT value FROM memories WHERE key=? ORDER BY id DESC LIMIT 1",
        (key,)
    )

    result = c.fetchone()

    conn.close()

    if result:
        return result[0]

    return None


def get_all_memory():
    conn = sqlite3.connect(db)
    c = conn.cursor()

    c.execute(
        "SELECT key, value FROM memories ORDER BY id ASC"
    )

    result = c.fetchall()

    conn.close()

    return result