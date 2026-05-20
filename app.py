import json
import mimetypes
import os
import re
import secrets
import sqlite3
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "taskflow.sqlite3"))
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "24"))


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def parse_iso(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def json_response(start_response, status, payload):
    body = json.dumps(payload).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Headers", "Content-Type, Authorization"),
        ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
    ]
    start_response(status, headers)
    return [body]


class TaskFlowApp:
    def __init__(self):
        self._ensure_db()

    def _connect(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA synchronous = OFF")
        return conn

    def _ensure_db(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    avatar_color TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS project_members (
                    user_id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'member')),
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, project_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('todo', 'in_progress', 'review', 'done')),
                    priority TEXT NOT NULL CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
                    due_date TEXT,
                    project_id INTEGER NOT NULL,
                    assignee_id INTEGER,
                    creator_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(assignee_id) REFERENCES users(id) ON DELETE SET NULL,
                    FOREIGN KEY(creator_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )

    def __call__(self, environ, start_response):
        method = environ["REQUEST_METHOD"].upper()
        path = environ.get("PATH_INFO", "/")

        if method == "OPTIONS":
            start_response(
                "204 No Content",
                [
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Headers", "Content-Type, Authorization"),
                    ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
                    ("Content-Length", "0"),
                ],
            )
            return [b""]

        try:
            if path.startswith("/api/"):
                return self.handle_api(environ, start_response)
            return self.handle_static(path, start_response)
        except Exception as exc:
            traceback.print_exc()
            return json_response(start_response, "500 Internal Server Error", {"error": str(exc)})

    def handle_static(self, path, start_response):
        target = (STATIC_DIR / path.lstrip("/")).resolve() if path != "/" else STATIC_DIR / "index.html"
        if path == "/" or not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists() or target.is_dir():
            target = STATIC_DIR / "index.html"
        data = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        start_response(
            "200 OK",
            [
                ("Content-Type", content_type),
                ("Content-Length", str(len(data))),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )
        return [data]

    def read_json(self, environ):
        length = int(environ.get("CONTENT_LENGTH") or "0")
        raw = environ["wsgi.input"].read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8")) if raw else {}

    def get_query(self, environ):
        return parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)

    def hash_password(self, password):
        import hashlib

        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
        return f"{salt}${digest.hex()}"

    def verify_password(self, password, stored):
        import hashlib
        import hmac

        salt, expected = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
        return hmac.compare_digest(digest.hex(), expected)

    def create_session(self, conn, user_id):
        token = secrets.token_urlsafe(32)
        created_at = utc_now()
        expires_at = created_at + timedelta(hours=SESSION_HOURS)
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, expires_at.isoformat(), created_at.isoformat()),
        )
        return token

    def user_to_dict(self, row):
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "full_name": row["full_name"],
            "avatar_color": row["avatar_color"],
            "created_at": row["created_at"],
        }

    def get_current_user(self, conn, environ):
        auth = environ.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        user = conn.execute(
            """
            SELECT u.*, s.expires_at FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not user:
            return None
        expires_at = parse_iso(user["expires_at"])
        if not expires_at or expires_at < utc_now():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return None
        return user

    def require_user(self, conn, environ, start_response):
        user = self.get_current_user(conn, environ)
        if not user:
            return None, json_response(start_response, "401 Unauthorized", {"error": "Authentication required"})
        return user, None

    def get_member_role(self, conn, project_id, user_id):
        project = conn.execute("SELECT owner_id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return None
        if project["owner_id"] == user_id:
            return "admin"
        row = conn.execute(
            "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        ).fetchone()
        return row["role"] if row else None

    def serialize_project(self, conn, project_row, include_stats=False, include_members=False, current_user_id=None):
        owner = conn.execute("SELECT * FROM users WHERE id = ?", (project_row["owner_id"],)).fetchone()
        member_count = conn.execute(
            "SELECT COUNT(*) AS count FROM project_members WHERE project_id = ?",
            (project_row["id"],),
        ).fetchone()["count"]
        payload = {
            "id": project_row["id"],
            "name": project_row["name"],
            "description": project_row["description"],
            "color": project_row["color"],
            "owner_id": project_row["owner_id"],
            "owner": self.user_to_dict(owner) if owner else None,
            "member_count": member_count,
            "created_at": project_row["created_at"],
            "updated_at": project_row["updated_at"],
        }
        if include_stats:
            stats = {"total": 0, "todo": 0, "in_progress": 0, "review": 0, "done": 0, "overdue": 0}
            for row in conn.execute("SELECT status, due_date FROM tasks WHERE project_id = ?", (project_row["id"],)):
                stats["total"] += 1
                stats[row["status"]] += 1
                due_date = parse_iso(row["due_date"]) if row["due_date"] else None
                if due_date and due_date < utc_now() and row["status"] != "done":
                    stats["overdue"] += 1
            payload["task_stats"] = stats
        if include_members:
            payload["members"] = []
            for member in conn.execute(
                """
                SELECT u.*, pm.role
                FROM project_members pm
                JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = ?
                ORDER BY CASE WHEN u.id = ? THEN 0 ELSE 1 END, u.full_name
                """,
                (project_row["id"], project_row["owner_id"]),
            ):
                member_data = self.user_to_dict(member)
                member_data["role"] = "admin" if member["id"] == project_row["owner_id"] else member["role"]
                payload["members"].append(member_data)
        if current_user_id:
            payload["current_user_role"] = self.get_member_role(conn, project_row["id"], current_user_id)
        return payload

    def serialize_task(self, conn, task_row):
        assignee = None
        creator = None
        if task_row["assignee_id"]:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (task_row["assignee_id"],)).fetchone()
            assignee = self.user_to_dict(row) if row else None
        if task_row["creator_id"]:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (task_row["creator_id"],)).fetchone()
            creator = self.user_to_dict(row) if row else None
        project = conn.execute("SELECT name, color FROM projects WHERE id = ?", (task_row["project_id"],)).fetchone()
        due_date = parse_iso(task_row["due_date"]) if task_row["due_date"] else None
        return {
            "id": task_row["id"],
            "title": task_row["title"],
            "description": task_row["description"],
            "status": task_row["status"],
            "priority": task_row["priority"],
            "due_date": task_row["due_date"],
            "project_id": task_row["project_id"],
            "project_name": project["name"] if project else None,
            "project_color": project["color"] if project else None,
            "assignee_id": task_row["assignee_id"],
            "assignee": assignee,
            "creator_id": task_row["creator_id"],
            "creator": creator,
            "is_overdue": bool(due_date and due_date < utc_now() and task_row["status"] != "done"),
            "created_at": task_row["created_at"],
            "updated_at": task_row["updated_at"],
        }

    def handle_api(self, environ, start_response):
        method = environ["REQUEST_METHOD"].upper()
        path = environ["PATH_INFO"]
        with self._connect() as conn:
            if path == "/api/health":
                return json_response(start_response, "200 OK", {"status": "ok", "time": iso_now()})

            if path == "/api/auth/signup" and method == "POST":
                data = self.read_json(environ)
                errors = {}
                username = (data.get("username") or "").strip().lower()
                email = (data.get("email") or "").strip().lower()
                password = data.get("password") or ""
                full_name = (data.get("full_name") or "").strip()
                if len(username) < 3:
                    errors["username"] = "Username must be at least 3 characters"
                if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
                    errors["email"] = "Valid email is required"
                if len(password) < 6:
                    errors["password"] = "Password must be at least 6 characters"
                if len(full_name) < 2:
                    errors["full_name"] = "Full name is required"
                if errors:
                    return json_response(start_response, "400 Bad Request", {"errors": errors})
                if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                    return json_response(start_response, "409 Conflict", {"errors": {"username": "Username already taken"}})
                if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                    return json_response(start_response, "409 Conflict", {"errors": {"email": "Email already registered"}})
                color = ["#0A84FF", "#30B0C7", "#34C759", "#FF9F0A", "#FF375F", "#7D7AFF"][secrets.randbelow(6)]
                cursor = conn.execute(
                    """
                    INSERT INTO users (username, email, password_hash, full_name, avatar_color, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (username, email, self.hash_password(password), full_name, color, iso_now()),
                )
                token = self.create_session(conn, cursor.lastrowid)
                conn.commit()
                user = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
                return json_response(start_response, "201 Created", {"message": "Account created", "token": token, "user": self.user_to_dict(user)})

            if path == "/api/auth/login" and method == "POST":
                data = self.read_json(environ)
                username = (data.get("username") or "").strip().lower()
                password = data.get("password") or ""
                if not username or not password:
                    return json_response(start_response, "400 Bad Request", {"errors": {"general": "Username and password are required"}})
                user = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, username)).fetchone()
                if not user or not self.verify_password(password, user["password_hash"]):
                    return json_response(start_response, "401 Unauthorized", {"errors": {"general": "Invalid credentials"}})
                token = self.create_session(conn, user["id"])
                conn.commit()
                return json_response(start_response, "200 OK", {"message": "Login successful", "token": token, "user": self.user_to_dict(user)})

            if path == "/api/auth/me" and method == "GET":
                user, response = self.require_user(conn, environ, start_response)
                if response:
                    return response
                return json_response(start_response, "200 OK", {"user": self.user_to_dict(user)})

            user, response = self.require_user(conn, environ, start_response)
            if response:
                return response

            if path == "/api/dashboard" and method == "GET":
                projects = [
                    self.serialize_project(conn, row, include_stats=True)
                    for row in conn.execute(
                        """
                        SELECT DISTINCT p.* FROM projects p
                        LEFT JOIN project_members pm ON pm.project_id = p.id
                        WHERE p.owner_id = ? OR pm.user_id = ?
                        ORDER BY p.updated_at DESC
                        LIMIT 6
                        """,
                        (user["id"], user["id"]),
                    )
                ]
                tasks = [self.serialize_task(conn, row) for row in conn.execute("SELECT * FROM tasks WHERE assignee_id = ? ORDER BY updated_at DESC", (user["id"],))]
                overdue_tasks = [task for task in tasks if task["is_overdue"]]
                stats = {
                    "total_projects": len(projects),
                    "total_tasks": len(tasks),
                    "completed": len([t for t in tasks if t["status"] == "done"]),
                    "in_progress": len([t for t in tasks if t["status"] == "in_progress"]),
                    "todo": len([t for t in tasks if t["status"] == "todo"]),
                    "review": len([t for t in tasks if t["status"] == "review"]),
                    "overdue": len(overdue_tasks),
                }
                stats["completion_rate"] = round((stats["completed"] / stats["total_tasks"] * 100) if stats["total_tasks"] else 0, 1)
                return json_response(start_response, "200 OK", {"stats": stats, "recent_tasks": tasks[:10], "overdue_tasks": overdue_tasks, "projects": projects})

            if path == "/api/projects" and method == "GET":
                rows = conn.execute(
                    """
                    SELECT DISTINCT p.* FROM projects p
                    LEFT JOIN project_members pm ON pm.project_id = p.id
                    WHERE p.owner_id = ? OR pm.user_id = ?
                    ORDER BY p.updated_at DESC
                    """,
                    (user["id"], user["id"]),
                )
                return json_response(start_response, "200 OK", {"projects": [self.serialize_project(conn, row, include_stats=True) for row in rows]})

            if path == "/api/projects" and method == "POST":
                data = self.read_json(environ)
                name = (data.get("name") or "").strip()
                description = (data.get("description") or "").strip()
                color = data.get("color") or ["#0A84FF", "#30B0C7", "#34C759", "#FF9F0A", "#FF375F"][secrets.randbelow(5)]
                if len(name) < 2:
                    return json_response(start_response, "400 Bad Request", {"error": "Project name is required"})
                now = iso_now()
                cursor = conn.execute(
                    """
                    INSERT INTO projects (name, description, color, owner_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (name, description, color, user["id"], now, now),
                )
                conn.execute("INSERT INTO project_members (user_id, project_id, role, joined_at) VALUES (?, ?, 'admin', ?)", (user["id"], cursor.lastrowid, now))
                conn.commit()
                row = conn.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)).fetchone()
                return json_response(start_response, "201 Created", {"message": "Project created", "project": self.serialize_project(conn, row, include_stats=True)})

            if path == "/api/users/search" and method == "GET":
                q = (self.get_query(environ).get("q", [""])[0] or "").strip().lower()
                if len(q) < 2:
                    return json_response(start_response, "200 OK", {"users": []})
                users = conn.execute(
                    """
                    SELECT * FROM users
                    WHERE username LIKE ? OR email LIKE ? OR full_name LIKE ?
                    ORDER BY full_name ASC
                    LIMIT 10
                    """,
                    (f"%{q}%", f"%{q}%", f"%{q}%"),
                )
                return json_response(start_response, "200 OK", {"users": [self.user_to_dict(row) for row in users]})

            project_match = re.fullmatch(r"/api/projects/(\d+)", path)
            if project_match:
                project_id = int(project_match.group(1))
                project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
                if not project:
                    return json_response(start_response, "404 Not Found", {"error": "Project not found"})
                role = self.get_member_role(conn, project_id, user["id"])
                if not role:
                    return json_response(start_response, "403 Forbidden", {"error": "Access denied"})
                if method == "GET":
                    return json_response(start_response, "200 OK", {"project": self.serialize_project(conn, project, include_stats=True, include_members=True, current_user_id=user["id"])})
                if method == "PUT":
                    if role != "admin":
                        return json_response(start_response, "403 Forbidden", {"error": "Only admins can update projects"})
                    data = self.read_json(environ)
                    name = (data.get("name") or project["name"]).strip()
                    description = (data.get("description") if "description" in data else project["description"]).strip()
                    color = data.get("color") or project["color"]
                    if len(name) < 2:
                        return json_response(start_response, "400 Bad Request", {"error": "Project name is required"})
                    conn.execute("UPDATE projects SET name = ?, description = ?, color = ?, updated_at = ? WHERE id = ?", (name, description, color, iso_now(), project_id))
                    conn.commit()
                    updated = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
                    return json_response(start_response, "200 OK", {"message": "Project updated", "project": self.serialize_project(conn, updated, include_stats=True)})
                if method == "DELETE":
                    if project["owner_id"] != user["id"]:
                        return json_response(start_response, "403 Forbidden", {"error": "Only the owner can delete this project"})
                    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                    conn.commit()
                    return json_response(start_response, "200 OK", {"message": "Project deleted"})

            member_add_match = re.fullmatch(r"/api/projects/(\d+)/members", path)
            if member_add_match and method == "POST":
                project_id = int(member_add_match.group(1))
                role = self.get_member_role(conn, project_id, user["id"])
                if role != "admin":
                    return json_response(start_response, "403 Forbidden", {"error": "Only admins can add members"})
                data = self.read_json(environ)
                lookup = (data.get("username") or "").strip().lower()
                member_role = data.get("role") if data.get("role") in ("admin", "member") else "member"
                if not lookup:
                    return json_response(start_response, "400 Bad Request", {"error": "Username or email is required"})
                target = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (lookup, lookup)).fetchone()
                if not target:
                    return json_response(start_response, "404 Not Found", {"error": "User not found"})
                if self.get_member_role(conn, project_id, target["id"]):
                    return json_response(start_response, "409 Conflict", {"error": "User is already a member"})
                conn.execute("INSERT INTO project_members (user_id, project_id, role, joined_at) VALUES (?, ?, ?, ?)", (target["id"], project_id, member_role, iso_now()))
                conn.commit()
                member = self.user_to_dict(target)
                member["role"] = member_role
                return json_response(start_response, "201 Created", {"message": "Member added", "member": member})

            member_match = re.fullmatch(r"/api/projects/(\d+)/members/(\d+)", path)
            if member_match and method == "DELETE":
                project_id = int(member_match.group(1))
                member_id = int(member_match.group(2))
                role = self.get_member_role(conn, project_id, user["id"])
                if role != "admin":
                    return json_response(start_response, "403 Forbidden", {"error": "Only admins can remove members"})
                project = conn.execute("SELECT owner_id FROM projects WHERE id = ?", (project_id,)).fetchone()
                if not project:
                    return json_response(start_response, "404 Not Found", {"error": "Project not found"})
                if member_id == project["owner_id"]:
                    return json_response(start_response, "400 Bad Request", {"error": "Cannot remove the project owner"})
                conn.execute("DELETE FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, member_id))
                conn.execute("UPDATE tasks SET assignee_id = NULL, updated_at = ? WHERE project_id = ? AND assignee_id = ?", (iso_now(), project_id, member_id))
                conn.commit()
                return json_response(start_response, "200 OK", {"message": "Member removed"})

            role_match = re.fullmatch(r"/api/projects/(\d+)/members/(\d+)/role", path)
            if role_match and method == "PUT":
                project_id = int(role_match.group(1))
                member_id = int(role_match.group(2))
                project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
                if not project:
                    return json_response(start_response, "404 Not Found", {"error": "Project not found"})
                if project["owner_id"] != user["id"]:
                    return json_response(start_response, "403 Forbidden", {"error": "Only the owner can change roles"})
                if member_id == project["owner_id"]:
                    return json_response(start_response, "400 Bad Request", {"error": "Cannot change the owner role"})
                data = self.read_json(environ)
                new_role = data.get("role")
                if new_role not in ("admin", "member"):
                    return json_response(start_response, "400 Bad Request", {"error": "Invalid role"})
                conn.execute("UPDATE project_members SET role = ? WHERE project_id = ? AND user_id = ?", (new_role, project_id, member_id))
                conn.commit()
                return json_response(start_response, "200 OK", {"message": "Role updated"})

            tasks_match = re.fullmatch(r"/api/projects/(\d+)/tasks", path)
            if tasks_match:
                project_id = int(tasks_match.group(1))
                role = self.get_member_role(conn, project_id, user["id"])
                if not role:
                    return json_response(start_response, "403 Forbidden", {"error": "Access denied"})
                if method == "GET":
                    query = "SELECT * FROM tasks WHERE project_id = ?"
                    params = [project_id]
                    filters = self.get_query(environ)
                    status = filters.get("status", [""])[0]
                    priority = filters.get("priority", [""])[0]
                    assignee = filters.get("assignee", [""])[0]
                    if status:
                        query += " AND status = ?"
                        params.append(status)
                    if priority:
                        query += " AND priority = ?"
                        params.append(priority)
                    if assignee == "me":
                        query += " AND assignee_id = ?"
                        params.append(user["id"])
                    elif assignee == "unassigned":
                        query += " AND assignee_id IS NULL"
                    elif assignee.isdigit():
                        query += " AND assignee_id = ?"
                        params.append(int(assignee))
                    query += " ORDER BY created_at DESC"
                    tasks = [self.serialize_task(conn, row) for row in conn.execute(query, params)]
                    return json_response(start_response, "200 OK", {"tasks": tasks, "current_user_role": role})
                if method == "POST":
                    data = self.read_json(environ)
                    title = (data.get("title") or "").strip()
                    description = (data.get("description") or "").strip()
                    status = data.get("status") if data.get("status") in ("todo", "in_progress", "review", "done") else "todo"
                    priority = data.get("priority") if data.get("priority") in ("low", "medium", "high", "urgent") else "medium"
                    if len(title) < 2:
                        return json_response(start_response, "400 Bad Request", {"error": "Task title is required"})
                    assignee_id = data.get("assignee_id")
                    if assignee_id not in (None, ""):
                        assignee_id = int(assignee_id)
                        if not self.get_member_role(conn, project_id, assignee_id):
                            return json_response(start_response, "400 Bad Request", {"error": "Assignee must be a project member"})
                    else:
                        assignee_id = None
                    due_date = parse_iso(data.get("due_date"))
                    now = iso_now()
                    cursor = conn.execute(
                        """
                        INSERT INTO tasks (title, description, status, priority, due_date, project_id, assignee_id, creator_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (title, description, status, priority, due_date.isoformat() if due_date else None, project_id, assignee_id, user["id"], now, now),
                    )
                    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
                    conn.commit()
                    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
                    return json_response(start_response, "201 Created", {"message": "Task created", "task": self.serialize_task(conn, task)})

            task_match = re.fullmatch(r"/api/tasks/(\d+)", path)
            if task_match:
                task_id = int(task_match.group(1))
                task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
                if not task:
                    return json_response(start_response, "404 Not Found", {"error": "Task not found"})
                role = self.get_member_role(conn, task["project_id"], user["id"])
                if not role:
                    return json_response(start_response, "403 Forbidden", {"error": "Access denied"})
                if method == "GET":
                    return json_response(start_response, "200 OK", {"task": self.serialize_task(conn, task), "current_user_role": role})
                if method == "PUT":
                    data = self.read_json(environ)
                    editable = data
                    if role == "member":
                        if user["id"] not in (task["creator_id"], task["assignee_id"]):
                            return json_response(start_response, "403 Forbidden", {"error": "Members can only edit their own tasks"})
                        editable = {key: value for key, value in data.items() if key in ("status", "description")}
                    title = task["title"]
                    description = task["description"]
                    status = task["status"]
                    priority = task["priority"]
                    assignee_id = task["assignee_id"]
                    due_date = task["due_date"]
                    if "title" in editable and str(editable["title"]).strip():
                        title = str(editable["title"]).strip()
                    if "description" in editable:
                        description = str(editable["description"]).strip()
                    if "status" in editable and editable["status"] in ("todo", "in_progress", "review", "done"):
                        status = editable["status"]
                    if "priority" in editable and editable["priority"] in ("low", "medium", "high", "urgent"):
                        priority = editable["priority"]
                    if "assignee_id" in editable:
                        if editable["assignee_id"] in (None, ""):
                            assignee_id = None
                        else:
                            candidate = int(editable["assignee_id"])
                            if not self.get_member_role(conn, task["project_id"], candidate):
                                return json_response(start_response, "400 Bad Request", {"error": "Assignee must be a project member"})
                            assignee_id = candidate
                    if "due_date" in editable:
                        parsed = parse_iso(editable["due_date"])
                        due_date = parsed.isoformat() if parsed else None
                    now = iso_now()
                    conn.execute(
                        """
                        UPDATE tasks
                        SET title = ?, description = ?, status = ?, priority = ?, assignee_id = ?, due_date = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (title, description, status, priority, assignee_id, due_date, now, task_id),
                    )
                    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, task["project_id"]))
                    conn.commit()
                    updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
                    return json_response(start_response, "200 OK", {"message": "Task updated", "task": self.serialize_task(conn, updated)})
                if method == "DELETE":
                    if role != "admin" and task["creator_id"] != user["id"]:
                        return json_response(start_response, "403 Forbidden", {"error": "Only admins or the task creator can delete tasks"})
                    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (iso_now(), task["project_id"]))
                    conn.commit()
                    return json_response(start_response, "200 OK", {"message": "Task deleted"})

            return json_response(start_response, "404 Not Found", {"error": "Route not found"})


application = TaskFlowApp()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    with make_server("0.0.0.0", port, application) as server:
        print(f"TaskFlow running on http://0.0.0.0:{port}")
        server.serve_forever()
