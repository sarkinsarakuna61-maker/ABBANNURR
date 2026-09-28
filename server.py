from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import time
import os

app = Flask(__name__)
CORS(app)

DB_NAME = "abbannurr.db"

MAX_MINING_SECONDS = 24 * 60 * 60
BASE_RATE = 1
DAILY_REWARD = 100
REFERRAL_REWARD = 100


def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            coins INTEGER DEFAULT 0,
            mining_started_at INTEGER,
            streak INTEGER DEFAULT 0,
            last_daily_at INTEGER,
            referrer_id INTEGER,
            referral_count INTEGER DEFAULT 0,
            wallet_address TEXT DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            reward INTEGER DEFAULT 0,
            url TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            telegram_id INTEGER,
            task_id INTEGER,
            claimed INTEGER DEFAULT 0,
            PRIMARY KEY (telegram_id, task_id)
        )
    """)

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks"
    ).fetchone()["c"]

    if count == 0:
        conn.execute("""
            INSERT INTO tasks
            (title, description, reward, url)
            VALUES (?, ?, ?, ?)
        """, (
            "Join ABBANNURR Telegram",
            "Join the official ABBANNURR Telegram",
            500,
            "https://t.me/ABBANNURR1"
        ))

        conn.execute("""
            INSERT INTO tasks
            (title, description, reward, url)
            VALUES (?, ?, ?, ?)
        """, (
            "Follow ABBANNURR on X",
            "Follow the official ABBANNURR X account",
            1000,
            "https://x.com/ABBANNURR4077"
        ))

    conn.commit()
    conn.close()


def get_user(telegram_id):
    conn = db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (telegram_id,)).fetchone()

    conn.close()

    return user


def create_user(telegram_id, username="", referrer_id=None):
    conn = db()

    existing = conn.execute("""
        SELECT telegram_id
        FROM users
        WHERE telegram_id = ?
    """, (telegram_id,)).fetchone()

    if existing:
        conn.close()
        return

    now = int(time.time())
    valid_referrer = None

    try:
        if referrer_id:
            referrer_id = int(referrer_id)

            if referrer_id != telegram_id:
                ref = conn.execute("""
                    SELECT telegram_id
                    FROM users
                    WHERE telegram_id = ?
                """, (referrer_id,)).fetchone()

                if ref:
                    valid_referrer = referrer_id
    except:
        valid_referrer = None

    conn.execute("""
        INSERT INTO users (
            telegram_id,
            username,
            coins,
            mining_started_at,
            streak,
            referrer_id,
            referral_count,
            wallet_address
        )
        VALUES (?, ?, 0, ?, 0, ?, 0, '')
    """, (
        telegram_id,
        username,
        now,
        valid_referrer
    ))

    if valid_referrer:
        conn.execute("""
            UPDATE users
            SET coins = coins + ?,
                referral_count = referral_count + 1
            WHERE telegram_id = ?
        """, (
            REFERRAL_REWARD,
            valid_referrer
        ))

    conn.commit()
    conn.close()


def mining_status(user):
    now = int(time.time())
    started = user["mining_started_at"] or now

    elapsed = max(0, now - started)

    seconds = min(
        elapsed,
        MAX_MINING_SECONDS
    )

    pending = seconds * BASE_RATE

    remaining = max(
        0,
        MAX_MINING_SECONDS - elapsed
    )

    return {
        "mining_rate": BASE_RATE,
        "mining_seconds": seconds,
        "pending_coins": pending,
        "remaining": remaining,
        "ready": elapsed >= MAX_MINING_SECONDS
    }


@app.route("/")
def home():
    return jsonify({
        "project": "ABBANNURR",
        "status": "online",
        "version": "1.0",
        "wallet": "TON",
        "mining": "24-hour"
    })


@app.route("/index.html")
def index():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "index.html"
    )


@app.route("/api/user", methods=["POST"])
def api_user():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
    except:
        return jsonify({"error": "Invalid telegram_id"}), 400

    username = str(
        data.get("username", "")
    )

    referrer_id = data.get("referrer_id")

    create_user(
        telegram_id,
        username,
        referrer_id
    )

    user = get_user(telegram_id)

    status = mining_status(user)

    return jsonify({
        "telegram_id": user["telegram_id"],
        "username": user["username"],
        "coins": user["coins"],
        "streak": user["streak"],
        "referral_count": user["referral_count"],
        "wallet_address": user["wallet_address"],
        **status
    })


@app.route("/api/mine/claim", methods=["POST"])
def claim_mining():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
    except:
        return jsonify({"error": "Invalid telegram_id"}), 400

    user = get_user(telegram_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    status = mining_status(user)

    if not status["ready"]:
        return jsonify({
            "error": "Mining cycle is not complete",
            "remaining": status["remaining"]
        }), 400

    reward = status["pending_coins"]
    now = int(time.time())

    conn = db()

    conn.execute("""
        UPDATE users
        SET coins = coins + ?,
            mining_started_at = ?
        WHERE telegram_id = ?
    """, (
        reward,
        now,
        telegram_id
    ))

    conn.commit()
    conn.close()

    user = get_user(telegram_id)

    return jsonify({
        "success": True,
        "claimed": reward,
        "coins": user["coins"],
        **mining_status(user)
    })


@app.route("/api/daily", methods=["POST"])
def daily():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
    except:
        return jsonify({"error": "Invalid telegram_id"}), 400

    user = get_user(telegram_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    now = int(time.time())

    if user["last_daily_at"]:
        elapsed = now - user["last_daily_at"]

        if elapsed < 86400:
            return jsonify({
                "error": "Daily reward already claimed",
                "remaining": 86400 - elapsed
            }), 400

    streak = user["streak"] + 1

    reward = DAILY_REWARD + ((streak - 1) * 25)

    conn = db()

    conn.execute("""
        UPDATE users
        SET coins = coins + ?,
            streak = ?,
            last_daily_at = ?
        WHERE telegram_id = ?
    """, (
        reward,
        streak,
        now,
        telegram_id
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "reward": reward,
        "streak": streak
    })


@app.route("/api/tasks", methods=["POST"])
def tasks():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
    except:
        return jsonify({"error": "Invalid telegram_id"}), 400

    conn = db()

    rows = conn.execute("""
        SELECT
            t.id,
            t.title,
            t.description,
            t.reward,
            t.url,
            COALESCE(ut.claimed, 0) AS claimed
        FROM tasks t
        LEFT JOIN user_tasks ut
        ON t.id = ut.task_id
        AND ut.telegram_id = ?
        WHERE t.active = 1
        ORDER BY t.id
    """, (telegram_id,)).fetchall()

    conn.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


@app.route("/api/task/claim", methods=["POST"])
def claim_task():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
        task_id = int(data.get("task_id"))
    except:
        return jsonify({"error": "Invalid data"}), 400

    conn = db()

    task = conn.execute("""
        SELECT *
        FROM tasks
        WHERE id = ?
        AND active = 1
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return jsonify({"error": "Task not found"}), 404

    existing = conn.execute("""
        SELECT claimed
        FROM user_tasks
        WHERE telegram_id = ?
        AND task_id = ?
    """, (
        telegram_id,
        task_id
    )).fetchone()

    if existing and existing["claimed"]:
        conn.close()
        return jsonify({
            "error": "Task already claimed"
        }), 400

    conn.execute("""
        INSERT OR REPLACE INTO user_tasks
        (telegram_id, task_id, claimed)
        VALUES (?, ?, 1)
    """, (
        telegram_id,
        task_id
    ))

    conn.execute("""
        UPDATE users
        SET coins = coins + ?
        WHERE telegram_id = ?
    """, (
        task["reward"],
        telegram_id
    ))

    conn.commit()

    user = conn.execute("""
        SELECT coins
        FROM users
        WHERE telegram_id = ?
    """, (telegram_id,)).fetchone()

    conn.close()

    return jsonify({
        "success": True,
        "reward": task["reward"],
        "coins": user["coins"]
    })


