import os
import sqlite3
import logging
from typing import Any, List, Optional, Tuple, Union
from config import Config

logger = logging.getLogger(__name__)

# Try importing pyodbc for Azure SQL
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False


class DictRow:
    """Wrapper around a pyodbc or sqlite row allowing key access, dict conversion, and index access."""
    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key: Union[str, int]):
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def __contains__(self, key: str):
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def __repr__(self):
        return repr(self._data)


class DatabaseConnection:
    """Unified wrapper around SQLite and Azure SQL connections."""

    def __init__(self, conn, is_azure_sql: bool = False):
        self.conn = conn
        self.is_azure_sql = is_azure_sql

    def cursor(self):
        return self.conn.cursor()

    def execute(self, query: str, params: Union[tuple, list] = ()):
        cur = self.conn.cursor()
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return CursorWrapper(cur, self.is_azure_sql)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def execute_insert(self, query: str, params: Union[tuple, list] = ()) -> int:
        """Executes an INSERT statement and returns the newly generated primary key."""
        cur = self.conn.cursor()
        if self.is_azure_sql:
            # Azure SQL: append SELECT SCOPE_IDENTITY() to get generated ID
            cur.execute(query, params)
            cur.execute("SELECT SCOPE_IDENTITY() AS id")
            row = cur.fetchone()
            inserted_id = int(row[0]) if row and row[0] is not None else 0
        else:
            cur.execute(query, params)
            inserted_id = cur.lastrowid
        self.conn.commit()
        return inserted_id


class CursorWrapper:
    """Wraps cursor fetch calls to return uniform DictRow objects."""

    def __init__(self, cursor, is_azure_sql: bool):
        self.cursor = cursor
        self.is_azure_sql = is_azure_sql
        self.lastrowid = getattr(cursor, "lastrowid", None)

    def _convert_row(self, row) -> Optional[DictRow]:
        if row is None:
            return None
        if self.is_azure_sql:
            columns = [column[0] for column in self.cursor.description]
            return DictRow(dict(zip(columns, row)))
        else:
            # SQLite Row
            return DictRow(dict(row))

    def fetchone(self) -> Optional[DictRow]:
        row = self.cursor.fetchone()
        return self._convert_row(row)

    def fetchall(self) -> List[DictRow]:
        rows = self.cursor.fetchall()
        return [self._convert_row(r) for r in rows if r is not None]

    def close(self):
        self.cursor.close()


def get_db() -> DatabaseConnection:
    """
    Returns a unified database connection.
    Attempts Azure SQL if configured; falls back to SQLite seamlessly.
    """
    if Config.use_azure_sql() and PYODBC_AVAILABLE:
        try:
            conn_str = Config.AZURE_SQL_CONNECTION_STRING
            if not conn_str:
                driver = Config.AZURE_SQL_DRIVER
                if not driver.startswith("{"):
                    driver = f"{{{driver}}}"
                conn_str = (
                    f"Driver={driver};"
                    f"Server=tcp:{Config.AZURE_SQL_SERVER},1433;"
                    f"Database={Config.AZURE_SQL_DATABASE};"
                    f"Uid={Config.AZURE_SQL_USER};"
                    f"Pwd={Config.AZURE_SQL_PASSWORD};"
                    f"Encrypt=yes;"
                    f"TrustServerCertificate=no;"
                    f"Connection Timeout=30;"
                )
            conn = pyodbc.connect(conn_str)
            return DatabaseConnection(conn, is_azure_sql=True)
        except Exception as e:
            logger.warning(f"Could not connect to Azure SQL ({e}). Falling back to SQLite.")

    # Local SQLite Fallback
    conn = sqlite3.connect(Config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return DatabaseConnection(conn, is_azure_sql=False)


def init_db():
    """Initializes tables for either Azure SQL or SQLite."""
    db = get_db()
    if db.is_azure_sql:
        init_azure_sql(db)
    else:
        init_sqlite(db)
    db.close()


def init_sqlite(db: DatabaseConnection):
    cur = db.conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        department TEXT DEFAULT 'Engineering',
        description TEXT,
        required_skills TEXT NOT NULL,
        min_experience REAL DEFAULT 0,
        education TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        name TEXT,
        email TEXT,
        phone TEXT,
        resume_filename TEXT NOT NULL,
        resume_blob_url TEXT,
        extracted_text TEXT,
        skills TEXT,
        education TEXT,
        experience REAL DEFAULT 0,
        skill_score REAL DEFAULT 0,
        experience_score REAL DEFAULT 0,
        education_score REAL DEFAULT 0,
        semantic_score REAL DEFAULT 0,
        overall_score REAL DEFAULT 0,
        matched_skills TEXT,
        missing_skills TEXT,
        status TEXT DEFAULT 'Under Review',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)
    db.conn.commit()

    # Safe migration for existing SQLite databases created prior to Stage 1 & 4
    try:
        cur.execute("SELECT resume_blob_url FROM candidates LIMIT 1")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE candidates ADD COLUMN resume_blob_url TEXT")
        db.conn.commit()

    try:
        cur.execute("SELECT semantic_score FROM candidates LIMIT 1")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE candidates ADD COLUMN semantic_score REAL DEFAULT 0")
        db.conn.commit()


def init_azure_sql(db: DatabaseConnection):
    cur = db.conn.cursor()
    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='jobs' AND xtype='U')
    CREATE TABLE jobs (
        id INT IDENTITY(1,1) PRIMARY KEY,
        title NVARCHAR(255) NOT NULL,
        department NVARCHAR(100) DEFAULT 'Engineering',
        description NVARCHAR(MAX),
        required_skills NVARCHAR(MAX) NOT NULL,
        min_experience FLOAT DEFAULT 0,
        education NVARCHAR(255),
        created_at DATETIME2 DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='candidates' AND xtype='U')
    CREATE TABLE candidates (
        id INT IDENTITY(1,1) PRIMARY KEY,
        job_id INT NOT NULL,
        name NVARCHAR(255),
        email NVARCHAR(255),
        phone NVARCHAR(50),
        resume_filename NVARCHAR(255) NOT NULL,
        resume_blob_url NVARCHAR(1024),
        extracted_text NVARCHAR(MAX),
        skills NVARCHAR(MAX),
        education NVARCHAR(255),
        experience FLOAT DEFAULT 0,
        skill_score FLOAT DEFAULT 0,
        experience_score FLOAT DEFAULT 0,
        education_score FLOAT DEFAULT 0,
        semantic_score FLOAT DEFAULT 0,
        overall_score FLOAT DEFAULT 0,
        matched_skills NVARCHAR(MAX),
        missing_skills NVARCHAR(MAX),
        status NVARCHAR(50) DEFAULT 'Under Review',
        created_at DATETIME2 DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT FK_candidates_jobs FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)
    db.conn.commit()
    logger.info("Azure SQL tables verified/initialized.")

