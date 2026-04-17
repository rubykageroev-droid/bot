from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class UserProfile:
    id: int
    telegram_id: int
    photo_id: str
    age: int
    bio: str
    gender_pref: str
    goal: str
    rating: int
    likes_count: int
    dislikes_count: int
    views_count: int
    created_at: str


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    photo_id TEXT,
                    age INTEGER,
                    bio TEXT DEFAULT '',
                    gender_pref TEXT,
                    goal TEXT,
                    rating INTEGER DEFAULT 1000,
                    likes_count INTEGER DEFAULT 0,
                    dislikes_count INTEGER DEFAULT 0,
                    views_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS likes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(from_user_id, to_user_id),
                    FOREIGN KEY(from_user_id) REFERENCES users(id),
                    FOREIGN KEY(to_user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user1_id INTEGER NOT NULL,
                    user2_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user1_id, user2_id)
                );

                CREATE TABLE IF NOT EXISTS views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    viewer_id INTEGER NOT NULL,
                    viewed_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(viewer_id, viewed_id)
                );
                """
            )

    def upsert_user(self, telegram_id: int, **fields: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, created_at) VALUES (?, ?)",
                (telegram_id, now),
            )
            if fields:
                cols = ", ".join([f"{k} = ?" for k in fields.keys()])
                values = list(fields.values()) + [telegram_id]
                conn.execute(f"UPDATE users SET {cols} WHERE telegram_id = ?", values)

    def get_user_by_telegram(self, telegram_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()

    def get_user_by_id(self, user_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def has_complete_profile(self, telegram_id: int) -> bool:
        user = self.get_user_by_telegram(telegram_id)
        if not user:
            return False
        return bool(user["photo_id"] and user["age"] and user["gender_pref"] and user["goal"])

    def daily_actions_count(self, user_id: int) -> int:
        date_prefix = datetime.now(timezone.utc).date().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM likes WHERE from_user_id = ? AND created_at LIKE ?",
                (user_id, f"{date_prefix}%"),
            ).fetchone()
            return int(row["cnt"])

    def pick_candidate(self, viewer_telegram_id: int) -> sqlite3.Row | None:
        viewer = self.get_user_by_telegram(viewer_telegram_id)
        if not viewer:
            return None

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT u.*
                FROM users u
                WHERE u.id != ?
                  AND u.photo_id IS NOT NULL
                  AND u.age IS NOT NULL
                  AND u.goal = ?
                  AND u.id NOT IN (
                      SELECT viewed_id FROM views WHERE viewer_id = ?
                  )
                """,
                (viewer["id"], viewer["goal"], viewer["id"]),
            ).fetchall()

        if not rows:
            return None

        same_bucket: list[sqlite3.Row] = []
        higher: list[sqlite3.Row] = []
        lower: list[sqlite3.Row] = []

        for row in rows:
            if abs(row["rating"] - viewer["rating"]) <= 100:
                same_bucket.append(row)
            elif row["rating"] > viewer["rating"]:
                higher.append(row)
            else:
                lower.append(row)

        roll = random.random()
        if roll <= 0.60 and same_bucket:
            pool = same_bucket
        elif roll <= 0.85 and higher:
            pool = higher
        elif lower:
            pool = lower
        else:
            pool = same_bucket or higher or lower

        pool.sort(key=lambda r: (r["views_count"] + r["likes_count"], r["created_at"]))
        top = pool[: max(1, min(8, len(pool)))]
        return random.choice(top)

    def mark_view(self, viewer_id: int, viewed_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO views (viewer_id, viewed_id, created_at) VALUES (?, ?, ?)",
                (viewer_id, viewed_id, now),
            )
            conn.execute("UPDATE users SET views_count = views_count + 1 WHERE id = ?", (viewed_id,))

    def save_reaction(self, from_id: int, to_id: int, reaction_type: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO likes (from_user_id, to_user_id, type, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(from_user_id, to_user_id)
                DO UPDATE SET type = excluded.type, created_at = excluded.created_at
                """,
                (from_id, to_id, reaction_type, now),
            )

            if reaction_type == "like":
                from_user = conn.execute("SELECT rating FROM users WHERE id = ?", (from_id,)).fetchone()
                to_user = conn.execute("SELECT rating FROM users WHERE id = ?", (to_id,)).fetchone()
                delta = 15
                if from_user and to_user and from_user["rating"] > to_user["rating"]:
                    delta = 22
                conn.execute(
                    "UPDATE users SET likes_count = likes_count + 1, rating = rating + ? WHERE id = ?",
                    (delta, to_id),
                )
            elif reaction_type == "neutral":
                conn.execute("UPDATE users SET rating = rating + 2 WHERE id = ?", (to_id,))
            else:
                conn.execute(
                    "UPDATE users SET dislikes_count = dislikes_count + 1, rating = rating - 10 WHERE id = ?",
                    (to_id,),
                )

            reverse_like = conn.execute(
                "SELECT 1 FROM likes WHERE from_user_id = ? AND to_user_id = ? AND type = 'like'",
                (to_id, from_id),
            ).fetchone()
            if reaction_type == "like" and reverse_like:
                a, b = sorted((from_id, to_id))
                conn.execute(
                    "INSERT OR IGNORE INTO matches (user1_id, user2_id, created_at) VALUES (?, ?, ?)",
                    (a, b, now),
                )
                return True
        return False

    def count_likes_to_user(self, user_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM likes WHERE to_user_id = ? AND type = 'like'",
                (user_id,),
            ).fetchone()
            return int(row["cnt"])

    def profile_stats(self, user_id: int) -> dict[str, int]:
        with self._connect() as conn:
            likes = conn.execute(
                "SELECT COUNT(*) AS cnt FROM likes WHERE to_user_id = ? AND type = 'like'", (user_id,)
            ).fetchone()["cnt"]
            dislikes = conn.execute(
                "SELECT COUNT(*) AS cnt FROM likes WHERE to_user_id = ? AND type = 'dislike'", (user_id,)
            ).fetchone()["cnt"]
            views = conn.execute("SELECT views_count FROM users WHERE id = ?", (user_id,)).fetchone()["views_count"]
        return {"likes": int(likes), "dislikes": int(dislikes), "views": int(views)}
