# database_manager.py
import sqlite3
import time
import os

class DatabaseManager:
    def __init__(self, db_name="focus_guardian.db"):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        try:
            # Connect to the database. It will be created if it doesn't exist.
            self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
            self.cursor = self.conn.cursor()
            print(f"DB: Successfully connected to database '{self.db_name}'.")
            self.create_table()
        except sqlite3.Error as e:
            print(f"DB Error: Failed to connect to database: {e}")

    def create_table(self):
        """Creates the main activity log table if it doesn't already exist."""
        if not self.cursor: return
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    focus_status TEXT,
                    focus_reason TEXT,
                    emotion TEXT,
                    app_name TEXT,
                    window_title TEXT,
                    ocr_content TEXT,
                    productivity_label TEXT,
                    user_feedback TEXT,
                    is_reviewed BOOLEAN DEFAULT 0
                )
            ''')
            self.conn.commit()
            print("DB: 'activity_log' table verified.")
        except sqlite3.Error as e:
            print(f"DB Error: Failed to create table: {e}")

    def log_activity(self, data_packet):
        """Inserts a new record into the activity_log table."""
        if not self.conn:
            print("DB Error: No database connection available for logging.")
            return
            
        sql = '''INSERT INTO activity_log(
                    timestamp, focus_status, focus_reason, emotion, 
                    app_name, window_title, ocr_content, productivity_label, is_reviewed
                 ) VALUES(?,?,?,?,?,?,?,?,?)'''
        
        # Prepare the data tuple in the correct order
        log_data = (
            data_packet.get('timestamp', time.time()),
            data_packet.get('focus_status'),
            data_packet.get('focus_reason'),
            data_packet.get('emotion'),
            data_packet.get('app_name'),
            data_packet.get('window_title'),
            data_packet.get('ocr_content'),
            data_packet.get('productivity_label'),
            False  # is_reviewed always starts as False
        )
        
        try:
            self.cursor.execute(sql, log_data)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"DB Error: Failed to insert record: {e}")

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            print("DB: Database connection closed.")