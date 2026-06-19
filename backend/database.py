import os
import time
import sqlite3
import psycopg2

class DatabaseManager:
    def __init__(self, config_path=None):
        self.db_type = "sqlite"  # Default fallback
        self.conn = None
        self.sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traffic_signal.db")
        
        # Load connection string from environment variable or local config
        self.pg_dsn = os.environ.get("DATABASE_URL")
        
        # Try to connect to PostgreSQL if DSN is set
        if self.pg_dsn:
            try:
                print(f"Attempting to connect to PostgreSQL (Supabase) database...")
                self.conn = psycopg2.connect(self.pg_dsn, connect_timeout=5)
                self.db_type = "postgres"
                print("Successfully connected to PostgreSQL (Supabase) Database!")
            except Exception as e:
                print(f"WARNING: PostgreSQL connection failed: {e}")
                print(f"Falling back to local SQLite database at: {self.sqlite_path}")
                self.conn = None
                
        if not self.conn:
            # Connect to local SQLite
            self.conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            self.db_type = "sqlite"
            print(f"Connected to local SQLite database: {self.sqlite_path}")
            
        self.init_db()

    def get_connection(self):
        if self.db_type == "postgres":
            try:
                # Test connection
                with self.conn.cursor() as cur:
                    cur.execute("SELECT 1")
            except Exception:
                try:
                    print("PostgreSQL connection lost. Reconnecting...")
                    self.conn = psycopg2.connect(self.pg_dsn, connect_timeout=5)
                except Exception as e:
                    print(f"Reconnection failed: {e}. Falling back to SQLite...")
                    self.db_type = "sqlite"
                    self.conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        return self.conn

    def init_db(self):
        conn = self.get_connection()
        cur = conn.cursor()
        
        if self.db_type == "postgres":
            create_table_query = """
            CREATE TABLE IF NOT EXISTS violations (
                id SERIAL PRIMARY KEY,
                violation_id VARCHAR(50) UNIQUE NOT NULL,
                video_filename VARCHAR(255) NOT NULL,
                location VARCHAR(255) NOT NULL,
                violation_type VARCHAR(100) NOT NULL,
                vehicle_type VARCHAR(50) NOT NULL,
                license_plate VARCHAR(50),
                confidence NUMERIC(5, 2) NOT NULL,
                timestamp_in_video VARCHAR(20) NOT NULL,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                challan_status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
                challan_amount NUMERIC(10, 2) NOT NULL,
                challan_number VARCHAR(100) UNIQUE NOT NULL,
                crop_url VARCHAR(255) NOT NULL,
                detail_url VARCHAR(255) NOT NULL,
                frame_count INTEGER NOT NULL,
                centroid_x INTEGER NOT NULL,
                centroid_y INTEGER NOT NULL,
                box_coords VARCHAR(100) NOT NULL,
                violator_name VARCHAR(100),
                violator_mobile VARCHAR(20),
                query_status VARCHAR(50) DEFAULT 'NONE',
                query_chat TEXT DEFAULT '[]'
            );
            """
        else:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                violation_id TEXT UNIQUE NOT NULL,
                video_filename TEXT NOT NULL,
                location TEXT NOT NULL,
                violation_type TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                license_plate TEXT,
                confidence REAL NOT NULL,
                timestamp_in_video TEXT NOT NULL,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                challan_status TEXT DEFAULT 'PENDING' NOT NULL,
                challan_amount REAL NOT NULL,
                challan_number TEXT UNIQUE NOT NULL,
                crop_url TEXT NOT NULL,
                detail_url TEXT NOT NULL,
                frame_count INTEGER NOT NULL,
                centroid_x INTEGER NOT NULL,
                centroid_y INTEGER NOT NULL,
                box_coords TEXT NOT NULL,
                violator_name TEXT,
                violator_mobile TEXT,
                query_status TEXT DEFAULT 'NONE',
                query_chat TEXT DEFAULT '[]'
            );
            """
            
        cur.execute(create_table_query)
        conn.commit()
        
        # Safe migration for existing schemas to add columns if they are missing
        if self.db_type == "postgres":
            columns_to_add = [
                ("violator_name", "VARCHAR(100)"),
                ("violator_mobile", "VARCHAR(20)"),
                ("query_status", "VARCHAR(50) DEFAULT 'NONE'"),
                ("query_chat", "TEXT DEFAULT '[]'")
            ]
            for col_name, col_type in columns_to_add:
                try:
                    cur.execute(f"ALTER TABLE violations ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    conn.commit()
                except Exception as e:
                    print(f"PostgreSQL Alter migration for {col_name} failed/ignored: {e}")
        else:
            columns_to_add = [
                ("violator_name", "TEXT"),
                ("violator_mobile", "TEXT"),
                ("query_status", "TEXT DEFAULT 'NONE'"),
                ("query_chat", "TEXT DEFAULT '[]'")
            ]
            for col_name, col_type in columns_to_add:
                try:
                    cur.execute(f"ALTER TABLE violations ADD COLUMN {col_name} {col_type}")
                    conn.commit()
                except Exception:
                    pass
        cur.close()

    def insert_violation(self, v_data):
        conn = self.get_connection()
        cur = conn.cursor()
        
        fields = [
            "violation_id", "video_filename", "location", "violation_type", 
            "vehicle_type", "license_plate", "confidence", "timestamp_in_video", 
            "challan_status", "challan_amount", "challan_number", "crop_url", 
            "detail_url", "frame_count", "centroid_x", "centroid_y", "box_coords",
            "violator_name", "violator_mobile", "query_status", "query_chat"
        ]
        
        placeholders = ", ".join(["%s" if self.db_type == "postgres" else "?"] * len(fields))
        query = f"INSERT INTO violations ({', '.join(fields)}) VALUES ({placeholders})"
        
        values = [v_data.get(f) for f in fields]
        
        try:
            cur.execute(query, values)
            conn.commit()
        except Exception as e:
            print(f"Error inserting violation into database: {e}")
            conn.rollback()
        finally:
            cur.close()

    def update_query_chat(self, violation_id, query_chat_json, query_status):
        conn = self.get_connection()
        cur = conn.cursor()
        
        param_placeholder = "%s" if self.db_type == "postgres" else "?"
        query = f"UPDATE violations SET query_chat = {param_placeholder}, query_status = {param_placeholder} WHERE violation_id = {param_placeholder}"
        
        try:
            cur.execute(query, (query_chat_json, query_status, violation_id))
            conn.commit()
            print(f"Successfully updated query chat for {violation_id} to status {query_status}")
            return True
        except Exception as e:
            print(f"Error updating query chat: {e}")
            conn.rollback()
            return False
        finally:
            cur.close()

    def get_all_violations(self):
        conn = self.get_connection()
        cur = conn.cursor()
        
        query = "SELECT * FROM violations ORDER BY id DESC"
        cur.execute(query)
        rows = cur.fetchall()
        
        columns = [desc[0] for desc in cur.description]
        cur.close()
        
        violations = []
        for r in rows:
            violations.append(dict(zip(columns, r)))
        return violations

    def get_violation_by_id(self, violation_id):
        conn = self.get_connection()
        cur = conn.cursor()
        
        param_placeholder = "%s" if self.db_type == "postgres" else "?"
        query = f"SELECT * FROM violations WHERE violation_id = {param_placeholder}"
        cur.execute(query, (violation_id,))
        row = cur.fetchone()
        
        if not row:
            cur.close()
            return None
            
        columns = [desc[0] for desc in cur.description]
        cur.close()
        return dict(zip(columns, row))

    def update_challan_status(self, violation_id, status):
        conn = self.get_connection()
        cur = conn.cursor()
        
        param_placeholder = "%s" if self.db_type == "postgres" else "?"
        query = f"UPDATE violations SET challan_status = {param_placeholder} WHERE violation_id = {param_placeholder}"
        
        try:
            cur.execute(query, (status, violation_id))
            conn.commit()
            print(f"Successfully updated challan status for {violation_id} to {status}")
            return True
        except Exception as e:
            print(f"Error updating challan status: {e}")
            conn.rollback()
            return False
        finally:
            cur.close()

    def clear_all_violations(self):
        conn = self.get_connection()
        cur = conn.cursor()
        query = "DELETE FROM violations"
        try:
            cur.execute(query)
            conn.commit()
            print("Database table 'violations' truncated successfully.")
        except Exception as e:
            print(f"Error truncating table: {e}")
            conn.rollback()
        finally:
            cur.close()