@app.route("/api/referral", methods=["POST"])
def referral():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
    except:
        return jsonify({"error": "Invalid telegram_id"}), 400

    user = get_user(telegram_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    link = (
        "https://t.me/ABBANNURR01_BOT"
        f"?start=ref_{telegram_id}"
    )

    return jsonify({
        "referral_count": user["referral_count"],
        "reward": REFERRAL_REWARD,
        "referral_link": link
    })


@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
    conn = db()

    rows = conn.execute("""
        SELECT
            telegram_id,
            username,
            coins
        FROM users
        ORDER BY coins DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    return jsonify([
        {
            "rank": i + 1,
            "telegram_id": row["telegram_id"],
            "username": row["username"],
            "coins": row["coins"]
        }
        for i, row in enumerate(rows)
    ])


@app.route("/api/wallet/connect", methods=["POST"])
def wallet_connect():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
    except:
        return jsonify({"error": "Invalid telegram_id"}), 400

    wallet = str(
        data.get("wallet_address", "")
    ).strip()

    if not wallet:
        return jsonify({
            "error": "Wallet address required"
        }), 400

    user = get_user(telegram_id)

    if not user:
        return jsonify({
            "error": "User not found"
        }), 404

    conn = db()

    conn.execute("""
        UPDATE users
        SET wallet_address = ?
        WHERE telegram_id = ?
    """, (
        wallet,
        telegram_id
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "wallet_address": wallet
    })


@app.route("/api/wallet/disconnect", methods=["POST"])
def wallet_disconnect():
    data = request.get_json(silent=True) or {}

    try:
        telegram_id = int(data.get("telegram_id"))
    except:
        return jsonify({"error": "Invalid telegram_id"}), 400

    conn = db()

    conn.execute("""
        UPDATE users
        SET wallet_address = ''
        WHERE telegram_id = ?
    """, (telegram_id,))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


if __name__ == "__main__":
    init_db()

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port
)
