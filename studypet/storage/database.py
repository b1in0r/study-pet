"""One connection policy for tasks, reminders and personal documents."""
import sqlite3


def connect_database(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 5000')
    return db
