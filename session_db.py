import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "chat_app.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tools_used TEXT DEFAULT '[]',
                action_selected TEXT DEFAULT 'Direct',
                feedback INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)
        
        # Documents metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()

# Session operations
def create_session(title: str = "New Chat") -> Dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now)
        )
        conn.commit()
    return {"id": session_id, "title": title, "created_at": now, "updated_at": now}

def get_all_sessions() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_session_title(session_id: str, title: str):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?", (title, now, session_id))
        conn.commit()

def delete_session(session_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()

# Message operations
def add_message(session_id: str, role: str, content: str, tools_used: List[str] = None, action_selected: str = "Direct") -> Dict[str, Any]:
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    tools_json = json.dumps(tools_used or [])
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (id, session_id, role, content, tools_used, action_selected, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, tools_json, action_selected, now)
        )
        cursor.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        conn.commit()
        
    return {
        "id": msg_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "tools_used": tools_used or [],
        "action_selected": action_selected,
        "feedback": 0,
        "created_at": now
    }

def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, session_id, role, content, tools_used, action_selected, feedback, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        )
        rows = cursor.fetchall()
        messages = []
        for row in rows:
            m = dict(row)
            try:
                m["tools_used"] = json.loads(m["tools_used"])
            except Exception:
                m["tools_used"] = []
            messages.append(m)
        return messages

def update_message_feedback(message_id: str, feedback: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET feedback = ? WHERE id = ?", (feedback, message_id))
        cursor.execute("SELECT id, session_id, role, content, action_selected, feedback FROM messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        conn.commit()
        return dict(row) if row else None

# Document operations
def save_document_meta(filename: str, file_type: str, chunk_count: int) -> Dict[str, Any]:
    doc_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (id, filename, file_type, chunk_count, created_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, filename, file_type, chunk_count, now)
        )
        conn.commit()
    return {"id": doc_id, "filename": filename, "file_type": file_type, "chunk_count": chunk_count, "created_at": now}

def get_all_documents() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, filename, file_type, chunk_count, created_at FROM documents ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
