# database_manager.py
# Manages the SQLite database, now with support for user-defined sessions.

import sqlite3
import time
import os

class DatabaseManager:
    def __init__(self, db_name="focus_guardian.db"):
        """
        Initializes the database connection and cursor, and ensures the table schema is up to date.
        """
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        try:
            # Connect to the database file. It will be created if it doesn't exist.
            # `check_same_thread=False` is important for use in multi-threaded apps (like with Flask).
            self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
            self.cursor = self.conn.cursor()
            print(f"DB: Successfully connected to database '{self.db_name}'.")
            self.update_schema() # Changed from create_table to a more robust update function
        except sqlite3.Error as e:
            print(f"DB Error: Failed to connect to database: {e}")

    def update_schema(self):
        """
        Ensures the database table exists and has all the required columns.
        This is safer than just trying to create the table every time.
        """
        if not self.cursor: return
        try:
            # First, ensure the main table exists.
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
                    service_name TEXT,
                    user_feedback TEXT,
                    is_reviewed BOOLEAN DEFAULT 0
                )
            ''')
            
            # --- NEW: Add the session_id column if it's missing ---
            # This makes the script backward-compatible with older DB files.
            self.add_column_if_not_exists('activity_log', 'session_id', 'TEXT')
            
            self.conn.commit()
            print("DB: 'activity_log' table schema verified and up to date.")
        except sqlite3.Error as e:
            print(f"DB Error: Failed to create or update table: {e}")

    def add_column_if_not_exists(self, table_name, column_name, column_type):
        """
        A helper function to safely add a column to a table if it doesn't already exist.
        Prevents errors if the script is run with an older database file.
        """
        self.cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [info[1] for info in self.cursor.fetchall()]
        if column_name not in columns:
            print(f"DB: Schema update - Adding missing column '{column_name}' to table '{table_name}'...")
            self.cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            print(f"DB: Column '{column_name}' added successfully.")

    def log_activity(self, data_packet):
        """Inserts a new record into the activity_log table."""
        if not self.conn:
            print("DB Error: No database connection available for logging.")
            return
            
        sql = '''INSERT INTO activity_log(
                    timestamp, session_id, focus_status, focus_reason, emotion, 
                    app_name, window_title, ocr_content, service_name, 
                    productivity_label, is_reviewed
                 ) VALUES(?,?,?,?,?,?,?,?,?,?,?)''' # Now has 11 placeholders
        
        # Prepare the data tuple in the correct order for the SQL query
        log_data = (
            data_packet.get('timestamp', time.time()),
            data_packet.get('session_id'), # The new session ID
            data_packet.get('focus_status'),
            data_packet.get('focus_reason'),
            data_packet.get('emotion'),
            data_packet.get('app_name'),
            data_packet.get('window_title'),
            data_packet.get('ocr_content'),
            data_packet.get('service_name'),
            data_packet.get('productivity_label'),
            False  # is_reviewed always starts as False for new records
        )
        
        try:
            self.cursor.execute(sql, log_data)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"DB Error: Failed to insert record: {e}")

    def close(self):
        """Closes the database connection gracefully."""
        if self.conn:
            self.conn.close()
            print("DB: Database connection closed.")

# --- Standalone Test Block ---
if __name__ == '__main__':
    print("--- Running a standalone test for DatabaseManager ---")
    
    # Create a temporary test database
    TEST_DB_NAME = "test_db.db"
    if os.path.exists(TEST_DB_NAME):
        os.remove(TEST_DB_NAME)
        
    db_manager = DatabaseManager(db_name=TEST_DB_NAME)
    
    # Test logging a record
    print("\nAttempting to log a sample record...")
    sample_packet = {
        'timestamp': time.time(),
        'session_id': 'session_test_123',
        'focus_status': 'Focused',
        'emotion': 'neutral',
        'app_name': 'Code.exe',
        'window_title': 'test.py - VS Code',
        'ocr_content': 'print("hello world")',
        'service_name': 'VS Code',
        'productivity_label': 'Productive'
    }
    db_manager.log_activity(sample_packet)
    
    # Verify the record was inserted
    print("\nReading from the database to verify...")
    try:
        db_manager.cursor.execute("SELECT * FROM activity_log")
        rows = db_manager.cursor.fetchall()
        print(f"Found {len(rows)} record(s) in the log.")
        if rows:
            print("Sample record content:", rows[0])
            print("Test successful!")
        else:
            print("Test failed: No records found.")
    except Exception as e:
        print(f"Test failed during verification: {e}")
    finally:
        db_manager.close()
        if os.path.exists(TEST_DB_NAME):
            os.remove(TEST_DB_NAME)
            print(f"\nCleaned up test database '{TEST_DB_NAME}'.")