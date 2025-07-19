# analytics_engine.py (Standalone CLI Tool)
# Reads from the database for a specific session and prints a JSON summary.

import pandas as pd
import sqlite3
import sys
import json

# --- This script is now intended to be run from the command line ---

def calculate_session_summary(db_name, session_id):
    """
    Connects to the DB, performs all calculations, and returns a summary dictionary.
    """
    try:
        conn = sqlite3.connect(db_name)
        query = "SELECT * FROM activity_log WHERE session_id = ?"
        df = pd.read_sql_query(query, conn, params=(session_id,))
        conn.close()
    except Exception as e:
        return {"error": f"Failed to read database: {e}"}

    if df.empty:
        return {"error": "No data found for this session."}

    # Calculation logic (unchanged)
    session_start = pd.to_datetime(df['timestamp'].min(), unit='s')
    session_end = pd.to_datetime(df['timestamp'].max(), unit='s')
    total_duration_seconds = (session_end - session_start).total_seconds()
    
    analysis_interval = df['timestamp'].diff().median()
    if pd.isna(analysis_interval) or analysis_interval <= 0:
        analysis_interval = 5 # Default interval if calculation fails
    
    productivity_counts = df['productivity_label'].value_counts()
    productive_seconds = productivity_counts.get('Productive', 0) * analysis_interval
    unproductive_seconds = productivity_counts.get('Unproductive', 0) * analysis_interval
    
    total_analyzed_seconds = productive_seconds + unproductive_seconds
    productivity_percentage = (productive_seconds / total_analyzed_seconds) * 100 if total_analyzed_seconds > 0 else 0

    time_per_service = (df['service_name'].value_counts() * analysis_interval).to_dict()

    summary = {
        "session_id": session_id,
        "start_time": session_start.strftime('%Y-%m-%d %H:%M:%S'),
        "end_time": session_end.strftime('%Y-%m-%d %H:%M:%S'),
        "total_duration_minutes": round(total_duration_seconds / 60, 2),
        "productivity_percentage": round(productivity_percentage, 2),
        "time_in_minutes": {
            "productive": round(productive_seconds / 60, 2),
            "unproductive": round(unproductive_seconds / 60, 2),
        },
        "time_per_service_minutes": {k: round(v / 60, 2) for k, v in time_per_service.items()}
    }
    
    return summary

if __name__ == "__main__":
    # This block allows us to call this script from the command line.
    # Example usage: python analytics_engine.py session_12345
    
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Session ID must be provided as an argument."}))
        sys.exit(1)
        
    db_file = "focus_guardian.db"
    session_id_to_analyze = sys.argv[1]
    
    # Calculate the summary
    final_summary = calculate_session_summary(db_file, session_id_to_analyze)
    
    # Print the final result as a JSON string to standard output
    print(json.dumps(final_summary))