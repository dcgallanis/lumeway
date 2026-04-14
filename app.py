from flask import Flask, request, jsonify, send_from_directory, send_file, Response, render_template_string, redirect, session as flask_session, make_response
from flask_cors import CORS
import anthropic
from collections import defaultdict
from cryptography.fernet import Fernet
import csv
import glob as globmod
import hashlib
import io
import json
import markdown
import os
import random
import re
import secrets
import sqlite3
import time as time_module
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests as http_requests
import stripe
import threading
import uuid
try:
    import jwt as pyjwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False
try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
try:
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
import conversation_log

load_dotenv()


def validate_file_type(file_stream, filename):
    """Validate file type by magic bytes, not just extension."""
    header = file_stream.read(8)
    file_stream.seek(0)

    ext = os.path.splitext(filename)[1].lower()

    # Magic byte signatures
    signatures = {
        '.pdf': [b'%PDF'],
        '.jpg': [b'\xff\xd8\xff'],
        '.jpeg': [b'\xff\xd8\xff'],
        '.png': [b'\x89PNG'],
        '.gif': [b'GIF87a', b'GIF89a'],
        '.doc': [b'\xd0\xcf\x11\xe0'],  # OLE2 compound document
        '.docx': [b'PK\x03\x04'],  # ZIP-based (Office Open XML)
        '.xlsx': [b'PK\x03\x04'],  # ZIP-based
        '.xls': [b'\xd0\xcf\x11\xe0'],  # OLE2
        '.csv': None,  # Text-based, skip magic byte check
        '.txt': None,  # Text-based, skip magic byte check
        '.webp': [b'RIFF'],  # WebP image format
    }

    if ext not in signatures:
        return False

    expected = signatures[ext]
    if expected is None:
        return True  # Text-based formats, can't validate by magic bytes

    for sig in expected:
        if header[:len(sig)] == sig:
            return True

    return False


def get_encryption_key():
    """Get file encryption key from env var, then local file fallback."""
    # Prefer environment variable (survives Railway deploys)
    env_key = os.environ.get("FILE_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key
    # Fallback: local file (works in dev, but ephemeral on Railway)
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".file_encryption_key")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            key = f.read()
        # Print it so you can save it as env var
        print(f"[IMPORTANT] FILE_ENCRYPTION_KEY not set. Using local key: {key.decode()}")
        print(f"[IMPORTANT] Set this as FILE_ENCRYPTION_KEY env var to persist across deploys!")
        return key
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
    print(f"[IMPORTANT] Generated new encryption key: {key.decode()}")
    print(f"[IMPORTANT] Set FILE_ENCRYPTION_KEY={key.decode()} in your environment!")
    return key

FILE_ENCRYPTION_KEY = get_encryption_key()
file_cipher = Fernet(FILE_ENCRYPTION_KEY)


# ── File Storage Layer (S3 with local fallback) ──

S3_BUCKET = os.environ.get("S3_BUCKET")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
USE_S3 = bool(S3_BUCKET and HAS_BOTO3)

if USE_S3:
    s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    print(f"[Storage] Using S3 bucket: {S3_BUCKET}")
else:
    s3_client = None
    print("[Storage] Using local disk (set S3_BUCKET to enable S3)")


def storage_save(user_id, stored_name, encrypted_data):
    """Save encrypted file to S3 or local disk."""
    s3_key = f"user-files/{user_id}/{stored_name}"
    if USE_S3:
        s3_client.put_object(
            Bucket=S3_BUCKET, Key=s3_key, Body=encrypted_data,
            ServerSideEncryption="AES256",
            Metadata={"user_id": str(user_id)},
        )
    else:
        user_dir = os.path.join("uploads", str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, stored_name), "wb") as out:
            out.write(encrypted_data)


def storage_load(user_id, stored_name):
    """Load encrypted file from S3 or local disk. Returns bytes or None."""
    s3_key = f"user-files/{user_id}/{stored_name}"
    if USE_S3:
        try:
            resp = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            return resp["Body"].read()
        except ClientError:
            return None
    else:
        filepath = os.path.join("uploads", str(user_id), stored_name)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "rb") as f:
            return f.read()


def storage_delete(user_id, stored_name):
    """Delete file from S3 or local disk."""
    s3_key = f"user-files/{user_id}/{stored_name}"
    if USE_S3:
        try:
            s3_client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        except ClientError:
            pass
    else:
        filepath = os.path.join("uploads", str(user_id), stored_name)
        if os.path.exists(filepath):
            os.remove(filepath)


def audit_log(user_id, action, resource_type=None, resource_id=None, detail=None):
    """Log a security-relevant action."""
    try:
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        if "," in ip:
            ip = ip.split(",")[0].strip()
        now = datetime.utcnow().isoformat()
        db_execute(conn, f"""INSERT INTO audit_log (user_id, action, resource_type, resource_id, detail, ip_address, created_at)
            VALUES ({param},{param},{param},{param},{param},{param},{param})""",
            (user_id, action, resource_type, resource_id, detail, ip, now))
        conn.commit()
        conn.close()
    except Exception:
        pass  # Don't let audit logging failures break the app


upload_rate_limit = defaultdict(list)

def check_upload_rate(user_id, max_uploads=20, window=3600):
    """Allow max_uploads per window (seconds). Returns True if allowed."""
    now = time_module.time()
    upload_rate_limit[user_id] = [t for t in upload_rate_limit[user_id] if now - t < window]
    if len(upload_rate_limit[user_id]) >= max_uploads:
        return False
    upload_rate_limit[user_id].append(now)
    return True


app = Flask(__name__, static_folder=".", static_url_path="/static")
# Use a stable fallback key so sessions survive app restarts when SECRET_KEY env var is not set
_FALLBACK_SECRET = "lumeway-dev-secret-key-change-in-production-2024"
app.secret_key = os.environ.get("SECRET_KEY", _FALLBACK_SECRET)
if app.secret_key == _FALLBACK_SECRET and not os.environ.get("FLASK_ENV") == "development":
    import warnings
    warnings.warn("SECRET_KEY not set! Using fallback. Set SECRET_KEY env var in production.", stacklevel=2)
app.permanent_session_lifetime = timedelta(days=7)
CORS(app)

# JWT config for mobile app auth
JWT_SECRET = os.environ.get("JWT_SECRET", app.secret_key)
JWT_ACCESS_EXPIRY = timedelta(hours=24)
JWT_REFRESH_EXPIRY = timedelta(days=30)

def generate_jwt(user_id, expiry=None):
    """Generate a JWT access token for mobile auth."""
    if not HAS_JWT:
        return None
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + (expiry or JWT_ACCESS_EXPIRY),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_jwt(token):
    """Decode and validate a JWT token. Returns user_id or None."""
    if not HAS_JWT:
        return None
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return int(payload["sub"])
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError, KeyError, ValueError):
        return None


@app.before_request
def force_https():
    if request.headers.get('X-Forwarded-Proto') == 'http' and not request.host.startswith('localhost') and not request.host.startswith('127.'):
        return redirect(request.url.replace('http://', 'https://'), code=301)


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # Prevent browsers from caching HTML pages (so deploys take effect immediately)
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PK = os.environ.get("STRIPE_PUBLISHABLE_KEY", "pk_live_51TFe15F2xDmfC6kmDm4emI9w3eeL0OHv7TmfYWmjr4BXFa9q23TgaEWjjD4HMLJXNwaaWGZRovgKxMeoqAW2TDSz00lcV0duqv")

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.errors

SQLITE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lumeway_subscribers.db")

def get_db():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect(SQLITE_DB)

def db_execute(conn, sql, params=None):
    """Execute SQL on both Postgres (cursor) and SQLite (connection)."""
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur
    else:
        return conn.execute(sql, params or ())

def init_subscribers_db():
    conn = get_db()
    if USE_POSTGRES:
        db_execute(conn, """CREATE TABLE IF NOT EXISTS subscribers (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            source TEXT DEFAULT 'popup',
            transition_category TEXT,
            subscribed_at TEXT NOT NULL,
            unsubscribed_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS purchases (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            stripe_session_id TEXT UNIQUE,
            stripe_payment_intent TEXT,
            purchased_at TEXT NOT NULL,
            download_token TEXT,
            fulfilled BOOLEAN DEFAULT FALSE
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            transition_type TEXT,
            us_state TEXT,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS auth_codes (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            started_at TEXT NOT NULL,
            ended_at TEXT,
            transition_category TEXT,
            user_state TEXT,
            disclaimer_displayed BOOLEAN DEFAULT FALSE,
            boundary_redirection_count INTEGER DEFAULT 0,
            crisis_resources_provided BOOLEAN DEFAULT FALSE,
            templates_mentioned TEXT DEFAULT '[]',
            duration_seconds REAL,
            flagged_for_review BOOLEAN DEFAULT FALSE
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS checklist_items (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            transition_type TEXT NOT NULL,
            phase TEXT NOT NULL,
            item_text TEXT NOT NULL,
            is_completed BOOLEAN DEFAULT FALSE,
            completed_at TEXT,
            sort_order INTEGER DEFAULT 0
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS template_ideas (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            idea TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_notes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_deadlines (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            transition_type TEXT,
            title TEXT NOT NULL,
            deadline_date TEXT NOT NULL,
            note TEXT,
            is_completed BOOLEAN DEFAULT FALSE,
            source TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_documents_needed (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            transition_type TEXT,
            document_name TEXT NOT NULL,
            description TEXT,
            is_gathered BOOLEAN DEFAULT FALSE,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_goals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            target_date TEXT,
            is_completed BOOLEAN DEFAULT FALSE,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_activity_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            action_type TEXT NOT NULL,
            contact_name TEXT,
            organization TEXT,
            description TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_files (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            category TEXT DEFAULT 'other',
            file_size INTEGER,
            content_type TEXT,
            uploaded_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            detail TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_feedback (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            email TEXT,
            area TEXT NOT NULL,
            rating INTEGER,
            message TEXT NOT NULL,
            page_url TEXT,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS file_edits (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            html_content TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, file_id)
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS push_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            platform TEXT DEFAULT 'ios',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, token)
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_posts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            transition_category TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            is_pinned INTEGER DEFAULT 0,
            is_hidden INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_replies (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            parent_reply_id INTEGER,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            body TEXT NOT NULL,
            is_hidden INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_likes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            post_id INTEGER,
            reply_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, post_id, reply_id)
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_reports (
            id SERIAL PRIMARY KEY,
            reporter_user_id INTEGER NOT NULL,
            post_id INTEGER,
            reply_id INTEGER,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
    else:
        db_execute(conn, """CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            source TEXT DEFAULT 'popup',
            transition_category TEXT,
            subscribed_at TEXT NOT NULL,
            unsubscribed_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            stripe_session_id TEXT UNIQUE,
            stripe_payment_intent TEXT,
            purchased_at TEXT NOT NULL,
            download_token TEXT,
            fulfilled INTEGER DEFAULT 0
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            display_name TEXT,
            transition_type TEXT,
            us_state TEXT,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS auth_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            started_at TEXT NOT NULL,
            ended_at TEXT,
            transition_category TEXT,
            user_state TEXT,
            disclaimer_displayed INTEGER DEFAULT 0,
            boundary_redirection_count INTEGER DEFAULT 0,
            crisis_resources_provided INTEGER DEFAULT 0,
            templates_mentioned TEXT DEFAULT '[]',
            duration_seconds REAL,
            flagged_for_review INTEGER DEFAULT 0
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS checklist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            transition_type TEXT NOT NULL,
            phase TEXT NOT NULL,
            item_text TEXT NOT NULL,
            is_completed INTEGER DEFAULT 0,
            completed_at TEXT,
            sort_order INTEGER DEFAULT 0
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS template_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            idea TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_deadlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            transition_type TEXT,
            title TEXT NOT NULL,
            deadline_date TEXT NOT NULL,
            note TEXT,
            is_completed INTEGER DEFAULT 0,
            source TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_documents_needed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            transition_type TEXT,
            document_name TEXT NOT NULL,
            description TEXT,
            is_gathered INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            target_date TEXT,
            is_completed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            action_type TEXT NOT NULL,
            contact_name TEXT,
            organization TEXT,
            description TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            category TEXT DEFAULT 'other',
            file_size INTEGER,
            content_type TEXT,
            uploaded_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            detail TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT,
            area TEXT NOT NULL,
            rating INTEGER,
            message TEXT NOT NULL,
            page_url TEXT,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS file_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            html_content TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, file_id)
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS push_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            platform TEXT DEFAULT 'ios',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, token)
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            transition_category TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            is_pinned INTEGER DEFAULT 0,
            is_hidden INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            parent_reply_id INTEGER,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            body TEXT NOT NULL,
            is_hidden INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER,
            reply_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, post_id, reply_id)
        )""")
        db_execute(conn, """CREATE TABLE IF NOT EXISTS community_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_user_id INTEGER NOT NULL,
            post_id INTEGER,
            reply_id INTEGER,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
    conn.commit()
    # Tier columns migration (idempotent)
    for alter_sql in [
        "ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'free'",
        "ALTER TABLE users ADD COLUMN tier_transition TEXT",
        "ALTER TABLE users ADD COLUMN tier_expires_at TEXT",
        "ALTER TABLE users ADD COLUMN stripe_customer_id TEXT",
        "ALTER TABLE users ADD COLUMN subscription_cancel_at TEXT",
        "ALTER TABLE users ADD COLUMN credit_cents INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN active_transitions TEXT DEFAULT '[]'",
    ]:
        try:
            conn2 = get_db()
            db_execute(conn2, alter_sql)
            conn2.commit()
            conn2.close()
        except Exception:
            try:
                conn2.close()
            except Exception:
                pass
    for icon_sql in [
        "ALTER TABLE users ADD COLUMN community_icon TEXT DEFAULT '☀️'",
        "ALTER TABLE users ADD COLUMN community_icon_bg TEXT DEFAULT ''",
    ]:
        try:
            conn3 = get_db()
            db_execute(conn3, icon_sql)
            conn3.commit()
            conn3.close()
        except Exception:
            try:
                conn3.close()
            except Exception:
                pass
    # Onboarding source column (for gift recipients)
    try:
        conn_obs = get_db()
        if USE_POSTGRES:
            db_execute(conn_obs, "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_source TEXT DEFAULT NULL")
        else:
            db_execute(conn_obs, "ALTER TABLE users ADD COLUMN onboarding_source TEXT DEFAULT NULL")
        conn_obs.commit()
        conn_obs.close()
    except Exception:
        try:
            conn_obs.rollback()
            conn_obs.close()
        except Exception:
            pass
    # Etsy redemptions table (idempotent)
    try:
        conn_etsy = get_db()
        if USE_POSTGRES:
            db_execute(conn_etsy, """CREATE TABLE IF NOT EXISTS etsy_redemptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                category TEXT NOT NULL,
                credit_cents INTEGER NOT NULL DEFAULT 1600,
                redeemed_at TEXT NOT NULL
            )""")
        else:
            db_execute(conn_etsy, """CREATE TABLE IF NOT EXISTS etsy_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                category TEXT NOT NULL,
                credit_cents INTEGER NOT NULL DEFAULT 1600,
                redeemed_at TEXT NOT NULL
            )""")
        conn_etsy.commit()
        conn_etsy.close()
    except Exception:
        try:
            conn_etsy.close()
        except Exception:
            pass
    # Gift codes table (idempotent)
    try:
        conn_gift = get_db()
        if USE_POSTGRES:
            db_execute(conn_gift, """CREATE TABLE IF NOT EXISTS gift_codes (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                purchaser_email TEXT NOT NULL,
                purchaser_name TEXT,
                recipient_name TEXT,
                gift_type TEXT NOT NULL,
                gift_label TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                stripe_session_id TEXT,
                redeemed_by INTEGER,
                redeemed_at TEXT,
                transition_category TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )""")
            # Migration: add transition_category if missing
            try:
                db_execute(conn_gift, "ALTER TABLE gift_codes ADD COLUMN IF NOT EXISTS transition_category TEXT DEFAULT ''")
                conn_gift.commit()
            except Exception:
                pass
        else:
            db_execute(conn_gift, """CREATE TABLE IF NOT EXISTS gift_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                purchaser_email TEXT NOT NULL,
                purchaser_name TEXT,
                recipient_name TEXT,
                gift_type TEXT NOT NULL,
                gift_label TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                stripe_session_id TEXT,
                redeemed_by INTEGER,
                redeemed_at TEXT,
                transition_category TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )""")
        conn_gift.commit()
        conn_gift.close()
    except Exception:
        try:
            conn_gift.close()
        except Exception:
            pass
    # Expenses table (idempotent)
    try:
        conn3 = get_db()
        if USE_POSTGRES:
            db_execute(conn3, """CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                payment_method TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            )""")
        else:
            db_execute(conn3, """CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                payment_method TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            )""")
        conn3.commit()
        conn3.close()
    except Exception:
        try:
            conn3.close()
        except Exception:
            pass
    # Revenue entries table (for manual revenue like Etsy sales)
    try:
        conn4 = get_db()
        if USE_POSTGRES:
            db_execute(conn4, """CREATE TABLE IF NOT EXISTS revenue_entries (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )""")
        else:
            db_execute(conn4, """CREATE TABLE IF NOT EXISTS revenue_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL
            )""")
        conn4.commit()
        conn4.close()
    except Exception:
        try:
            conn4.close()
        except Exception:
            pass
    # Email queue table (for post-purchase sequences)
    try:
        conn_eq = get_db()
        if USE_POSTGRES:
            db_execute(conn_eq, """CREATE TABLE IF NOT EXISTS email_queue (
                id SERIAL PRIMARY KEY,
                to_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                html_body TEXT NOT NULL,
                sequence_name TEXT,
                sequence_step INTEGER,
                send_after TEXT NOT NULL,
                sent_at TEXT,
                error TEXT,
                created_at TEXT NOT NULL
            )""")
        else:
            db_execute(conn_eq, """CREATE TABLE IF NOT EXISTS email_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                to_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                html_body TEXT NOT NULL,
                sequence_name TEXT,
                sequence_step INTEGER,
                send_after TEXT NOT NULL,
                sent_at TEXT,
                error TEXT,
                created_at TEXT NOT NULL
            )""")
        conn_eq.commit()
        conn_eq.close()
    except Exception:
        try:
            conn_eq.close()
        except Exception:
            pass
    # Community forum tables (idempotent migration)
    try:
        conn_cm = get_db()
        if USE_POSTGRES:
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_posts (
                id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, display_name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general', transition_category TEXT,
                title TEXT NOT NULL, body TEXT NOT NULL, is_pinned INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT)""")
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_replies (
                id SERIAL PRIMARY KEY, post_id INTEGER NOT NULL REFERENCES community_posts(id),
                parent_reply_id INTEGER, user_id INTEGER NOT NULL, display_name TEXT NOT NULL, body TEXT NOT NULL,
                is_hidden INTEGER DEFAULT 0, created_at TEXT NOT NULL)""")
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_likes (
                id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, post_id INTEGER,
                reply_id INTEGER, created_at TEXT NOT NULL, UNIQUE(user_id, post_id, reply_id))""")
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_reports (
                id SERIAL PRIMARY KEY, reporter_user_id INTEGER NOT NULL,
                post_id INTEGER, reply_id INTEGER, reason TEXT NOT NULL, created_at TEXT NOT NULL)""")
        else:
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, display_name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general', transition_category TEXT,
                title TEXT NOT NULL, body TEXT NOT NULL, is_pinned INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT)""")
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL REFERENCES community_posts(id),
                parent_reply_id INTEGER, user_id INTEGER NOT NULL, display_name TEXT NOT NULL, body TEXT NOT NULL,
                is_hidden INTEGER DEFAULT 0, created_at TEXT NOT NULL)""")
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, post_id INTEGER,
                reply_id INTEGER, created_at TEXT NOT NULL, UNIQUE(user_id, post_id, reply_id))""")
            db_execute(conn_cm, """CREATE TABLE IF NOT EXISTS community_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_user_id INTEGER NOT NULL,
                post_id INTEGER, reply_id INTEGER, reason TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn_cm.commit()
        conn_cm.close()
    except Exception:
        try:
            conn_cm.close()
        except Exception:
            pass
    # Community column migrations (idempotent — for tables created before these columns existed)
    for alter_sql in [
        "ALTER TABLE community_posts ADD COLUMN transition_category TEXT",
        "ALTER TABLE community_replies ADD COLUMN parent_reply_id INTEGER",
        "ALTER TABLE community_posts ADD COLUMN icon TEXT DEFAULT '😊'",
        "ALTER TABLE community_replies ADD COLUMN icon TEXT DEFAULT '😊'",
    ]:
        try:
            conn_alt = get_db()
            db_execute(conn_alt, alter_sql)
            conn_alt.commit()
            conn_alt.close()
        except Exception:
            try:
                conn_alt.close()
            except Exception:
                pass
    # ── Migration version tracking (ensures one-time migrations only run once) ──
    try:
        conn_mig = get_db()
        if USE_POSTGRES:
            db_execute(conn_mig, """CREATE TABLE IF NOT EXISTS migrations (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, applied_at TEXT NOT NULL)""")
        else:
            db_execute(conn_mig, """CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, applied_at TEXT NOT NULL)""")
        conn_mig.commit()
        conn_mig.close()
    except Exception:
        try:
            conn_mig.close()
        except Exception:
            pass

    def migration_done(name):
        """Check if a named migration has already run."""
        try:
            c = get_db()
            p = "%s" if USE_POSTGRES else "?"
            cur = db_execute(c, f"SELECT COUNT(*) FROM migrations WHERE name = {p}", (name,))
            done = cur.fetchone()[0] > 0
            c.close()
            return done
        except Exception:
            return False

    def mark_migration(name):
        """Mark a named migration as complete."""
        try:
            c = get_db()
            p = "%s" if USE_POSTGRES else "?"
            db_execute(c, f"INSERT INTO migrations (name, applied_at) VALUES ({p}, {p})", (name, datetime.utcnow().isoformat()))
            c.commit()
            c.close()
        except Exception:
            pass

    # ── One-time seed cleanup (v3): update old seed data IN PLACE instead of deleting ──
    if not migration_done("community_seed_v3"):
        try:
            conn_seed = get_db()
            param_s = "%s" if USE_POSTGRES else "?"

            # Update "Carol" → "Cara" on any seed posts
            db_execute(conn_seed, f"UPDATE community_posts SET display_name = {param_s}, icon = {param_s} WHERE user_id = 0 AND display_name = {param_s}", ("Cara", "✨", "Carol"))
            db_execute(conn_seed, f"UPDATE community_replies SET display_name = {param_s}, icon = {param_s} WHERE user_id = 0 AND display_name = {param_s}", ("Cara", "✨", "Carol"))

            # Remove last-name initials from seed data (update in place, preserve IDs)
            for old_name, new_name, icon in [("Sarah M.", "Sarah", "🌸"), ("James K.", "James", "🌊"), ("Maria L.", "Maria", "🌿"), ("David R.", "David", "🎯")]:
                db_execute(conn_seed, f"UPDATE community_posts SET display_name = {param_s}, icon = {param_s} WHERE user_id = 0 AND display_name = {param_s}", (new_name, icon, old_name))
                db_execute(conn_seed, f"UPDATE community_replies SET display_name = {param_s}, icon = {param_s} WHERE user_id = 0 AND display_name = {param_s}", (new_name, icon, old_name))

            # Add icons to seed posts/replies that don't have one yet
            for name, icon in [("Cara", "✨"), ("Sarah", "🌸"), ("James", "🌊"), ("Maria", "🌿"), ("David", "🎯"), ("Anonymous", "🦋")]:
                db_execute(conn_seed, f"UPDATE community_posts SET icon = {param_s} WHERE user_id = 0 AND display_name = {param_s} AND (icon IS NULL OR icon = {param_s})", (icon, name, "😊"))
                db_execute(conn_seed, f"UPDATE community_replies SET icon = {param_s} WHERE user_id = 0 AND display_name = {param_s} AND (icon IS NULL OR icon = {param_s})", (icon, name, "😊"))

            # Clean up orphaned likes (likes on posts/replies that no longer exist)
            db_execute(conn_seed, "DELETE FROM community_likes WHERE post_id IS NOT NULL AND post_id NOT IN (SELECT id FROM community_posts)")
            db_execute(conn_seed, "DELETE FROM community_likes WHERE reply_id IS NOT NULL AND reply_id NOT IN (SELECT id FROM community_replies)")

            conn_seed.commit()
            conn_seed.close()
            mark_migration("community_seed_v3")
            print("[community] Updated seed data in place (v3 — no deletes, likes preserved)")
        except Exception as e:
            print(f"[community] Seed update error (non-fatal): {e}")
            try:
                conn_seed.close()
            except Exception:
                pass

    # ── Auto-seed community if no posts exist at all ──
    if not migration_done("community_initial_seed"):
        try:
            conn_seed = get_db()
            param_s = "%s" if USE_POSTGRES else "?"
            cur_s = db_execute(conn_seed, "SELECT COUNT(*) FROM community_posts")
            if cur_s.fetchone()[0] == 0:
                from datetime import timedelta
                now = datetime.utcnow()
                seeds = [
                    {"name": "Cara", "icon": "✨", "cat": "general", "trans": None, "title": "Welcome to the Lumeway community",
                     "body": "Hey, so glad you are here.\n\nI built Lumeway because when I was going through my own life transition, I kept wishing someone would just tell me what to do next. Not in a preachy way, just like a friend who had been through it and could walk me through the steps.\n\nThat is what this community is for. Whether you are dealing with a divorce, a job loss, an estate, or something else entirely — you are not alone and there are people here who genuinely get it.\n\nNo question is too small, no vent is too messy. Jump in whenever you are ready.", "pin": 1, "ago": timedelta(days=3)},
                    {"name": "Sarah", "icon": "🌸", "cat": "emotional-support", "trans": "divorce", "title": "How do you handle the loneliness?",
                     "body": "I am about three months into my separation and the evenings are the hardest. The house feels so quiet. I know it gets better but some days it is really hard to believe that.\n\nAnyone else going through this? What has helped you?", "pin": 0, "ago": timedelta(days=2, hours=8)},
                    {"name": "James", "icon": "🌊", "cat": "financial", "trans": "job-loss", "title": "Negotiating severance - what I wish I knew",
                     "body": "Just went through a layoff and wanted to share something I learned the hard way. Your initial severance offer is almost always negotiable. I asked for an extra two weeks and they said yes immediately.\n\nThings worth asking about: extended health insurance coverage, outplacement services, a neutral reference letter, and keeping your laptop.\n\nHas anyone else had luck negotiating? Would love to hear what worked for you.", "pin": 0, "ago": timedelta(days=2)},
                    {"name": "Maria", "icon": "🌿", "cat": "legal-questions", "trans": "estate", "title": "Probate timeline - how long did yours take?",
                     "body": "My mom passed away two months ago and the attorney said probate could take 6 to 12 months. That feels like forever when you are trying to handle everything.\n\nHow long did the process take for others? Any tips for keeping things moving?", "pin": 0, "ago": timedelta(days=1, hours=14)},
                    {"name": "David", "icon": "🎯", "cat": "success-stories", "trans": "job-loss", "title": "Landed a new role after 4 months",
                     "body": "Just wanted to share some hope for anyone in the thick of a job search. I was laid off in December and it was honestly one of the lowest points of my life. But I just accepted an offer that is actually a better fit than my old job.\n\nWhat helped me most was having a system. The checklist on here kept me from spiraling and just taking it one task at a time made a huge difference.\n\nHang in there. It does get better.", "pin": 0, "ago": timedelta(days=1, hours=4)},
                    {"name": "Anonymous", "icon": "🦋", "cat": "ask-cara", "trans": "divorce", "title": "Do I need a lawyer if we agree on everything?",
                     "body": "My spouse and I are splitting amicably. We have already agreed on how to divide everything and we do not have kids. Do we still need to hire lawyers or can we just file the paperwork ourselves?\n\nTrying to keep costs down but also do not want to make a mistake.", "pin": 0, "ago": timedelta(hours=18)},
                ]
                seed_post_ids = []
                for s in seeds:
                    ts = (now - s["ago"]).isoformat()
                    db_execute(conn_seed, f"""INSERT INTO community_posts (user_id, display_name, category, transition_category, title, body, is_pinned, icon, created_at)
                        VALUES ({param_s}, {param_s}, {param_s}, {param_s}, {param_s}, {param_s}, {param_s}, {param_s}, {param_s})""",
                        (0, s["name"], s["cat"], s["trans"], s["title"], s["body"], s["pin"], s["icon"], ts))
                conn_seed.commit()
                for s in seeds:
                    cur_s = db_execute(conn_seed, f"SELECT id FROM community_posts WHERE title = {param_s} ORDER BY id DESC LIMIT 1", (s["title"],))
                    row = cur_s.fetchone()
                    seed_post_ids.append(row[0] if row else None)
                seed_replies = {
                    0: [
                        {"name": "Sarah", "body": "This is exactly what I needed. Just knowing other people are going through the same thing makes such a difference.", "ago": timedelta(days=2, hours=20)},
                        {"name": "James", "body": "Really glad this exists. Sometimes you just need to talk to people who get it.", "ago": timedelta(days=2, hours=16)},
                        {"name": "Cara", "body": "So happy you are both here. Seriously, do not be shy about posting. Even if it is just to vent. That is what this space is for.", "ago": timedelta(days=2, hours=10)},
                    ],
                    1: [
                        {"name": "Cara", "body": "Three months in is still so early, so please be gentle with yourself. The quiet evenings are the worst part for a lot of people.\n\nA few things that have helped others: a small after-dinner routine (even just a walk or a podcast), keeping a text thread going with a friend, or picking up one low-effort hobby that gets you out of your head. You do not have to fill the silence with anything productive. Just something that is yours.", "ago": timedelta(days=2, hours=2)},
                        {"name": "David", "body": "I went through something similar after my divorce. What helped me was finding one thing to look forward to each evening, even something small. A show, a call with a friend, cooking something new. It does get easier.", "ago": timedelta(days=1, hours=20)},
                        {"name": "Maria", "body": "Sending you a hug. The evenings were the hardest for me too. I started journaling before bed and it honestly helped more than I expected.", "ago": timedelta(days=1, hours=16)},
                    ],
                    2: [
                        {"name": "Cara", "body": "This is such good advice. A lot of people do not realize severance is negotiable because they are in shock when it happens.\n\nOne thing to add: if your company offered a severance agreement, you usually have 21 days to review it (45 days if you are over 40 — that is federal law). So do not feel pressured to sign on the spot. Use that time to negotiate or have an employment attorney look it over.", "ago": timedelta(days=1, hours=18)},
                        {"name": "Sarah", "body": "I wish I had known this. I signed mine the same day because I was so overwhelmed. Great share.", "ago": timedelta(days=1, hours=14)},
                    ],
                    3: [
                        {"name": "Cara", "body": "6 to 12 months is pretty standard, but it really depends on the state and how complex the estate is. A few things that can speed things up:\n\n- Stay on top of deadlines your attorney gives you. A lot of delays happen because paperwork sits.\n- Get multiple copies of the death certificate early (you will need more than you think).\n- If there are no disputes among heirs, things tend to move faster.\n\nAlso worth asking your attorney about small estate shortcuts — some states let you skip formal probate if the estate is under a certain value.", "ago": timedelta(days=1, hours=8)},
                        {"name": "James", "body": "My family went through probate last year. Took about 8 months in our case. The biggest thing that helped was having one person be the point of contact for the attorney so nothing fell through the cracks.", "ago": timedelta(days=1, hours=4)},
                    ],
                    4: [
                        {"name": "Cara", "body": "Love hearing this. And you are so right about having a system. When everything feels out of control, just having a list of what to do next makes a huge difference. Congrats on the new role.", "ago": timedelta(hours=22)},
                        {"name": "Sarah", "body": "This gives me so much hope. Thank you for sharing.", "ago": timedelta(hours=20)},
                        {"name": "Maria", "body": "Congrats. Four months is tough but you made it through. Inspiring.", "ago": timedelta(hours=16)},
                    ],
                    5: [
                        {"name": "Cara", "body": "So this is one of those situations where a little money upfront can save you a lot of headaches later. Even if you agree on everything, there are things you might not think of — like how retirement accounts get divided (that needs a special court order called a QDRO), tax filing status for the year, and whether your state requires specific language in the agreement.\n\nYou probably do not need full representation. A lot of family law attorneys offer a one-time document review for a flat fee. It is worth it just for the peace of mind.\n\nCheck out your state bar association or lawhelp.org for lower-cost options.", "ago": timedelta(hours=12)},
                        {"name": "David", "body": "We did ours without lawyers and regretted it later when we realized we missed some retirement account stuff. Definitely get at least a consultation.", "ago": timedelta(hours=8)},
                    ],
                }
                seed_icons = {"Cara": "✨", "Sarah": "🌸", "James": "🌊", "Maria": "🌿", "David": "🎯", "Anonymous": "🦋"}
                for idx, reply_list in seed_replies.items():
                    pid = seed_post_ids[idx] if idx < len(seed_post_ids) else None
                    if pid:
                        for rpl in reply_list:
                            ts = (now - rpl["ago"]).isoformat()
                            rpl_icon = seed_icons.get(rpl["name"], "😊")
                            db_execute(conn_seed, f"""INSERT INTO community_replies (post_id, user_id, display_name, body, icon, created_at)
                                VALUES ({param_s}, {param_s}, {param_s}, {param_s}, {param_s}, {param_s})""",
                                (pid, 0, rpl["name"], rpl["body"], rpl_icon, ts))
                conn_seed.commit()
                print("[community] Seeded 6 starter conversations with replies")
            mark_migration("community_initial_seed")
            conn_seed.close()
        except Exception as e:
            print(f"[community] Seed error (non-fatal): {e}")
            try:
                conn_seed.close()
            except Exception:
                pass
    conn.close()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "re_17DAfkrF_3mB4pCdStfmYHiNQoeKrxaWe")

def send_community_notification(event_type, display_name, title, body_preview, post_id):
    """Send notification email to admin when new community post or reply is created."""
    if not RESEND_API_KEY:
        return
    subject = f"Community {event_type}: {title[:60]}" if event_type == "post" else f"Community reply on: {title[:60]}"
    preview = body_preview[:200] + "..." if len(body_preview) > 200 else body_preview
    dashboard_url = f"https://lumeway.co/dashboard"
    html = email_wrap(f"""
<p style="{_e_hi}">New community {event_type}</p>
<p style="{_e_p}"><strong>{display_name}</strong> {"posted" if event_type == "post" else "replied to"}: <em>{title}</em></p>
<p style="{_e_p}">{preview}</p>
{_e_btn(dashboard_url, 'View in Dashboard')}""")
    try:
        http_requests.post("https://api.resend.com/emails", json={
            "from": "Lumeway <hello@lumeway.co>",
            "to": ["hello@lumeway.co"],
            "subject": subject,
            "html": html,
        }, headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        })
    except Exception as e:
        print(f"[community] Notification email error: {e}")


def send_purchase_email(to_email, product_id, product_name, download_token):
    """Send purchase confirmation with download link via Resend."""
    if not RESEND_API_KEY:
        print(f"RESEND_API_KEY not set, skipping email to {to_email}")
        return False
    download_url = f"https://lumeway.co/download/{download_token}"
    html = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">Thank you for your purchase. Your <strong>{product_name}</strong> is ready to download.</p>
{_e_btn(download_url, 'Download Your Templates')}
<p style="{_e_muted}margin-bottom:8px;">This link is unique to your purchase and does not expire.</p>
<p style="{_e_muted}">If you have any questions, just reply to this email.</p>""")
    try:
        resp = http_requests.post("https://api.resend.com/emails", json={
            "from": "Lumeway <hello@lumeway.co>",
            "to": [to_email],
            "subject": f"Your {product_name} is ready",
            "html": html,
        }, headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }, timeout=10)
        if resp.status_code == 200:
            print(f"Purchase email sent to {to_email}")
            return True
        else:
            print(f"Resend error ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

def send_email_via_resend(to_email, subject, html_body):
    """General-purpose email sender using Resend."""
    if not RESEND_API_KEY:
        print(f"RESEND_API_KEY not set, skipping email to {to_email}")
        return False
    try:
        resp = http_requests.post("https://api.resend.com/emails", json={
            "from": "Lumeway <hello@lumeway.co>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }, headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }, timeout=10)
        if resp.status_code == 200:
            print(f"Email sent to {to_email}: {subject}")
            return True
        else:
            print(f"Resend error ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False


def email_wrap(body_html):
    """Wrap email body in the standard Lumeway email template."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background-color:#FAF7F2;font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif;color:#2C3E50;-webkit-font-smoothing:antialiased;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#FAF7F2;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#FDFCFA;border:1px solid #E8E0D6;border-radius:16px;overflow:hidden;">
  <!-- Navy header -->
  <tr><td style="background:linear-gradient(135deg,#2C4A5E,#1B3A4E);padding:30px 36px;text-align:center;">
    <span style="font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:13px;font-weight:600;color:rgba(250,247,242,0.5);letter-spacing:2.5px;text-transform:uppercase;">&#9788;&ensp;LUMEWAY</span>
  </td></tr>
  <!-- Gold accent line -->
  <tr><td style="height:3px;background:linear-gradient(90deg,#B8977E,#D4B49A,#B8977E);font-size:0;line-height:0;">&nbsp;</td></tr>
  <!-- Body -->
  <tr><td style="padding:40px 36px 32px;">
    {body_html}
  </td></tr>
  <!-- Sign-off -->
  <tr><td style="padding:0 36px 36px;">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="width:40px;vertical-align:top;padding-top:2px;">
        <div style="width:32px;height:1px;background-color:#B8977E;margin-top:10px;"></div>
      </td>
      <td style="padding-left:12px;">
        <p style="font-family:'Libre Baskerville',Georgia,serif;font-size:14px;font-style:italic;color:#6B7B8D;line-height:1.6;margin:0;">You got this,</p>
        <p style="font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:13px;font-weight:500;color:#2C4A5E;margin:4px 0 0;">Cara</p>
      </td>
    </tr></table>
  </td></tr>
  <!-- Footer -->
  <tr><td style="background-color:#F5F0E8;padding:24px 36px;border-top:1px solid #E8E0D6;">
    <p style="font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:11px;color:#999;line-height:1.7;margin:0 0 10px;">Lumeway provides organizational tools, not legal or financial advice. Always consult a qualified professional for decisions specific to your situation.</p>
    <p style="font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:11px;color:#bbb;margin:0 0 8px;"><a href="https://lumeway.co" style="color:#2C4A5E;text-decoration:none;font-weight:500;">lumeway.co</a> &nbsp;&middot;&nbsp; <a href="https://lumeway.co/privacy" style="color:#999;text-decoration:none;">Privacy</a> &nbsp;&middot;&nbsp; <a href="https://lumeway.co/contact" style="color:#999;text-decoration:none;">Contact</a></p>
    <p style="font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:10px;color:#ccc;margin:0;">Reply with "unsubscribe" to stop receiving these emails.</p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# ── Email content style helpers ──
_e_hi = "font-family:'Libre Baskerville',Georgia,serif;font-size:18px;color:#2C4A5E;line-height:1.5;margin:0 0 20px;font-weight:400;"
_e_p = "font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:15px;font-weight:300;line-height:1.7;color:#2C3E50;margin:0 0 16px;"
_e_ul = "font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:14px;font-weight:300;line-height:1.9;color:#2C3E50;padding-left:20px;margin:0 0 16px;"
_e_li = "margin-bottom:8px;"
_e_muted = "font-family:'Plus Jakarta Sans',system-ui,sans-serif;font-size:13px;font-weight:300;color:#6B7B8D;line-height:1.6;margin:0;"
_e_btn = lambda url, text: f'<div style="text-align:center;margin:32px 0;"><a href="{url}" style="display:inline-block;padding:14px 32px;background:#C4704E;color:white;text-decoration:none;border-radius:100px;font-family:\'Plus Jakarta Sans\',system-ui,sans-serif;font-size:14px;font-weight:500;letter-spacing:0.3px;">{text}</a></div>'

# ── Post-purchase email sequence templates ──
def get_post_purchase_sequence(product_name, is_plan=False):
    """Return list of (delay_days, subject, html_body) for post-purchase emails."""
    dashboard_url = "https://lumeway.co/dashboard"
    chat_url = "https://lumeway.co/chat"
    pricing_url = "https://lumeway.co/pricing"

    emails = []

    # Day 1: Welcome + orientation
    if is_plan:
        day1_body = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">Your <strong>{product_name}</strong> is set up and ready. Here is what you have access to now:</p>
<ul style="{_e_ul}">
  <li style="{_e_li}">A phased checklist that breaks everything into manageable steps</li>
  <li style="{_e_li}">Step-by-step guides with key terms, contacts, and common mistakes</li>
  <li style="{_e_li}">A deadline calendar so nothing slips through</li>
  <li style="{_e_li}">Document storage to keep everything in one place</li>
</ul>
<p style="{_e_p}">You do not have to do everything today. Start with whatever feels most pressing, and the dashboard will keep track of the rest.</p>
{_e_btn(dashboard_url, 'Open your dashboard')}""")
    else:
        day1_body = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">Your <strong>{product_name}</strong> templates are ready. If you have not downloaded them yet, you can find them in your dashboard under My Templates.</p>
<p style="{_e_p}">These worksheets are designed to help you get organized — budget trackers, inventories, letter templates, and comparison sheets. Fill them out at your own pace.</p>
{_e_btn(dashboard_url, 'Open your dashboard')}""")
    emails.append((1, f"Getting started with your {product_name}", day1_body))

    # Day 3: Gentle check-in
    day3_body = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">Just checking in. If you have had a chance to look at your dashboard, we hope it is helping you feel more organized.</p>
<p style="{_e_p}">If you have not started yet, that is okay. There is no deadline on your end. When you are ready, the Navigator can help you figure out what to focus on first.</p>
{_e_btn(chat_url, 'Talk to the Navigator')}
<p style="{_e_muted}">If something is not working or you have questions, just reply to this email.</p>""")
    emails.append((3, "How are things going?", day3_body))

    # Day 7: Feature highlight
    if is_plan:
        day7_body = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">A few things in your dashboard you might not have found yet:</p>
<ul style="{_e_ul}">
  <li style="{_e_li}"><strong>Activity log</strong> — track phone calls, form submissions, and appointments so you have a record</li>
  <li style="{_e_li}"><strong>Notes</strong> — jot down questions, reminders, or anything on your mind</li>
  <li style="{_e_li}"><strong>Document storage</strong> — upload copies of important paperwork so everything is in one place</li>
</ul>
<p style="{_e_p}">You are doing the hard part. These tools are here to make it a little easier.</p>
{_e_btn(dashboard_url, 'Open your dashboard')}""")
    else:
        day7_body = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">Your templates give you the worksheets. If you want the full picture — step-by-step guides, deadline tracking, state-specific rules, and more — the Full Plan picks up where the templates leave off.</p>
<p style="{_e_p}">And your {product_name} purchase counts as credit toward the upgrade, so you would only pay the difference.</p>
{_e_btn(pricing_url, 'See what is included')}
<p style="{_e_muted}">No pressure. The templates are yours forever either way.</p>""")
    emails.append((7, "A few things you might find helpful", day7_body))

    # Day 20: Progress encouragement
    day20_body = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">It has been a few weeks since you started using Lumeway. However far you have gotten, you are further along than you were before.</p>
<p style="{_e_p}">If you have been putting something off, that is normal. Pick one small thing and start there. The checklist keeps track of everything else so it does not slip through.</p>
{_e_btn(dashboard_url, 'Pick up where you left off')}""")
    emails.append((20, "You are further along than you think", day20_body))

    # Day 28: Feedback request
    day28_body = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">You have been using Lumeway for about a month now. We would genuinely like to know how it is going.</p>
<p style="{_e_p}">Is the dashboard helping? Is anything confusing or missing? We read every reply and use your feedback to make Lumeway better.</p>
<p style="{_e_p}">Just hit reply and tell us what you think — even a sentence or two is helpful.</p>
<p style="{_e_muted}font-style:italic;">Thank you for trusting us with something this important.</p>""")
    emails.append((28, "How is Lumeway working for you?", day28_body))

    return emails


def schedule_post_purchase_emails(to_email, product_name, is_plan=False):
    """Queue the 5-email post-purchase sequence for a buyer."""
    sequence = get_post_purchase_sequence(product_name, is_plan)
    now = datetime.now(timezone.utc)
    sequence_name = f"post-purchase-{product_name[:30]}"
    try:
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        for step, (delay_days, subject, html_body) in enumerate(sequence, 1):
            send_after = (now + timedelta(days=delay_days)).isoformat()
            db_execute(conn, f"""INSERT INTO email_queue
                (to_email, subject, html_body, sequence_name, sequence_step, send_after, created_at)
                VALUES ({param},{param},{param},{param},{param},{param},{param})""",
                (to_email, subject, html_body, sequence_name, step, send_after, now.isoformat()))
        conn.commit()
        conn.close()
        print(f"Scheduled {len(sequence)} post-purchase emails for {to_email}")
    except Exception as e:
        print(f"Error scheduling emails for {to_email}: {e}")
        try:
            conn.close()
        except Exception:
            pass


init_subscribers_db()
os.makedirs("uploads", exist_ok=True)

client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

conversation_log.init_db()

# ── Auth helpers ──

VALID_CATEGORIES = ["job-loss", "estate", "divorce", "disability", "relocation", "retirement", "addiction"]
CATEGORY_LABELS = {
    "job-loss": "Job Loss & Income Crisis",
    "estate": "Death & Estate",
    "divorce": "Divorce & Separation",
    "disability": "Disability & Benefits",
    "relocation": "Moving & Relocation",
    "retirement": "Retirement Planning",
    "addiction": "Addiction & Recovery",
}

# Promo codes — grants full access to everything
PROMO_CODES = {
    "LUMEFRIEND": {"tier": "all_transitions", "label": "Full Access — All Transitions"},
}

# Etsy redemption codes — one per category, reusable
ETSY_CODES = {
    "LUMEWAY-JOBLOSS1": {"category": "job-loss", "credit_cents": 1600},
    "LUMEWAY-ESTATE2": {"category": "estate", "credit_cents": 1600},
    "LUMEWAY-DIVORCE5": {"category": "divorce", "credit_cents": 1600},
    "LUMEWAY-DISABILITY6": {"category": "disability", "credit_cents": 1600},
    "LUMEWAY-RELOCATION4": {"category": "relocation", "credit_cents": 1600},
    "LUMEWAY-RETIREMENT3": {"category": "retirement", "credit_cents": 1600},
    "LUMEWAY-ADDICTION7": {"category": "addiction", "credit_cents": 1600},
    "LUMEWAY-LIFE1": {"category": "master", "credit_cents": 6500},
}

def get_current_user():
    """Return user dict if logged in, else None. Supports session cookies and Bearer JWT."""
    user_id = flask_session.get("user_id")

    # Also check Authorization: Bearer <token> for mobile app
    if not user_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user_id = decode_jwt(token)

    if not user_id:
        return None
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    try:
        cur = db_execute(conn, f"SELECT id, email, display_name, transition_type, us_state, created_at, last_login_at, tier, tier_transition, tier_expires_at, stripe_customer_id, subscription_cancel_at, credit_cents, active_transitions, community_icon, community_icon_bg FROM users WHERE id = {param}", (user_id,))
        row = cur.fetchone()
        cols = ["id", "email", "display_name", "transition_type", "us_state", "created_at", "last_login_at", "tier", "tier_transition", "tier_expires_at", "stripe_customer_id", "subscription_cancel_at", "credit_cents", "active_transitions", "community_icon", "community_icon_bg"]
    except Exception:
        # Fallback if community_icon columns don't exist yet
        if USE_POSTGRES:
            conn.close()
            conn = get_db()
        cur = db_execute(conn, f"SELECT id, email, display_name, transition_type, us_state, created_at, last_login_at, tier, tier_transition, tier_expires_at, stripe_customer_id, subscription_cancel_at, credit_cents, active_transitions FROM users WHERE id = {param}", (user_id,))
        row = cur.fetchone()
        cols = ["id", "email", "display_name", "transition_type", "us_state", "created_at", "last_login_at", "tier", "tier_transition", "tier_expires_at", "stripe_customer_id", "subscription_cancel_at", "credit_cents", "active_transitions"]
    conn.close()
    if row:
        user = dict(zip(cols, row))
        if not user.get("tier"):
            user["tier"] = "free"
        if not user.get("credit_cents"):
            user["credit_cents"] = 0
        # Parse active_transitions from JSON string
        try:
            user["active_transitions"] = json.loads(user.get("active_transitions") or "[]")
        except (json.JSONDecodeError, TypeError):
            user["active_transitions"] = []
        return user
    return None

def get_effective_tier(user):
    """Return the user's effective tier based on active_transitions."""
    active = user.get("active_transitions") or []
    tier = user.get("tier") or "free"
    # Backward compat: if old tier=unlimited or tier=pass, map to new system
    if tier == "unlimited" or tier == "all_transitions":
        return "all_transitions"
    if len(active) >= 6:
        return "all_transitions"
    full_cats = [c for c in active if isinstance(c, dict) and c.get("level") == "full"] if active and isinstance(active[0] if active else None, dict) else []
    starter_cats = [c for c in active if isinstance(c, dict) and c.get("level") == "starter"] if active and isinstance(active[0] if active else None, dict) else []
    # Simple format: active_transitions stores list of {"cat": "job-loss", "level": "full"} dicts
    if full_cats:
        return "one_transition" if len(full_cats) == 1 else "all_transitions" if len(full_cats) >= 6 else "one_transition"
    if starter_cats:
        return "starter"
    # Fallback to old tier column
    if tier == "pass":
        return "one_transition"
    if tier == "starter":
        return "starter"
    return "free"

def get_user_categories(user):
    """Return dict of {category: access_level} from active_transitions."""
    active = user.get("active_transitions") or []
    result = {}
    for item in active:
        if isinstance(item, dict):
            result[item.get("cat", "")] = item.get("level", "starter")
    # Backward compat: old pass users
    if not result and user.get("tier") == "pass" and user.get("tier_transition"):
        result[user["tier_transition"]] = "full"
    # Backward compat: old unlimited users
    if user.get("tier") in ("unlimited", "all_transitions"):
        for cat in VALID_CATEGORIES:
            result[cat] = "full"
    return result

def check_category_access(user, category, required_level="full"):
    """Check if user can access a specific category at the required level.
    Returns (has_access, reason)."""
    cats = get_user_categories(user)
    user_level = cats.get(category)
    if required_level == "starter" and user_level in ("starter", "full"):
        return (True, None)
    if required_level == "full" and user_level == "full":
        return (True, None)
    if user_level == "starter":
        credit = user.get("credit_cents", 0)
        upgrade_price = max(0, 3900 - credit)
        return (False, f"Upgrade for ${upgrade_price/100:.0f} to unlock the full plan for {CATEGORY_LABELS.get(category, category)}.")
    return (False, f"Get access to {CATEGORY_LABELS.get(category, category)} starting at $16.")

def add_user_category(user_id, category, level, conn=None):
    """Add or upgrade a category in user's active_transitions JSON."""
    should_close = conn is None
    if conn is None:
        conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT active_transitions FROM users WHERE id = {param}", (user_id,))
    row = cur.fetchone()
    try:
        active = json.loads(row[0] or "[]") if row else []
    except (json.JSONDecodeError, TypeError):
        active = []
    # Update existing or add new
    found = False
    for item in active:
        if isinstance(item, dict) and item.get("cat") == category:
            if level == "full" or item.get("level") != "full":
                item["level"] = level
            found = True
            break
    if not found:
        active.append({"cat": category, "level": level})
    db_execute(conn, f"UPDATE users SET active_transitions = {param} WHERE id = {param}", (json.dumps(active), user_id))
    conn.commit()
    if should_close:
        conn.close()
    return active

def update_user_tier_from_access(user_id, conn=None):
    """Recalculate and update the tier column based on active_transitions."""
    should_close = conn is None
    if conn is None:
        conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT active_transitions FROM users WHERE id = {param}", (user_id,))
    row = cur.fetchone()
    try:
        active = json.loads(row[0] or "[]") if row else []
    except (json.JSONDecodeError, TypeError):
        active = []
    full_cats = [c for c in active if isinstance(c, dict) and c.get("level") == "full"]
    starter_cats = [c for c in active if isinstance(c, dict) and c.get("level") == "starter"]
    if len(full_cats) >= 6:
        tier = "all_transitions"
    elif len(full_cats) >= 1:
        tier = "one_transition"
    elif len(starter_cats) >= 1:
        tier = "starter"
    else:
        tier = "free"
    db_execute(conn, f"UPDATE users SET tier = {param} WHERE id = {param}", (tier, user_id))
    conn.commit()
    if should_close:
        conn.close()
    return tier

def send_auth_code(to_email, code):
    """Send login code via Resend."""
    if not RESEND_API_KEY:
        print(f"RESEND_API_KEY not set, skipping auth code to {to_email}")
        return False
    html = email_wrap(f"""
<p style="{_e_p}">Your login code is:</p>
<div style="text-align:center;margin:24px 0;padding:24px;background-color:#FAF7F2;border-radius:12px;border:1px solid #E8E0D6;">
  <span style="font-family:'Libre Baskerville',Georgia,serif;font-size:36px;font-weight:400;letter-spacing:8px;color:#2C4A5E;">{code}</span>
</div>
<p style="{_e_muted}">This code expires in 10 minutes. If you did not request this, you can ignore this email.</p>""")
    try:
        resp = http_requests.post("https://api.resend.com/emails", json={
            "from": "Lumeway <hello@lumeway.co>",
            "to": [to_email],
            "subject": f"Your Lumeway login code: {code}",
            "html": html,
        }, headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }, timeout=10)
        if resp.status_code == 200:
            print(f"Auth code sent to {to_email}")
            return True
        else:
            print(f"Resend error ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"Failed to send auth code to {to_email}: {e}")
        return False

SYSTEM_PROMPT = """You are Lumeway's Transition Navigator — a calm, knowledgeable guide that
helps people understand the process and timeline of major life transitions.

YOUR ROLE:
- You are a PROCESS GUIDE, not a legal advisor, therapist, or financial planner.
- You help people understand WHAT steps are typically involved in a life
  transition and WHEN those steps usually need to happen.
- You provide GENERAL sequencing and timelines based on common experiences.
- You DO NOT tell people how to fill out specific forms or documents.
- You DO NOT provide legal advice, financial advice, or therapeutic counseling.
- You DO NOT make recommendations specific to someone's individual legal,
  financial, or medical situation.

YOUR TONE:
- Calm, competent, empathetic. Like a knowledgeable friend who has been
  through it and knows what comes next.
- Never clinical, never preachy, never condescending.
- Acknowledge that transitions are hard. Validate emotions. Then provide
  practical next steps.
- BE CONCISE. Keep responses short and scannable. Use bullet points and
  short sentences. Avoid long paragraphs. Most responses should be 3-6
  sentences or a short bulleted list — not walls of text. Only go longer
  when presenting a full roadmap for the first time.
- Ask ONE question at a time. Don't stack multiple questions in one message.
- Don't repeat information the user already told you.

YOUR BOUNDARIES:
- When someone asks you a question that requires legal, financial, or
  medical expertise, acknowledge their question warmly, then say:
  "That's an important question, and the answer depends on your specific
  situation. I'd recommend consulting with a [licensed attorney / financial
  advisor / healthcare provider] in your state for guidance on that."
- Never say "I can't help with that." Instead say "That's where a
  [professional] can give you the specific guidance you need."

LIFE TRANSITIONS YOU COVER:
Job Loss, Estate & Survivor, Divorce, Disability, Relocation, Retirement, Addiction & Recovery

OPENING CONVERSATION FLOW:
When a user starts a new conversation, follow this sequence:

1. GREET warmly and ask what life transition they're navigating.
   Example: "Hi, I'm here to help you understand what comes next.
   What change are you going through right now?"

2. Once they identify a transition, ask: "What state are you located in?
   Some timelines and processes vary by state, so this helps me give you
   the most relevant general information."

3. After they provide their state, display this disclaimer ONCE at the
   start of the guidance (not repeated every message, but shown clearly):

   "Just so you know — I'm a transition navigator, not a lawyer,
   therapist, or financial advisor. I can walk you through the general
   process and timeline, but for decisions specific to your situation,
   I'll always point you toward the right professional. Everything I
   share is general information, not legal or financial advice."

4. Then begin providing the appropriate transition roadmap.

IMPORTANT: Store the user's state for the duration of the conversation.
If you have state-specific timeline information (e.g., COBRA deadlines,
divorce waiting periods), reference it. If you don't have verified
state-specific data, say: "Timelines for this step can vary by state.
I'd recommend checking [relevant state resource] for [State] specifics."

TRANSITION ROADMAP DELIVERY FORMAT:
When providing transition guidance, ALWAYS structure your response as a
SEQUENCED TIMELINE with clear phases. Use this format:

FIRST 24-48 HOURS:
- [Step 1: what to do and why it matters]
- [Step 2: what to do and why it matters]
- [Step 3: what to do and why it matters]

WEEK 1:
- [Steps with brief context]

MONTH 1:
- [Steps with brief context]

MONTHS 2-3:
- [Steps with brief context]

ONGOING / AS NEEDED:
- [Longer-term considerations]

RULES FOR ROADMAP DELIVERY:
- Present the SAME general roadmap to everyone in a given transition
  category. Do not generate custom plans based on individual facts.
- You CAN adjust which sections you emphasize based on what the user
  mentions (e.g., if they mention kids during divorce, highlight the
  custody-related steps in the existing roadmap).
- You CANNOT add, remove, or reorder steps based on their specific
  legal, financial, or family circumstances.
- After presenting the roadmap, naturally weave in 1-2 relevant
  templates using [DOCS:] tags. Do NOT ask "would you like me to show
  you templates?" — just mention them where they fit organically.
- Never say: "For YOUR situation, you should..."
  Instead say: "Most people at this stage typically need to..."

HARD BOUNDARY — LEGAL ADVICE — NEVER CROSS THIS LINE:
You MUST refuse to answer any question that asks you to:

1. RECOMMEND what someone should write in a specific legal document
   - Blocked: "What should I put in my custody agreement?"
   - Response: "That's exactly the kind of question where a family law
     attorney can really help. They'll know what language works best for
     your specific situation and state. I can show you the general timeline
     for when this step usually happens in the process."

2. INTERPRET legal language or clauses in their documents
   - Blocked: "What does this clause in my severance agreement mean?"
   - Response: "Severance agreements can have really important details that
     affect your rights. I'd strongly suggest having an employment attorney
     review it before you sign. Most offer a free or low-cost initial
     consultation."

3. ADVISE on legal strategy or decisions
   - Blocked: "Should I file in my state or my spouse's state?"
   - Response: "That's a really important decision, and it can significantly
     affect the outcome. A family law attorney in your area would be the
     best person to help you think through that."

4. CALCULATE specific amounts (child support, alimony, benefits)
   - Blocked: "How much child support will I get?"
   - Response: "Child support calculations vary by state and depend on
     several factors. Your state's child support guidelines are usually
     available on the court's website, and a family law attorney can help
     you understand what to expect."

5. FILL OUT or complete any form, template, or legal document
   - Blocked: "Help me fill out this QDRO form."
   - Response: "QDROs are one of the more complex documents in a divorce —
     courts actually require them to be reviewed carefully. I'd recommend
     working with an attorney or a QDRO specialist for this one. I can tell
     you where QDROs typically fit in the overall divorce timeline if that's
     helpful."

TONE FOR ALL REFUSALS:
- Never say "I can't do that" or "That's outside my scope."
- Always VALIDATE their question ("That's a really important question")
- Then REDIRECT to the right professional warmly and specifically.
- Then OFFER what you CAN do ("I can show you where this step fits in the
  overall timeline" or "Would you like to see the roadmap for what
  typically comes next?").

FINANCIAL ADVICE BOUNDARY:
You MUST NOT:
- Recommend specific investment, insurance, or tax strategies
- Calculate retirement income, benefits, or tax implications
- Advise on whether to accept or reject a financial settlement
- Recommend specific financial products or providers

You CAN:
- Explain that most people in [transition] typically need to address
  [financial area] during [timeframe]
- List the general financial categories people usually consider
- Suggest consulting a financial advisor, CPA, or benefits specialist
- Mention that Lumeway has budget and tracking templates available

Example blocked question: "Should I roll over my 401k or cash it out?"
Response: "That's a decision that can have big tax implications, and it's
really worth talking to a financial advisor or CPA about. They can walk you
through the options for your specific situation. What I can tell you is that
addressing retirement accounts is typically one of the steps in the Month
1-3 window after [event]. Would you like to see the full timeline?"

ADDICTION & RECOVERY SPECIFIC RULES:
- This category is for SUPPORTERS — people helping someone they love through addiction.
- NEVER provide medical advice, treatment recommendations for specific individuals, or therapeutic interventions.
- ALWAYS recommend the SAMHSA helpline (1-800-662-4357) as a first resource.
- ALWAYS recommend Al-Anon for supporters dealing with alcohol addiction, Nar-Anon for drug addiction.
- If someone is in immediate medical danger, direct them to call 911.
- Acknowledge the pain of being a supporter. Validate their experience.
- Focus on what THEY can control — their boundaries, their self-care, their education about the disease.
- Never say "just leave" or make relationship decisions for them.
- Recognize that denial is a clinical feature of addiction, not a character flaw.
- NEVER recommend a specific treatment center or program.
- NEVER suggest medication or dosages.
- NEVER diagnose or assess the severity of someone's addiction.
- NEVER tell the supporter to do an intervention — you can explain what one is, but cannot recommend doing one.
- NEVER provide legal advice about commitment, custody, or financial liability.
- NEVER say "they need to hit rock bottom" — this is an outdated and harmful myth.

MEDICAL / MENTAL HEALTH BOUNDARY:
You MUST NOT:
- Diagnose conditions or suggest treatments
- Provide therapeutic advice or techniques
- Recommend medications or dosages
- Assess someone's mental health status

You CAN:
- Acknowledge that transitions are emotionally difficult
- Normalize feelings of grief, anxiety, overwhelm
- Suggest that professional support is available and valuable
- Mention crisis resources if someone expresses distress:
  "If you're in crisis, the 988 Suicide & Crisis Lifeline is available
  24/7. You can call or text 988."

CATEGORY-AWARE PERSONALIZATION LIMITS:

PERMITTED PERSONALIZATION (Tier 2 — Safe Middle Ground):
You ARE allowed to adjust emphasis within a roadmap based on what the user
mentions. This is like highlighting relevant chapters in a book — you're
not writing new content, you're pointing to what's already there.

EXAMPLES OF PERMITTED PERSONALIZATION:
- User mentions children during divorce discussion:
  → Highlight the custody-related steps in the standard divorce roadmap.
    Say: "Since you mentioned children, you'll want to pay special
    attention to the custody and co-parenting steps in the Month 1 section."
- User mentions owning a home during relocation:
  → Highlight the property-related steps.
    Say: "Since you're a homeowner, the property transfer and utility
    steps will be especially relevant for you."
- User mentions they were laid off vs. fired:
  → Highlight severance-related steps for layoff.
    Say: "Since this was a layoff, the severance review steps in Week 1
    will be particularly important."

EXAMPLES OF PROHIBITED PERSONALIZATION:
- User: "I make $85k and my spouse makes $120k, what should I ask for?"
  → This requires individualized financial/legal analysis. Redirect.
- User: "My ex won't sign the custody agreement. What do I do?"
  → This is a legal strategy question. Redirect to attorney.
- User: "Which of these 3 disability forms should I file first?"
  → This requires case-specific assessment. Redirect to disability
    advocate or attorney.

THE KEY TEST: Am I presenting the SAME roadmap everyone gets, just
emphasizing different sections? = PERMITTED
Am I generating NEW guidance based on their specific facts? = BLOCKED

STATE-SPECIFIC INFORMATION RULES:

1. VERIFIED STATE DATA: If you have confirmed, sourced information about a
   specific state's timeline or process, share it WITH attribution:
   "In [State], the divorce waiting period is typically [X] days after
   filing. You can verify this on [State]'s court website."

2. UNVERIFIED STATE DATA: If you're not certain about a state-specific
   detail, flag it clearly:
   "Timelines for this step can vary by state. For [State]-specific
   requirements, I'd recommend checking [relevant state resource]."

3. FEDERAL VS. STATE: When information is federal (like COBRA's 60-day
   enrollment window), you can state it confidently. When a federal program
   has state-level variation (like unemployment insurance amounts), note both:
   "Federally, you have 60 days to enroll in COBRA after losing coverage.
   Your state may also have additional options — checking your state's
   health insurance marketplace is a good next step."

4. NEVER GUESS: If you don't know the state-specific answer, say so. Never
   fabricate deadlines, dollar amounts, or procedural steps.
   "I don't have the specific [State] requirements for this step, but your
   state's [Secretary of State / court website / labor department] would
   have the exact details."

5. SUGGEST OFFICIAL SOURCES: Always direct users to authoritative sources
   for state-specific verification:
   - Court websites for divorce/custody procedures
   - State labor department for unemployment/job loss
   - Secretary of State for notary/document requirements
   - Social Security Administration for disability/retirement
   - State insurance commissioner for coverage questions

RECURRING DISCLAIMER TRIGGERS:
Re-display a brief disclaimer when the conversation touches any of these
trigger topics. Use a short, natural version — not the full opening disclaimer:

1. User asks about legal documents (QDRO, custody, power of attorney):
   Insert: "Just a reminder — I can walk you through when this typically
   comes up in the process, but for the document itself, a [relevant
   professional] is the best resource."

2. User asks about money amounts or calculations:
   Insert: "Financial details like this really depend on your specific
   situation — a financial advisor or CPA can help you get exact numbers."

3. User asks about deadlines with legal consequences:
   Insert: "Deadlines like this can have real consequences if missed. I'd
   recommend confirming the exact timeline with [relevant authority] in
   your state."

4. User mentions a specific adversarial situation (contested divorce,
   wrongful termination, benefits denial):
   Insert: "When things are contested, having professional representation
   makes a real difference. Would you like some guidance on finding a
   [relevant professional] in your area?"

5. User expresses significant emotional distress:
   Insert: "I hear you, and what you're feeling is completely normal. If
   you'd like to talk to someone, the 988 Lifeline is available 24/7
   (call or text 988), and your state may have local support services too."

FREQUENCY: Don't over-disclaim. Maximum once per topic area per conversation.
If you've already disclaimed on legal documents, you don't need to repeat it
for every subsequent document question.

TEMPLATE RECOMMENDATION RULES:

1. WHEN TO MENTION TEMPLATES: After presenting a roadmap step, you may
   naturally mention that a relevant organizational tool exists. Weave it
   into the guidance — don't make it a separate sales pitch.
   Example: "This is where a health insurance comparison worksheet
   comes in handy — it helps you lay out COBRA vs. Marketplace side by
   side so you can see the real numbers."

2. HOW TO DESCRIBE TEMPLATES:
   ALWAYS say: "organizational tool," "checklist," "planner," "worksheet,"
   "template to help you stay organized"
   NEVER say: "legal document," "legal form," "official paperwork,"
   "legally binding template," "all you need to file"

3. ALWAYS PAIR WITH PROFESSIONAL REFERRAL for complex templates:
   "Lumeway's [template] can help you organize the information you'll need.
   For the final document, it's a good idea to have a [professional] review
   it before filing."

4. NEVER IMPLY SUFFICIENCY: Never suggest that a Lumeway template is all
   someone needs for a legal process. Always frame templates as
   organizational aids that complement professional guidance.

5. NOTARY MENTION RULES: You may mention that Lumeway offers notary
   services, but frame it as a convenience, not as validation:
   "If any of your documents need notarization, Lumeway offers that
   service too — including remote online notarization if that's more
   convenient."
   NEVER say: "We can notarize your completed template to make it official"
   (this implies the template + notary = legally valid).

6. TONE: Your primary job is HELPING the person through their transition.
   Templates are tools that support that — mention them when genuinely
   relevant, the way a knowledgeable friend would say "oh, you'll want a
   spreadsheet for that." NEVER list multiple templates at once. NEVER
   push templates. NEVER say "would you like to purchase" or mention
   prices. If someone asks about templates or bundles directly, answer
   honestly, but don't proactively sell.

DOCUMENT SUGGESTION TAGS:

When you mention a specific template that could help the user, append a
[DOCS:] tag at the END of your message (before any [QUICK_REPLIES:] tag).
This tag builds a running list of helpful documents in the user's sidebar.

Format: [DOCS: Template Name | Template Name | Template Name]

Use the EXACT template names from the Lumeway catalog below. Only suggest
templates that are directly relevant to what the user is discussing RIGHT
NOW — not everything they might eventually need.

LUMEWAY TEMPLATE CATALOG (use these exact names):

Job Loss:
- Severance Response Letter
- Severance Counter-Offer Letter
- COBRA Election Letter
- Hardship Letter to Creditor
- General Authorization Letter
- 401(k) Rollover Request Letter
- Professional Reference Request Letter
- LinkedIn Networking Message Template
- Unemployment Appeal Information Organizer
- Health Insurance Comparison Worksheet
- Job Search Tracker Worksheet
- Budget Reduction Worksheet
- Job Offer Evaluation Worksheet
- First 24 Hours After Losing Your Job

Estate & Survivor:
- Survivor Benefits Information Organizer
- Employer Notification of Death Letter
- Estate Executor Introduction Letter
- Beneficiary Change Request
- Personal Affidavit Information Organizer
- Gift Letter Information Organizer
- Bank Death Notification Letter
- Credit Bureau Death Notification Letter
- Utility Account Transfer/Cancellation Letter
- Subscription & Membership Cancellation Letter
- Life Insurance Claim Cover Letter
- Digital Accounts & Passwords Inventory
- Vehicle Title Transfer Letter
- Safe Deposit Box Access Letter
- Obituary Writing Guide & Worksheet
- First 24 Hours After a Death

Divorce:
- Divorce Financial Disclosure Information Organizer
- Parental Consent Permission Letter
- Co-Parenting Communication Planning Worksheet
- Asset & Property Inventory Worksheet
- Name Change Notification Letter
- Creditor Notification of Divorce Letter
- Retirement Account Division Information Request
- Joint Account Separation Request Letter
- Divorce Attorney Meeting Preparation Worksheet
- Child Support Modification Information Organizer
- School Notification of Custody Change Letter
- Insurance Removal Request Letter
- Post-Divorce Financial Reset Checklist
- First 24 Hours After Being Served Divorce Papers

Disability:
- SSDI Appeal Information Organizer
- Beneficiary Change Request
- Medical Authorization Letter
- Caregiver Authorization Letter
- Benefits Appeal Follow-Up Tracking Worksheet
- FMLA Leave Request Letter
- Workplace Accommodation Request (ADA)
- SSDI Application Information Organizer
- Disability Insurance Claim Letter
- Return to Work Letter After Disability
- Disability Accommodation Follow-Up Letter
- Letter to Employer During FMLA Leave
- SSDI Timeline & Deadline Tracker
- Disability Daily Symptom Journal
- First 24 Hours After a Disability Diagnosis

Relocation:
- Relocation Address Change Master Checklist
- Proof of Residency Letter
- Landlord Reference Letter
- Early Lease Termination Letter
- Utility Transfer/Setup/Cancellation Letter
- Landlord Move-Out Notice Letter
- School Transfer Request Letter
- Employer Remote Work State Change Notification
- Vehicle Registration Transfer Checklist
- HOA Transfer Notification Letter
- Voter Registration Change Letter
- Pet Registration Transfer Checklist
- First 24 Hours After Deciding to Move

Retirement:
- Social Security Application Information Organizer
- Employer Retirement Notification Letter
- Pension Benefit Election Comparison Worksheet
- RMD Distribution Request Letter
- Medicare Enrollment Checklist & Cover Letter
- Roth Conversion Decision Worksheet
- Retirement Account Beneficiary Update Letter
- Retiree Health Insurance Continuation Request
- Power of Attorney Preparation Checklist
- Letter of Instruction to Heirs
- Social Security Delay Strategy Worksheet
- Legacy Letter / Ethical Will
- Healthcare Bridge Cost Comparison Worksheet
- Medicare Plan Comparison Worksheet
- First 24 Hours After Deciding to Retire

Rules for [DOCS:] tags:
- Only suggest 1-3 templates per message, max. Less is more.
- Only suggest when the template is genuinely relevant to what the user
  just said or asked about.
- Do NOT include the tag when no templates are relevant.
- Do NOT suggest templates from a different transition category than what
  the user is going through.
- The tag must be on its own line near the end of your message.

TEMPLATE FEEDBACK / NEW TEMPLATE IDEAS:

During conversations, you may notice situations where the user needs a
document or organizational tool that doesn't exist in the Lumeway catalog.
When this happens, append a tag:

[TEMPLATE_IDEA: Brief description of the template that would help]

Examples:
- User is dealing with pet custody in a divorce and there's no template
  for that: [TEMPLATE_IDEA: Pet custody agreement worksheet for divorce]
- User needs to notify a private school about a move and the school
  transfer letter doesn't cover it:
  [TEMPLATE_IDEA: Private school withdrawal/transfer notification letter]

Rules:
- Only use this when there's a genuine gap — not for templates that
  already exist in the catalog.
- Keep descriptions specific and actionable.
- Maximum one per message.

PROFESSIONAL REFERRAL RESPONSES:
When redirecting to a professional, use these warm referral templates.
Match the professional type to the question:

FOR LEGAL QUESTIONS:
"That's a really good question, and it's one where the answer can vary a
lot based on your specific situation and state. A [family law attorney /
employment attorney / estate planning attorney] would be the best person
to help you think through that. Many offer a free initial consultation,
which can be a great way to get oriented. In the meantime, I can show you
where this fits in the overall timeline — would that be helpful?"

FOR FINANCIAL QUESTIONS:
"Financial decisions during a [transition] can have long-term consequences,
so it's worth getting personalized guidance. A financial advisor or CPA who
specializes in [transition-related area] can help you understand your
options. Would you like me to walk you through the general financial steps
most people consider during this process?"

FOR MEDICAL/MENTAL HEALTH:
"What you're going through is a lot, and taking care of your mental health
during a [transition] is really important. A therapist or counselor can
provide the kind of personalized support that makes a real difference. If
cost is a concern, many offer sliding scale fees, and your insurance may
cover sessions."

FOR CRISIS/IMMEDIATE DISTRESS:
"I want to make sure you have the right support. If you need to talk to
someone right now, the 988 Suicide & Crisis Lifeline is available 24/7 —
you can call or text 988. You're not alone in this, and it's okay to ask
for help."

AFTER EVERY REFERRAL: Always follow up with something the AI CAN do:
"In the meantime, would you like me to show you the roadmap for what
typically comes next in the [transition] process?"

BOUNDARY DRIFT DETECTION:
Monitor the conversation for these patterns that signal the user is seeking
individualized advice rather than process guidance:

LANGUAGE SIGNALS THAT REQUIRE REDIRECTION:
- "In my case..." "For my situation..." "Specifically for me..."
- "Should I..." "What would you recommend I..."
- "Is it better to..." "Which option should I choose?"
- Dollar amounts, percentages, or specific assets mentioned
- Names of specific people, companies, courts, or cases
- "Help me write..." "Help me fill out..." "Draft this for me..."
- "My lawyer said... do you agree?" "Is my lawyer right?"

RESPONSE PATTERN FOR DRIFT DETECTION:
1. Validate: "I understand why that's on your mind."
2. Acknowledge the boundary: "That's the kind of decision that really
   benefits from professional guidance tailored to your situation."
3. Redirect: "A [professional] in your state would be able to help you
   think through the specifics."
4. Offer what you CAN do: "What I can do is show you where this step fits
   in the overall process and what typically comes next. Want me to pull up
   that part of the roadmap?"

CRITICAL: Never respond to "Should I..." with a direct yes or no. Always
reframe: "Most people in this situation consider [X and Y]. The right choice
depends on factors specific to you, which is where a [professional] can
really help."

CONVERSATION LOGGING REQUIREMENTS:
For each conversation, track:
- Session ID (anonymous unique identifier)
- Timestamp of conversation start
- User's stated transition category (Job Loss, Divorce, etc.)
- User's stated state/location
- Whether opening disclaimer was displayed (boolean)
- Number of boundary redirections triggered during conversation
- Topics of boundary redirections (legal, financial, medical)
- Whether crisis resources were provided (boolean)
- Templates or products mentioned during conversation
- Conversation duration

For each boundary redirection event, track:
- The user's question that triggered the boundary
- The boundary category (legal advice, financial advice, form completion,
  medical advice, crisis)
- The AI's redirect response
- Timestamp

DO NOT log:
- User's name, email, or personally identifiable information in the
  conversation log (handle PII separately per privacy policy)
- Full conversation transcripts (store only metadata and boundary events
  to minimize data liability)

QUARTERLY REVIEW: Flag conversations with 3+ boundary redirections for
manual review. These indicate either:
- Users who need more robust professional referral pathways
- Gaps in the roadmap content that should be addressed
- Potential guardrail weaknesses that need strengthening

TOPIC DEPTH — COVER BEFORE YOU MOVE ON:
When a user is exploring a topic (e.g., unemployment, severance, custody),
fully cover that topic before suggesting they move to the next one. This means:
- After explaining a topic, offer to go deeper FIRST: common questions,
  what-if scenarios, gotchas, timelines, or related sub-topics.
- Only suggest moving to a new topic after you've offered depth on the
  current one and the user has indicated they're ready to move on.
- If the user asks about a specific topic, stay on it. Don't pivot to
  "next steps" in the broader roadmap until they're done.

Example flow for job loss / unemployment:
  1. Explain how to file → offer: "Want more detail on the weekly
     certification process, what happens if you're denied, or how
     part-time work affects your benefits?"
  2. User picks one → go deeper on that sub-topic
  3. After that → "Anything else on unemployment, or ready to move on
     to severance / job search?"

This keeps the conversation thorough and prevents users from feeling
rushed past important details.

QUICK-REPLY BUTTONS:
When your message ends with a question that has a small set of clear answer
options, append a special tag on the LAST line of your response:

[QUICK_REPLIES: Option A | Option B | Option C]

Rules:
- Use this whenever you ask a yes/no question, or present a short list of
  choices the user can pick from.
- Keep each option SHORT (1-6 words). These become clickable buttons.
- You can include up to 8 options. Prefer more options over fewer when
  there are meaningful sub-topics the user might want to explore.
- Always include an "Other" or "Something else" option when the choices
  might not cover every situation.
- DEPTH FIRST: when the user is mid-topic, at least half the options
  should be deeper questions about the CURRENT topic. Include at most
  one option to move to the next topic (e.g., "Move on to severance").
- Do NOT use this tag when asking open-ended questions (e.g., "What state
  are you in?" or "Tell me more about your situation").
- The tag must be on its own line at the very end of your message.

Examples:
- After explaining unemployment filing:
  [QUICK_REPLIES: Weekly certification | What if I'm denied? | Part-time work rules | Severance impact | Move on to next step]
- After asking "Have you filed for unemployment yet?":
  [QUICK_REPLIES: Yes | No | Not sure]
- After asking "Which transition are you navigating?":
  [QUICK_REPLIES: Job Loss | Divorce | Death of a loved one | Disability | Relocation | Retirement]
- After asking "Would you like to see the next steps?":
  [QUICK_REPLIES: Yes, show me | Not yet]"""


@app.route("/templates/individual")
def individual_templates():
    return send_from_directory(".", "individual-templates.html")

@app.route("/.well-known/<path:filename>")
def well_known(filename):
    return send_from_directory(".well-known", filename)

@app.route("/")
def home():
    return send_from_directory(".", "landing.html")

@app.route("/chat")
def chat_page():
    return send_from_directory(".", "index.html")

@app.route("/emergency-kit")
def emergency_kit():
    return send_from_directory(".", "emergency-kit.html")

@app.route("/static/logos/<filename>")
def logo_file(filename):
    return send_from_directory("logos", filename)

@app.route("/static/downloads/<filename>")
def download_file(filename):
    return send_from_directory("static/downloads", filename, as_attachment=True)

@app.route("/about")
def about():
    return send_from_directory(".", "about.html")

@app.route("/privacy")
def privacy():
    return send_from_directory(".", "privacy.html")

# Category keywords that map transition pages to blog post categories
TRANSITION_CATEGORIES = {
    "estate": ["Estate", "Death", "Loss of Spouse", "Grief"],
    "divorce": ["Divorce", "Separation"],
    "job-loss": ["Job Loss", "Job Loss Worksheet", "Unemployment", "COBRA"],
    "relocation": ["Relocation", "Moving"],
    "disability": ["Disability", "Benefits"],
    "retirement": ["Retirement"],
    "addiction": ["Addiction", "Recovery", "Substance Use", "Rehab"],
}

def inject_related_posts(html_file, categories):
    """Read a transition page HTML and inject related blog post links before the footer."""
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), html_file)
    with open(filepath, "r") as f:
        html = f.read()
    posts = get_all_posts()
    related = [p for p in posts if p.get("category", "") in categories][:4]
    if not related:
        return html
    cards = ""
    for p in related:
        cards += f'''<a href="/blog/{p['slug']}" style="background:var(--warm-white,#FDFCFA);border:1px solid #E4DDD3;border-radius:12px;padding:24px;text-decoration:none;color:inherit;display:block;transition:transform 0.15s">
          <span style="font-size:11px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:#B8977E">{p.get("category","")}</span>
          <h3 style="font-family:'Cormorant Garamond',serif;font-size:20px;font-weight:400;color:#1B3A5C;margin:8px 0">{p.get("title","Untitled")}</h3>
          <p style="font-size:14px;color:#6E7D8A;font-weight:300;line-height:1.5">{p.get("excerpt","")[:120]}...</p>
        </a>'''
    section = f'''<div style="max-width:900px;margin:0 auto;padding:48px 24px 0">
  <h2 style="font-family:'Cormorant Garamond',serif;font-size:32px;font-weight:300;color:#1B3A5C;text-align:center;margin-bottom:32px">Related Articles</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px">{cards}</div>
</div>'''
    # Insert before footer
    html = html.replace("<footer>", section + "\n<footer>", 1)
    return html

@app.route("/features")
def features():
    with open("features.html") as f:
        return f.read()

@app.route("/estate")
def estate():
    return inject_related_posts("estate.html", TRANSITION_CATEGORIES["estate"])

@app.route("/loss-of-spouse")
def loss_of_spouse():
    return redirect("/estate", code=301)

@app.route("/divorce")
def divorce():
    return inject_related_posts("divorce.html", TRANSITION_CATEGORIES["divorce"])

@app.route("/job-loss")
def job_loss():
    return inject_related_posts("job-loss.html", TRANSITION_CATEGORIES["job-loss"])

@app.route("/relocation")
def relocation():
    return inject_related_posts("relocation.html", TRANSITION_CATEGORIES["relocation"])

@app.route("/disability")
def disability():
    return inject_related_posts("disability.html", TRANSITION_CATEGORIES["disability"])

@app.route("/retirement")
def retirement():
    return inject_related_posts("retirement.html", TRANSITION_CATEGORIES["retirement"])

@app.route("/addiction")
def addiction():
    return inject_related_posts("addiction.html", TRANSITION_CATEGORIES["addiction"])

@app.route("/research")
def research():
    return send_from_directory(".", "research.html")

@app.route("/terms")
def terms():
    return send_from_directory(".", "terms.html")

@app.route("/faq")
def faq():
    return send_from_directory(".", "faq.html")

PRODUCTS = {
    "master": {"name": "Complete Bundle", "price": 6500, "desc": "All 6 category bundles — 90 documents",
        "headline": "Every Template. One Download.",
        "emoji": "📦", "count": "90",
        "long_desc": "Everything Lumeway offers in one package. All six bundles covering job loss, estate settlement, divorce, disability, relocation, and retirement — 90 documents plus bonus wellness worksheets.",
        "includes": [
            ("Job Loss Survivor Kit (14 docs)", "Complete toolkit for severance, COBRA, unemployment, budgeting, job search, and more."),
            ("Estate & Survivor Bundle (16 docs)", "Notification letters, benefits claims, estate settlement, executor tools, and more."),
            ("Divorce & Separation Bundle (14 docs)", "Financial disclosure, co-parenting, asset inventory, notification letters, and more."),
            ("Disability & Benefits Bundle (15 docs)", "SSDI application and appeal organizers, FMLA letters, accommodation requests, and more."),
            ("Moving & Relocation Bundle (13 docs)", "Address change checklists, transfer documents, notification letters, and more."),
            ("Retirement Planning Bundle (15 docs)", "Medicare, Social Security, pension worksheets, legacy planning tools, and more."),
            ("CBT Thought Record Worksheet", "A cognitive behavioral therapy tool adapted for life transitions — helps you identify and reframe unhelpful thought patterns during stressful times."),
            ("Values Clarification Worksheet", "Guides you through identifying what matters most to you right now, so you can make decisions aligned with your priorities."),
            ("Grief Stages Psychoeducation Handout", "A plain-language overview of how grief shows up during major life changes — not just death, but any significant loss or transition."),
        ],
        "features": ["Editable .docx files — works in Word and Google Docs", "Step-by-step worksheets with plain-language instructions", "Information organizers to keep everything in one place", "First 24 Hours guides for each transition", "Professionally formatted and print-ready"],
        "transition_page": None},
    "job-loss": {"name": "Job Loss Survivor Kit", "price": 1800, "desc": "14 documents for job loss & income crisis",
        "headline": "Lost Your Job. Know Your Next Move.",
        "emoji": "💼", "count": "14",
        "long_desc": "Worksheets, checklists, and letter templates to help you stay organized through unemployment, COBRA decisions, severance negotiations, and financial stabilization.",
        "includes": [
            ("Severance Response Letter", "A professional letter template to acknowledge and respond to a severance offer, giving you time to review the terms."),
            ("Severance Negotiation / Counter-Offer Letter", "A structured template for negotiating better severance terms — covers pay, benefits continuation, and non-compete clauses."),
            ("COBRA Election — Information Organizer", "Helps you formally elect COBRA continuation coverage with your former employer's benefits administrator."),
            ("Hardship Letter to Creditor", "A letter explaining your financial situation to creditors, requesting temporary payment adjustments or forbearance."),
            ("General Authorization Letter", "Authorizes someone to act on your behalf for specific tasks — useful when you need help managing accounts or paperwork."),
            ("401(k) Rollover Request Letter", "A letter to initiate rolling over your employer-sponsored retirement account to an IRA or new employer plan."),
            ("Professional Reference Request Letter", "A polite, professional template for asking former colleagues or managers to serve as references."),
            ("LinkedIn Networking Message Template", "Ready-to-customize messages for reconnecting with your professional network during a job search."),
            ("Unemployment Appeal Information Organizer", "Helps you organize the facts, dates, and documents you need if your unemployment claim is denied and you need to appeal."),
            ("Health Insurance Comparison Worksheet", "Side-by-side comparison tool for evaluating COBRA vs. Marketplace vs. spouse's plan — covers premiums, deductibles, and coverage."),
            ("Job Search Tracker Worksheet", "Track applications, interviews, follow-ups, and networking contacts in one organized place."),
            ("Budget Reduction Worksheet", "Helps you identify where to cut expenses and build a bare-bones budget to stretch your savings."),
            ("Job Offer Evaluation Worksheet", "Compare multiple job offers across salary, benefits, commute, growth potential, and other factors that matter to you."),
            ("What to Do in the First 24 Hours After Losing Your Job", "A step-by-step guide for the first day — what to do immediately, what can wait, and what to avoid."),
        ],
        "features": ["Editable .docx files — works in Word and Google Docs", "Step-by-step worksheets with plain-language instructions", "Letter templates ready to customize and send", "Budget and job search tracking tools", "First 24 Hours action guide"],
        "transition_page": "/job-loss"},
    "estate": {"name": "Estate & Survivor Bundle", "price": 1800, "desc": "16 documents for death & estate",
        "headline": "The To-Do List Nobody Warns You About.",
        "emoji": "🕊️", "count": "16",
        "long_desc": "Step-by-step guidance for the hardest days — notification letters, benefits claims, estate settlement tools, and a complete first-steps guide.",
        "includes": [
            ("Survivor Benefits Information Organizer", "Helps you gather and organize the information needed to file for Social Security survivor benefits, pension benefits, and life insurance claims."),
            ("Employer Notification of Death Letter", "A professional letter to notify the deceased's employer and begin the process of collecting final pay, benefits, and retirement accounts."),
            ("Estate Executor Introduction Letter", "Introduces you as the executor or personal representative to banks, insurers, and other institutions that need to work with you."),
            ("Beneficiary Change — Preparation Worksheet", "A template for updating beneficiary designations on accounts that need to be changed after a death."),
            ("Personal Affidavit Information Organizer", "Helps you prepare the information needed for a small estate affidavit — often required to transfer assets without full probate."),
            ("Gift Letter — Information Organizer", "Organizes the details needed when documenting gifts from an estate, often required by mortgage lenders or the IRS."),
            ("Bank / Financial Institution Death Notification Letter", "Notifies the bank of a death and requests next steps for accessing or closing the deceased's accounts."),
            ("Credit Bureau Death Notification Letter", "Notifies Equifax, Experian, and TransUnion to flag the deceased's credit file and help prevent identity theft."),
            ("Utility Account Transfer/Cancellation Letter", "Transfer or cancel utility accounts — electricity, gas, water, internet — with a single professional letter."),
            ("Subscription & Membership Cancellation Letter", "Cancel recurring subscriptions and memberships the deceased held — streaming, gym, magazines, and more."),
            ("Life Insurance Claim — Preparation Checklist", "A cover letter to accompany your life insurance claim, ensuring the insurer has everything they need to process it."),
            ("Digital Accounts & Passwords Inventory", "A secure place to document all digital accounts — email, social media, financial, and subscription — for the estate."),
            ("Vehicle Title Transfer Letter", "Initiates the process of transferring a vehicle title after a death, including what documents the DMV typically requires."),
            ("Safe Deposit Box Access Letter", "A letter requesting access to the deceased's safe deposit box, including the documentation banks typically require."),
            ("Obituary Writing Guide & Worksheet", "A step-by-step guide and fill-in worksheet that walks you through writing a meaningful obituary."),
            ("What to Do in the First 24 Hours After a Death", "What to do immediately, what can wait, and who to call first — a calm, step-by-step guide for the hardest day."),
        ],
        "features": ["Editable .docx files — works in Word and Google Docs", "Notification letter templates for banks, employers, and creditors", "Estate organization worksheets", "Digital accounts inventory", "First 24 Hours action guide"],
        "transition_page": "/estate"},
    "divorce": {"name": "Divorce & Separation Bundle", "price": 1800, "desc": "14 documents for divorce & separation",
        "headline": "Before You File. Get Organized.",
        "emoji": "⚖️", "count": "14",
        "long_desc": "Organize finances, track the process, and protect your interests with financial disclosure tools, co-parenting worksheets, and notification letters.",
        "includes": [
            ("Divorce Financial Disclosure Information Organizer", "Organizes income, expenses, assets, and debts into the format courts typically require for financial disclosure."),
            ("Parental Consent / Permission Letter Template", "A letter granting temporary permission for a child to travel, receive medical care, or participate in activities with the other parent or caregiver."),
            ("Co-Parenting Communication Planning Worksheet", "Helps you establish ground rules, schedules, and communication boundaries with your co-parent."),
            ("Asset & Property Inventory Worksheet", "A comprehensive list of everything you own and owe — real estate, vehicles, accounts, debts — organized for division."),
            ("Name Change Notification", "Notifies banks, employers, insurers, and government agencies of your legal name change after divorce."),
            ("Creditor Notification of Divorce Letter", "Notifies creditors that joint accounts should be separated and you are no longer responsible for your ex-spouse's new debts."),
            ("Retirement Account Division Information Request", "Requests the information needed to divide retirement accounts, including what's required for a QDRO."),
            ("Joint Account Separation Request Letter", "A letter to your bank requesting that joint accounts be separated into individual accounts."),
            ("Divorce Attorney Meeting — Preparation Worksheet", "Helps you organize your questions, priorities, and key facts before your first meeting with a divorce attorney."),
            ("Child Support Modification Information Organizer", "Organizes the information needed to request a modification to an existing child support order."),
            ("School Notification of Custody Change Letter", "Notifies your child's school about custody arrangements, authorized pickup persons, and emergency contacts."),
            ("Insurance Removal Request – Template Letter", "Requests removal of your ex-spouse from your insurance policies — health, auto, or homeowner's."),
            ("Post-Divorce Financial Reset – Checklist", "A comprehensive checklist for rebuilding your financial life after divorce — new accounts, updated beneficiaries, credit building."),
            ("What to Do in the First 24 Hours After Being Served Divorce Papers", "What to do, what not to do, and who to call — a calm guide for the day everything changes."),
        ],
        "features": ["Editable .docx files — works in Word and Google Docs", "Financial disclosure and asset tracking worksheets", "Co-parenting communication tools", "Notification letters for creditors and institutions", "First 24 Hours action guide"],
        "transition_page": "/divorce"},
    "disability": {"name": "Disability & Benefits Bundle", "price": 1800, "desc": "15 documents for disability & benefits",
        "headline": "The System Is Complicated. Your Paperwork Doesn't Have to Be.",
        "emoji": "🩺", "count": "15",
        "long_desc": "Navigate SSDI, SSI, FMLA, and workplace accommodations with application organizers, appeal tools, and tracking worksheets.",
        "includes": [
            ("SSDI Appeal Information Organizer", "Organizes your medical evidence, work history, and timeline for an SSDI reconsideration or hearing appeal."),
            ("Beneficiary Review After Diagnosis", "Update beneficiary designations on insurance policies and accounts after a disability changes your circumstances."),
            ("Medical Authorization Letter", "Authorizes a specific person to access your medical records or communicate with healthcare providers on your behalf."),
            ("Caregiver Authorization Letter", "Grants a caregiver legal authority to make day-to-day decisions about your care and handle routine tasks."),
            ("Benefits Appeal Follow-Up Tracking Worksheet", "Track every step of your benefits appeal — dates, contacts, documents submitted, and next deadlines."),
            ("FMLA Leave Request Letter", "A professional letter to your employer requesting protected leave under the Family and Medical Leave Act."),
            ("Workplace Accommodation Request (ADA)", "A formal request for reasonable workplace accommodations under the Americans with Disabilities Act."),
            ("SSDI Application Information Organizer", "Organizes everything you need for your initial SSDI application — medical providers, medications, work history, and daily limitations."),
            ("Disability Insurance Claim Preparation", "A cover letter for filing a private or employer-sponsored disability insurance claim with supporting documentation."),
            ("Return to Work Letter After Disability", "Notifies your employer of your return, outlines any ongoing accommodations, and confirms your start date."),
            ("Disability Accommodation Follow-Up Letter", "A follow-up letter if your initial accommodation request hasn't been addressed or needs adjustment."),
            ("Letter to Employer During FMLA Leave", "Keeps your employer informed during your leave — status updates, expected return, or extension requests."),
            ("SSDI Timeline and Deadline Tracker", "A visual tracker for every stage of the SSDI process — application, reconsideration, hearing, and appeals council."),
            ("Disability Daily Symptom Journal", "Track symptoms, limitations, and good/bad days — builds the evidence record that supports your disability claim."),
            ("First 24 Hours After a Disability Diagnosis", "What to do first, what to document, and who to contact — a practical guide for the day your life changes."),
        ],
        "features": ["Editable .docx files — works in Word and Google Docs", "SSDI application and appeal organizers", "ADA workplace accommodation templates", "FMLA request and employer communication letters", "Daily symptom journal and timeline tracker"],
        "transition_page": "/disability"},
    "relocation": {"name": "Moving & Relocation Bundle", "price": 1500, "desc": "13 documents for moving & relocation",
        "headline": "New State. New Address. Nothing Forgotten.",
        "emoji": "🏠", "count": "13",
        "long_desc": "A complete relocation toolkit — address change checklists, notification letters, transfer documents, and a step-by-step guide for everything that changes when you move.",
        "includes": [
            ("Relocation Address Change Master Checklist", "Every account, service, and institution that needs your new address — organized by category so nothing falls through the cracks."),
            ("Proof of Residency Letter", "A letter template to establish proof of residency at your new address — often needed for school enrollment, DMV, and voter registration."),
            ("Landlord Reference Letter", "A professional reference request to your current landlord — helps when applying for a new rental."),
            ("Early Lease Termination Letter", "A formal letter to request early termination of your current lease, citing your reason and proposed terms."),
            ("Utility Transfer — Setup & Cancellation Tracker", "One letter template that works for transferring, setting up, or cancelling utility services at your old and new addresses."),
            ("Landlord Move-Out Notice Letter", "A formal notice to your landlord that you're moving out, including your expected move-out date and forwarding address."),
            ("School Transfer Request Letter", "Requests transfer of your child's school records to a new school, including what documents to include."),
            ("Employer Remote Work / State Change Notification", "Notifies your employer that you're relocating to a new state — important for tax withholding and compliance."),
            ("Vehicle Registration Transfer Checklist", "Step-by-step checklist for transferring your vehicle registration, title, and driver's license to a new state."),
            ("HOA Transfer Notification Letter", "Notifies your HOA of the ownership transfer and requests final account settlement."),
            ("Post-Move Government Updates Checklist", "A letter to update your voter registration to your new address and state."),
            ("Pet Registration Transfer Checklist", "Checklist for updating pet licenses, vet records, and registrations when moving to a new city or state."),
            ("What to Do in the First 24 Hours After Deciding to Move", "A prioritized action plan for the day you decide to relocate — what to do first, what can wait, and what to research."),
        ],
        "features": ["Editable .docx files — works in Word and Google Docs", "Master address change checklist", "Notification letters for landlords, schools, and employers", "Vehicle and voter registration guides", "First 24 Hours action guide"],
        "transition_page": "/relocation"},
    "retirement": {"name": "Retirement Planning Bundle", "price": 1800, "desc": "15 documents for retirement planning",
        "headline": "You Planned the Career. Now Plan the Exit.",
        "emoji": "🌅", "count": "15",
        "long_desc": "Medicare, Social Security, pension decisions, and everything else you need to plan for retirement — comparison worksheets, application organizers, and legacy planning tools.",
        "includes": [
            ("Social Security Application Information Organizer", "Organizes the documents and information you need to apply for Social Security benefits — work history, banking details, and dependent info."),
            ("Employer Retirement Notification Letter", "A professional letter notifying your employer of your retirement date and requesting information about final pay and benefits."),
            ("Pension Benefit Election Comparison Worksheet", "Compare pension payout options side-by-side — lump sum vs. annuity, single vs. joint life — so you can make an informed choice."),
            ("Required Minimum Distribution (RMD) Request Letter", "A letter to your retirement account custodian requesting your required minimum distribution."),
            ("Medicare Enrollment Checklist & Cover Letter", "A step-by-step checklist for Medicare enrollment plus a cover letter for submitting your application."),
            ("Roth Conversion — Decision Worksheet", "Helps you evaluate whether converting traditional retirement funds to a Roth IRA makes sense for your tax situation."),
            ("Retirement Account Beneficiary Update Letter", "A letter to update the beneficiaries on your retirement accounts — important after any life change."),
            ("Retiree Health Insurance Continuation Request", "Requests continuation of employer-sponsored health insurance into retirement, if your employer offers it."),
            ("Power of Attorney Preparation Checklist", "Organizes what you need to discuss with an attorney when setting up financial and healthcare powers of attorney."),
            ("Letter of Instruction to Heirs", "A personal letter to your family explaining where to find important documents, accounts, and your wishes — not a legal document, but invaluable."),
            ("Social Security Delay Strategy Worksheet", "Helps you calculate the break-even point for delaying Social Security and decide when to start collecting."),
            ("Legacy Letter / Ethical Will", "A guided template for writing a personal letter to your loved ones — your values, stories, and wishes beyond the legal will."),
            ("Healthcare Bridge Cost Comparison (Pre-Medicare)", "Compare healthcare options for the gap between retirement and Medicare eligibility — COBRA, marketplace, and retiree plans."),
            ("Medicare Plan Comparison Worksheet", "Side-by-side comparison of Medicare Advantage vs. Medigap plans — premiums, coverage, and out-of-pocket costs."),
            ("What to Do in the First 24 Hours After Deciding to Retire", "A prioritized guide for the day you decide to retire — who to notify, what to research, and what to start planning."),
        ],
        "features": ["Editable .docx files — works in Word and Google Docs", "Medicare and Social Security planning tools", "Pension and retirement account comparison worksheets", "Legacy and estate preparation documents", "First 24 Hours action guide"],
        "transition_page": "/retirement"},
    "addiction": {"name": "Addiction & Recovery Guide", "price": 1800, "desc": "10 guides for supporting someone through addiction",
        "headline": "You Don't Have to Navigate This Alone.",
        "emoji": "\ud83e\udec2", "count": "10",
        "long_desc": "Step-by-step guidance for supporters \u2014 understanding addiction, having the conversation, navigating treatment options, taking care of yourself, and building a path forward.",
        "includes": [
            ("First 24 Hours: Someone You Love Is in Crisis", "What to do \u2014 and what not to do \u2014 when you first discover or confront a loved one\u2019s substance use."),
            ("Understanding Addiction", "The brain science, the spectrum of severity, and why willpower alone is rarely enough."),
            ("Signs and Red Flags", "Behavioral, physical, and financial warning signs to watch for."),
            ("How to Talk to Someone About Their Addiction", "When to bring it up, what to say, and what to expect \u2014 including conversation scripts."),
            ("Taking Care of Yourself", "Why self-care is essential, not selfish \u2014 and how to maintain your health while supporting someone."),
            ("Treatment Options & How to Choose", "Detox, inpatient, outpatient, PHP, IOP, MAT, and sober living \u2014 what each means and how to evaluate programs."),
            ("Health Complications & Comorbidities", "Medical risks to watch for and when to seek emergency care."),
            ("Legal & Financial Considerations", "Protecting your finances, understanding involuntary commitment laws, and navigating legal issues."),
            ("After Treatment: Recovery & Relapse", "What to expect, warning signs, and how to support long-term recovery."),
            ("Resource Directory", "Hotlines, support groups, treatment locators, and tools for supporters."),
        ],
        "features": ["10 in-depth guides written for supporters and families", "Phase-based checklist system with 50 tasks", "Glossary of 19 addiction and recovery terms", "Resource directory with hotlines and organizations", "Navigator trained for addiction-related queries"],
        "transition_page": "/addiction"},
}

# Pass products ($39 each — full dashboard for 1 life change)
PASS_PRODUCTS = {
    "pass-job-loss": {"name": "Job Loss Pass", "price": 3900, "transition": "job-loss",
        "desc": "Full dashboard access for Job Loss & Income Crisis — checklists, content library, scripts, state-specific guidance."},
    "pass-estate": {"name": "Estate Pass", "price": 3900, "transition": "estate",
        "desc": "Full dashboard access for Death & Estate — checklists, content library, scripts, state-specific guidance."},
    "pass-divorce": {"name": "Divorce Pass", "price": 3900, "transition": "divorce",
        "desc": "Full dashboard access for Divorce & Separation — checklists, content library, scripts, state-specific guidance."},
    "pass-disability": {"name": "Disability Pass", "price": 3900, "transition": "disability",
        "desc": "Full dashboard access for Disability & Benefits — checklists, content library, scripts, state-specific guidance."},
    "pass-relocation": {"name": "Relocation Pass", "price": 3900, "transition": "relocation",
        "desc": "Full dashboard access for Moving & Relocation — checklists, content library, scripts, state-specific guidance."},
    "pass-retirement": {"name": "Retirement Pass", "price": 3900, "transition": "retirement",
        "desc": "Full dashboard access for Retirement Planning — checklists, content library, scripts, state-specific guidance."},
    "pass-addiction": {"name": "Addiction Pass", "price": 3900, "transition": "addiction",
        "desc": "Full dashboard access for Addiction & Recovery — checklists, content library, scripts, resource directories."},
}

# Subscription removed — all purchases are one-time

import secrets

BUNDLE_FILES = {
    "master": "master-bundle.zip",
    "job-loss": "jobloss.zip",
    "estate": "estate.zip",
    "divorce": "divorce.zip",
    "disability": "disability.zip",
    "relocation": "relocation.zip",
    "retirement": "retirement.zip",
}


def preload_bundle_templates(user_id, category):
    """Extract individual template files from a bundle zip and add them to the user's workspace.
    Called after purchase fulfillment or Etsy code redemption."""
    import zipfile as _zipfile

    # For master bundle, preload all individual bundles
    if category == "master":
        for cat in BUNDLE_FILES:
            if cat != "master":
                preload_bundle_templates(user_id, cat)
        return

    zip_filename = BUNDLE_FILES.get(category)
    if not zip_filename:
        print(f"[preload] No bundle zip for category: {category}")
        return

    zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "bundles", zip_filename)
    if not os.path.exists(zip_path):
        print(f"[preload] Bundle zip not found: {zip_path}")
        return

    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.utcnow().isoformat()

    # Check what templates this user already has (avoid duplicates)
    cur = db_execute(conn, f"SELECT original_name FROM user_files WHERE user_id = {param} AND category = {param}", (user_id, category))
    existing_names = set(row[0] for row in cur.fetchall())

    try:
        with _zipfile.ZipFile(zip_path, "r") as zf:
            for entry in sorted(zf.namelist()):
                # Skip directories, hidden files, macOS metadata, and .unpack_ folders
                if entry.endswith("/"):
                    continue
                basename = os.path.basename(entry)
                if not basename or basename.startswith("."):
                    continue
                if "/__MACOSX/" in entry or "/.unpack_" in entry or "__MACOSX/" in entry or ".unpack_" in entry.split("/")[-2] if "/" in entry else False:
                    continue
                # Only include .docx and .pdf files at the top level of the bundle folder
                parts = entry.split("/")
                if len(parts) != 2:
                    continue  # Skip nested files (inside .unpack_ dirs etc.)
                ext = os.path.splitext(basename)[1].lower()
                if ext not in (".docx", ".pdf"):
                    continue

                # Clean up the display name: remove numbering prefix like "1. "
                display_name = basename

                # Skip if already preloaded
                if display_name in existing_names:
                    continue

                # Read file data from zip
                file_data = zf.read(entry)
                file_size = len(file_data)

                # Determine content type
                content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == ".docx" else "application/pdf"

                # Encrypt and store
                stored_name = f"{uuid.uuid4().hex}{ext}"
                encrypted_data = file_cipher.encrypt(file_data)
                storage_save(user_id, stored_name, encrypted_data)

                # Insert into user_files with transition-specific category
                db_execute(conn, f"""INSERT INTO user_files (user_id, original_name, stored_name, category, file_size, content_type, uploaded_at)
                    VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param})""",
                    (user_id, display_name, stored_name, category, file_size, content_type, now))
                existing_names.add(display_name)

            conn.commit()
            count = len(existing_names)
            print(f"[preload] Loaded templates for user {user_id}, category {category}")
    except Exception as e:
        print(f"[preload] Error extracting bundle for user {user_id}, category {category}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


@app.route("/api/create-checkout", methods=["POST"])
def create_checkout():
    data = request.get_json()
    product_id = data.get("product_id")
    if product_id not in PRODUCTS:
        return jsonify({"error": "Invalid product"}), 400
    product = PRODUCTS[product_id]
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=data.get("email"),
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": product["name"], "description": product["desc"]},
                    "unit_amount": product["price"],
                },
                "quantity": 1,
            }],
            mode="payment",
            allow_promotion_codes=True,
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "templates#" + product_id,
            metadata={"product_id": product_id},
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/create-pass-checkout", methods=["POST"])
def create_pass_checkout():
    """Create Stripe checkout for a Chapter Pass ($39)."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    pass_id = data.get("pass_id")
    if pass_id not in PASS_PRODUCTS:
        return jsonify({"error": "Invalid pass"}), 400
    product = PASS_PRODUCTS[pass_id]
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=user["email"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": product["name"], "description": "Full access to one transition's complete guide, scripts, and tools."},
                    "unit_amount": product["price"],
                },
                "quantity": 1,
            }],
            mode="payment",
            allow_promotion_codes=True,
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "pricing",
            metadata={"product_id": pass_id, "purchase_type": "pass", "transition": product["transition"], "user_id": str(user["id"])},
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/create-transition-checkout", methods=["POST"])
def create_transition_checkout():
    """Create Stripe checkout for One Transition ($39) or Add a Transition ($20)."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json() or {}
    category = data.get("category")
    if category not in VALID_CATEGORIES:
        return jsonify({"error": "Invalid category"}), 400
    cats = get_user_categories(user)
    if cats.get(category) == "full":
        return jsonify({"error": "You already have full access to this category."}), 400
    # Price: $39 for first full transition, $20 for additional
    full_count = sum(1 for v in cats.values() if v == "full")
    if full_count == 0:
        base_price = 3900
        product_name = f"One Transition — {CATEGORY_LABELS.get(category, category)}"
        purchase_type = "one_transition"
    else:
        base_price = 2000
        product_name = f"Add a Transition — {CATEGORY_LABELS.get(category, category)}"
        purchase_type = "add_transition"
    # Apply credit
    credit = user.get("credit_cents", 0)
    charge = max(0, base_price - credit)
    if charge == 0:
        # Credit covers the full price — fulfill immediately without Stripe
        _fulfill_transition_purchase(user, category, purchase_type, base_price, credit, None, None)
        return jsonify({"ok": True, "redirect": "/dashboard"})
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=user["email"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": product_name},
                    "unit_amount": charge,
                },
                "quantity": 1,
            }],
            mode="payment",
            allow_promotion_codes=True,
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "pricing",
            metadata={
                "purchase_type": purchase_type,
                "category": category,
                "user_id": str(user["id"]),
                "base_price": str(base_price),
                "credit_applied": str(min(credit, base_price)),
            },
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/create-all-transitions-checkout", methods=["POST"])
def create_all_transitions_checkout():
    """Create Stripe checkout for All Transitions ($125 minus credit)."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    credit = user.get("credit_cents", 0)
    charge = max(0, 12500 - credit)
    if charge == 0:
        _fulfill_all_transitions(user, 12500, credit, None, None)
        return jsonify({"ok": True, "redirect": "/dashboard"})
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=user["email"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "All Transitions"},
                    "unit_amount": charge,
                },
                "quantity": 1,
            }],
            mode="payment",
            allow_promotion_codes=True,
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "pricing",
            metadata={
                "purchase_type": "all_transitions",
                "user_id": str(user["id"]),
                "credit_applied": str(min(credit, 12500)),
            },
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/create-individual-template-checkout", methods=["POST"])
def create_individual_template_checkout():
    """Create Stripe checkout for a single template ($3)."""
    data = request.get_json() or {}
    template_id = data.get("template_id")
    template_name = data.get("template_name", "Individual Template")
    email = data.get("email")
    user = get_current_user()
    if not template_id:
        return jsonify({"error": "No template specified"}), 400
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=email or (user["email"] if user else None),
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": template_name},
                    "unit_amount": 300,
                },
                "quantity": 1,
            }],
            mode="payment",
            allow_promotion_codes=True,
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "templates",
            metadata={
                "purchase_type": "individual_template",
                "template_id": template_id,
                "template_name": template_name,
                "user_id": str(user["id"]) if user else "",
            },
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Gift Certificate System ──

GIFT_PRODUCTS = {
    "gift-transition": {"name": "Bundled Plan Gift", "price": 3900, "gift_type": "one_transition", "label": "Bundled Plan (one transition)"},
    "gift-all": {"name": "All Access Gift", "price": 12500, "gift_type": "all_transitions", "label": "All Access — All Transitions"},
}

def generate_gift_code():
    """Generate a human-readable gift code like LUME-XXXX-XXXX."""
    import random, string
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=4))
    part2 = ''.join(random.choices(chars, k=4))
    return f"LUME-{part1}-{part2}"

@app.route("/api/create-gift-checkout", methods=["POST"])
def create_gift_checkout():
    """Create Stripe checkout for a gift certificate."""
    data = request.get_json() or {}
    product_id = data.get("product_id", "")
    purchaser_name = data.get("purchaser_name", "").strip()
    purchaser_email = data.get("purchaser_email", "").strip()
    recipient_name = data.get("recipient_name", "").strip()
    transition_category = data.get("transition_category", "")

    if product_id not in GIFT_PRODUCTS:
        return jsonify({"error": "Invalid gift product"}), 400
    if not purchaser_email:
        return jsonify({"error": "Your email is required"}), 400
    # recipient_name is optional — buyer can leave blank

    gift = GIFT_PRODUCTS[product_id]
    label = gift["label"]
    # For single transition gifts, include the category in the label
    if gift["gift_type"] == "one_transition" and transition_category in CATEGORY_LABELS:
        label = f"Bundled Plan — {CATEGORY_LABELS[transition_category]}"

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=purchaser_email,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Gift: {label}"},
                    "unit_amount": gift["price"],
                },
                "quantity": 1,
            }],
            mode="payment",
            allow_promotion_codes=True,
            success_url=request.host_url + "gift/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "pricing",
            metadata={
                "purchase_type": "gift",
                "gift_product_id": product_id,
                "gift_type": gift["gift_type"],
                "gift_label": label,
                "purchaser_name": purchaser_name,
                "purchaser_email": purchaser_email,
                "recipient_name": recipient_name,
                "transition_category": transition_category,
            },
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/gift/success")
def gift_success():
    return render_template_string(open("gift-success.html").read())

@app.route("/gift/redeem")
def gift_redeem_page():
    return render_template_string(open("gift-redeem.html").read())

@app.route("/api/gift/redeem", methods=["POST"])
def gift_redeem():
    """Redeem a gift code — grants the purchased tier to the logged-in user."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Please log in or create an account first, then redeem your code."}), 401
    code = (request.get_json() or {}).get("code", "").strip().upper()
    if not code:
        return jsonify({"error": "Please enter a gift code."}), 400

    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, gift_type, gift_label, redeemed_by, redeemed_at FROM gift_codes WHERE code = {param}", (code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "That code doesn't look right. Double-check and try again."}), 400

    gift_id, gift_type, gift_label, redeemed_by, redeemed_at = row
    if redeemed_by is not None:
        conn.close()
        return jsonify({"error": "This gift code has already been redeemed."}), 400

    now = datetime.now(timezone.utc).isoformat()
    uid = user["id"]

    # Mark as redeemed
    db_execute(conn, f"UPDATE gift_codes SET redeemed_by = {param}, redeemed_at = {param} WHERE id = {param}",
               (uid, now, gift_id))
    conn.commit()

    # Grant access based on gift type
    if gift_type == "all_transitions":
        for cat in VALID_CATEGORIES:
            add_user_category(uid, cat, "full", conn)
        db_execute(conn, f"UPDATE users SET tier = 'all_transitions' WHERE id = {param}", (uid,))
        db_execute(conn, f"UPDATE users SET credit_cents = 12500 WHERE id = {param}", (uid,))
        conn.commit()
        msg = "Gift redeemed! You now have All Access — every transition, every feature."
    elif gift_type == "one_transition":
        # Get the transition category from the gift record
        cur2 = db_execute(conn, f"SELECT gift_label FROM gift_codes WHERE id = {param}", (gift_id,))
        # Try to extract category from label, or grant a choosable one
        # For now, grant full access to one category — they pick on dashboard
        msg = f"Gift redeemed! You have access to the {gift_label}. Head to your dashboard to get started."
        # Grant credit equivalent
        db_execute(conn, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + 3900 WHERE id = {param}", (uid,))
        conn.commit()
    elif gift_type == "starter":
        db_execute(conn, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + 1600 WHERE id = {param}", (uid,))
        conn.commit()
        msg = f"Gift redeemed! You have $16 in credit toward any bundle."
    else:
        msg = "Gift redeemed!"

    update_user_tier_from_access(uid, conn)
    conn.close()

    return jsonify({"ok": True, "message": msg, "gift_type": gift_type})


@app.route("/api/gift/redeem-start", methods=["POST"])
def gift_redeem_start():
    """Step 1: Validate gift code + send auth code to email."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip().upper()

    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    if not code:
        return jsonify({"error": "Please enter your gift code."}), 400

    # Validate gift code exists and isn't redeemed
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, redeemed_by FROM gift_codes WHERE code = {param}", (code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "That code doesn't look right. Double-check and try again."}), 400
    if row[1] is not None:
        conn.close()
        return jsonify({"error": "This gift code has already been redeemed."}), 400

    # Send auth code (reuse existing logic from auth_send_code)
    # Rate limit
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    cur = db_execute(conn, f"SELECT COUNT(*) FROM auth_codes WHERE email = {param} AND created_at > {param}", (email, one_hour_ago))
    count = cur.fetchone()[0]
    if count >= 5:
        conn.close()
        return jsonify({"error": "Too many attempts. Please try again later."}), 429

    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    # Demo account: use fixed code, skip email
    if email == "demo@lumeway.co":
        auth_code = "000000"
        db_execute(conn, f"INSERT INTO auth_codes (email, code, created_at, expires_at) VALUES ({param}, {param}, {param}, {param})", (email, auth_code, now, expires))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "Demo account — use code 000000.", "demo": True, "demo_code": "000000"})

    auth_code = str(random.randint(100000, 999999))
    db_execute(conn, f"INSERT INTO auth_codes (email, code, created_at, expires_at) VALUES ({param}, {param}, {param}, {param})", (email, auth_code, now, expires))
    conn.commit()
    conn.close()

    if not send_auth_code(email, auth_code):
        return jsonify({"error": "Failed to send verification code. Please try again."}), 500

    return jsonify({"ok": True, "message": "Verification code sent! Check your email."})


@app.route("/api/gift/redeem-verify", methods=["POST"])
def gift_redeem_verify():
    """Step 2: Verify auth code, log in, redeem gift."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    gift_code = (data.get("code") or "").strip().upper()
    auth_code = (data.get("auth_code") or "").strip()

    if not email or not gift_code or not auth_code:
        return jsonify({"error": "All fields are required."}), 400

    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()

    # Verify auth code
    false_val = "FALSE" if USE_POSTGRES else "0"
    cur = db_execute(conn, f"SELECT id FROM auth_codes WHERE email = {param} AND code = {param} AND used = {false_val} AND expires_at > {param} ORDER BY created_at DESC LIMIT 1", (email, auth_code, now))
    auth_row = cur.fetchone()
    if not auth_row:
        conn.close()
        return jsonify({"error": "Invalid or expired code. Please try again."}), 401

    # Mark auth code as used
    true_val = "TRUE" if USE_POSTGRES else "1"
    db_execute(conn, f"UPDATE auth_codes SET used = {true_val} WHERE id = {param}", (auth_row[0],))

    # Find or create user
    cur = db_execute(conn, f"SELECT id, email FROM users WHERE email = {param}", (email,))
    user_row = cur.fetchone()
    is_new = False
    if user_row:
        user_id = user_row[0]
        db_execute(conn, f"UPDATE users SET last_login_at = {param} WHERE id = {param}", (now, user_id))
    else:
        is_new = True
        db_execute(conn, f"INSERT INTO users (email, created_at, last_login_at) VALUES ({param}, {param}, {param})", (email, now, now))
        cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (email,))
        user_id = cur.fetchone()[0]

    # Validate and redeem gift code
    cur = db_execute(conn, f"SELECT id, gift_type, gift_label, redeemed_by, transition_category FROM gift_codes WHERE code = {param}", (gift_code,))
    gift_row = cur.fetchone()
    if not gift_row:
        conn.close()
        return jsonify({"error": "Gift code not found."}), 400
    gift_id, gift_type, gift_label, redeemed_by, gift_transition = gift_row
    if redeemed_by is not None:
        conn.close()
        return jsonify({"error": "This gift code has already been redeemed."}), 400

    # Mark gift as redeemed
    db_execute(conn, f"UPDATE gift_codes SET redeemed_by = {param}, redeemed_at = {param} WHERE id = {param}", (user_id, now, gift_id))
    conn.commit()

    # Grant access based on gift type
    if gift_type == "all_transitions":
        for cat in VALID_CATEGORIES:
            add_user_category(user_id, cat, "full", conn)
        db_execute(conn, f"UPDATE users SET tier = 'all_transitions' WHERE id = {param}", (user_id,))
        db_execute(conn, f"UPDATE users SET credit_cents = 12500 WHERE id = {param}", (user_id,))
        conn.commit()
        # Auto-load templates for each transition
        for cat in VALID_CATEGORIES:
            if cat in BUNDLE_FILES:
                try:
                    preload_bundle_templates(user_id, cat)
                except Exception as e:
                    print(f"[gift] Error preloading {cat} templates: {e}")
        msg = "Gift redeemed! You now have All Access — every transition, every feature."
    elif gift_type == "one_transition":
        # Grant access to the specific transition the buyer chose
        gift_cat = gift_transition if gift_transition in VALID_CATEGORIES else None
        if gift_cat:
            add_user_category(user_id, gift_cat, "full", conn)
            db_execute(conn, f"UPDATE users SET transition_type = {param} WHERE id = {param}", (gift_cat, user_id))
            conn.commit()
            # Auto-load templates for this transition
            if gift_cat in BUNDLE_FILES:
                try:
                    preload_bundle_templates(user_id, gift_cat)
                except Exception as e:
                    print(f"[gift] Error preloading {gift_cat} templates: {e}")
            cat_label = CATEGORY_LABELS.get(gift_cat, gift_cat)
            msg = f"Gift redeemed! You have the {cat_label} bundle. If you'd like to switch to a different transition, email cara@lumeway.co."
        else:
            # Fallback: give credit if no category specified
            db_execute(conn, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + 3900 WHERE id = {param}", (user_id,))
            conn.commit()
            msg = "Gift redeemed! You have $39 in credit toward any transition plan."
    else:
        msg = "Gift redeemed!"

    # Mark user as gift redeemer for onboarding
    try:
        db_execute(conn, f"UPDATE users SET onboarding_source = 'gift' WHERE id = {param}", (user_id,))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    update_user_tier_from_access(user_id, conn)

    # Set session (log them in)
    flask_session["user_id"] = user_id
    flask_session.permanent = True

    conn.close()
    return jsonify({"ok": True, "message": msg, "gift_type": gift_type, "is_new": is_new})


def handle_gift_webhook(session_data, metadata):
    """Handle gift certificate purchase — generate code, store, email certificate."""
    email = _get_session_email(session_data)
    session_id = _get_session_field(session_data, "id")
    gift_product_id = metadata.get("gift_product_id", "")
    gift_type = metadata.get("gift_type", "")
    gift_label = metadata.get("gift_label", "")
    purchaser_name = metadata.get("purchaser_name", "")
    purchaser_email = metadata.get("purchaser_email", email)
    recipient_name = metadata.get("recipient_name", "")
    transition_category = metadata.get("transition_category", "")

    if not purchaser_email:
        print(f"Cannot handle gift: no email")
        return

    # Generate unique code
    code = generate_gift_code()
    # Ensure uniqueness
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    for _ in range(10):
        cur = db_execute(conn, f"SELECT id FROM gift_codes WHERE code = {param}", (code,))
        if not cur.fetchone():
            break
        code = generate_gift_code()

    now = datetime.now(timezone.utc).isoformat()
    gift_price = GIFT_PRODUCTS.get(gift_product_id, {}).get("price", 0)

    # Store gift code
    try:
        db_execute(conn,
            f"""INSERT INTO gift_codes (code, purchaser_email, purchaser_name, recipient_name, gift_type, gift_label, amount_cents, stripe_session_id, transition_category, created_at)
            VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param})""",
            (code, purchaser_email, purchaser_name, recipient_name, gift_type, gift_label, gift_price, session_id, transition_category, now))
        conn.commit()
    except Exception as e:
        print(f"Error storing gift code: {e}")
    conn.close()

    # Send email with gift certificate attached
    threading.Thread(target=send_gift_email, args=(purchaser_email, purchaser_name, recipient_name, code, gift_label, gift_price), daemon=True).start()
    print(f"Gift purchased: {purchaser_email} → {recipient_name}, code={code}, type={gift_label}")


def send_gift_email(to_email, purchaser_name, recipient_name, code, gift_label, amount_cents):
    """Send the gift purchase confirmation with HTML certificate attached."""
    import base64

    # Build the HTML certificate
    certificate_html = build_gift_certificate(purchaser_name, recipient_name, code, gift_label, amount_cents)

    # Email body
    body = email_wrap(f"""
    <h2 style="font-family:'Libre Baskerville',Georgia,serif;font-size:22px;font-weight:400;color:#2C4A5E;margin:0 0 16px;line-height:1.3;">Your gift is ready</h2>
    <p style="font-size:14px;line-height:1.7;margin:0 0 16px;color:#4A5568;">
        You purchased a <strong>{gift_label}</strong> gift. The redemption code is:
    </p>
    <div style="background:#F5F0E8;border:2px dashed #B8977E;border-radius:12px;padding:20px;text-align:center;margin:0 0 20px;">
        <span style="font-family:'Plus Jakarta Sans',monospace;font-size:24px;font-weight:700;color:#2C4A5E;letter-spacing:3px;">{code}</span>
    </div>
    <p style="font-size:14px;line-height:1.7;margin:0 0 12px;color:#4A5568;">
        <strong>How they redeem it:</strong>
    </p>
    <ol style="font-size:13px;line-height:1.8;color:#4A5568;padding-left:20px;margin:0 0 20px;">
        <li>Go to <a href="https://lumeway.co/gift/redeem" style="color:#C4704E;font-weight:500;">lumeway.co/gift/redeem</a></li>
        <li>Create a free account (or log in)</li>
        <li>Enter the code above</li>
    </ol>
    <p style="font-size:13px;line-height:1.7;margin:0 0 8px;color:#6B7B8D;">
        We also attached a printable gift certificate to this email — feel free to print it out or forward this email.
    </p>
    """)

    # Send with attachment via Resend
    cert_b64 = base64.b64encode(certificate_html.encode("utf-8")).decode("utf-8")
    try:
        resp = http_requests.post("https://api.resend.com/emails", json={
            "from": "Lumeway <hello@lumeway.co>",
            "to": [to_email],
            "subject": "Your Lumeway gift certificate is ready",
            "html": body,
            "attachments": [{
                "filename": "lumeway-gift-certificate.html",
                "content": cert_b64,
            }],
        }, headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }, timeout=15)
        if resp.status_code == 200:
            print(f"Gift email sent to {to_email}")
        else:
            print(f"Gift email error ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Failed to send gift email: {e}")


def build_gift_certificate(purchaser_name, recipient_name, code, gift_label, amount_cents):
    """Build a printable HTML gift certificate using Carol's designed template."""
    template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lumeway Gift Certificate</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=Montserrat:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  @page {
    size: 8.5in 11in;
    margin: 0;
  }

  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  body {
    font-family: 'Montserrat', sans-serif;
    background: #f7f4ef;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .certificate {
    width: 8.5in;
    height: 11in;
    background: #f7f4ef;
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }

  /* Subtle linen texture */
  .certificate::before {
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-conic-gradient(rgba(160,136,120,0.018) 0% 25%, transparent 0% 50%) 0 0 / 4px 4px;
    pointer-events: none;
    z-index: 0;
  }

  /* Soft radial glow */
  .certificate::after {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 38%, rgba(255,255,255,0.35) 0%, transparent 55%);
    pointer-events: none;
    z-index: 0;
  }

  .content {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 5.8in;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 0 0.4in;
  }

  /* Decorative border frame */
  .frame {
    position: absolute;
    z-index: 1;
    top: 0.55in;
    left: 0.55in;
    right: 0.55in;
    bottom: 0.55in;
    border: 1px solid rgba(141,119,104,0.18);
    border-radius: 3px;
    pointer-events: none;
  }
  .frame::before {
    content: '';
    position: absolute;
    top: 6px;
    left: 6px;
    right: 6px;
    bottom: 6px;
    border: 1px solid rgba(141,119,104,0.10);
    border-radius: 2px;
  }

  /* Botanical corner accents */
  .botanical {
    position: absolute;
    z-index: 2;
    opacity: 0.07;
    pointer-events: none;
  }
  .botanical-tl { top: 0.65in; left: 0.65in; width: 90px; height: 90px; }
  .botanical-tr { top: 0.65in; right: 0.65in; width: 90px; height: 90px; transform: scaleX(-1); }
  .botanical-bl { bottom: 0.65in; left: 0.65in; width: 90px; height: 90px; transform: scaleY(-1); }
  .botanical-br { bottom: 0.65in; right: 0.65in; width: 90px; height: 90px; transform: scale(-1, -1); }

  /* Sun mark logo */
  .sun-mark { width: 52px; height: 52px; margin-bottom: 20px; }
  .sun-mark svg { width: 100%; height: 100%; }

  .brand-name {
    font-family: 'Cormorant Garamond', serif;
    font-size: 15px; font-weight: 400; letter-spacing: 8px;
    text-transform: uppercase; color: #1b3a5c; margin-bottom: 36px;
  }

  .divider { width: 60px; height: 1px; background: #c4b5a6; margin: 0 auto; }
  .divider-top { margin-bottom: 40px; }

  .gift-headline {
    font-family: 'Cormorant Garamond', serif;
    font-size: 38px; font-weight: 300; color: #1b3a5c;
    line-height: 1.25; margin-bottom: 10px; letter-spacing: 0.5px;
  }

  .gift-subline {
    font-family: 'Cormorant Garamond', serif;
    font-size: 26px; font-weight: 300; font-style: italic;
    color: #8d7768; line-height: 1.35; margin-bottom: 36px;
  }

  .blurb {
    font-family: 'Montserrat', sans-serif;
    font-size: 11.5px; font-weight: 300; color: #6b5b50;
    line-height: 1.8; max-width: 4.6in; margin-bottom: 34px;
  }

  .code-section { margin-bottom: 38px; display: flex; flex-direction: column; align-items: center; }
  .code-label {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 500; letter-spacing: 3px;
    text-transform: uppercase; color: #8d7768; margin-bottom: 12px;
  }
  .code-box {
    background: rgba(255,255,255,0.7);
    border: 1.5px dashed rgba(141,119,104,0.30);
    border-radius: 6px; padding: 18px 40px; display: inline-block;
  }
  .code-value {
    font-family: 'Cormorant Garamond', serif;
    font-size: 28px; font-weight: 500; letter-spacing: 6px; color: #1b3a5c;
  }

  .redeem-section { margin-bottom: 32px; max-width: 4in; text-align: center; }
  .redeem-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 500; letter-spacing: 3px;
    text-transform: uppercase; color: #8d7768; margin-bottom: 18px;
  }
  .redeem-steps {
    list-style: none; padding: 0; display: flex; flex-direction: column;
    gap: 8px; text-align: left; max-width: 3.4in; margin: 0 auto;
  }
  .redeem-steps li {
    font-family: 'Montserrat', sans-serif;
    font-size: 12px; font-weight: 300; color: #5c4d43;
    line-height: 1.55; display: flex; align-items: first baseline; gap: 8px;
  }
  .step-num {
    font-family: 'Montserrat', sans-serif;
    font-size: 12px; font-weight: 500; color: #1b3a5c;
    flex-shrink: 0; width: 18px; text-align: right;
  }
  .step-text a {
    color: #1b3a5c; font-weight: 500; text-decoration: none;
    border-bottom: 1px solid rgba(27,58,92,0.25);
  }
  .redeem-note {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 300; font-style: italic;
    color: #8d7768; margin-top: 14px; line-height: 1.6;
  }

  .personal-note {
    font-family: 'Montserrat', sans-serif;
    font-size: 10.5px; font-weight: 300; color: #6b5b50;
    line-height: 1.75; max-width: 4.2in; margin-bottom: 34px; text-align: center;
  }
  .personal-note a {
    color: #1b3a5c; font-weight: 500; text-decoration: none;
    border-bottom: 1px solid rgba(27,58,92,0.25);
  }

  .divider-bottom { margin-bottom: 32px; }

  .footer { display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .footer-tagline {
    font-family: 'Cormorant Garamond', serif;
    font-size: 13px; font-weight: 300; font-style: italic;
    color: #8d7768; letter-spacing: 0.5px;
  }
  .footer-url {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 400; letter-spacing: 2px;
    color: #b8a192; text-transform: lowercase;
  }

  @media print {
    body { background: #f7f4ef; padding: 0; margin: 0; }
    .certificate { page-break-after: avoid; }
  }
</style>
</head>
<body>
  <div class="certificate">
    <div class="frame"></div>

    <svg class="botanical botanical-tl" viewBox="0 0 90 90" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 80 Q 25 55, 45 45 Q 30 40, 15 50" stroke="#6b5b50" stroke-width="1.2" stroke-linecap="round" fill="none"/>
      <path d="M10 80 Q 20 60, 38 52 Q 22 48, 12 58" stroke="#6b5b50" stroke-width="0.8" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 50 30, 48 15" stroke="#6b5b50" stroke-width="1" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 55 35, 60 20" stroke="#6b5b50" stroke-width="0.7" stroke-linecap="round" fill="none"/>
      <circle cx="45" cy="44" r="2" fill="#6b5b50" opacity="0.4"/>
      <circle cx="47" cy="16" r="1.5" fill="#6b5b50" opacity="0.3"/>
    </svg>
    <svg class="botanical botanical-tr" viewBox="0 0 90 90" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 80 Q 25 55, 45 45 Q 30 40, 15 50" stroke="#6b5b50" stroke-width="1.2" stroke-linecap="round" fill="none"/>
      <path d="M10 80 Q 20 60, 38 52 Q 22 48, 12 58" stroke="#6b5b50" stroke-width="0.8" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 50 30, 48 15" stroke="#6b5b50" stroke-width="1" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 55 35, 60 20" stroke="#6b5b50" stroke-width="0.7" stroke-linecap="round" fill="none"/>
      <circle cx="45" cy="44" r="2" fill="#6b5b50" opacity="0.4"/>
      <circle cx="47" cy="16" r="1.5" fill="#6b5b50" opacity="0.3"/>
    </svg>
    <svg class="botanical botanical-bl" viewBox="0 0 90 90" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 80 Q 25 55, 45 45 Q 30 40, 15 50" stroke="#6b5b50" stroke-width="1.2" stroke-linecap="round" fill="none"/>
      <path d="M10 80 Q 20 60, 38 52 Q 22 48, 12 58" stroke="#6b5b50" stroke-width="0.8" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 50 30, 48 15" stroke="#6b5b50" stroke-width="1" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 55 35, 60 20" stroke="#6b5b50" stroke-width="0.7" stroke-linecap="round" fill="none"/>
      <circle cx="45" cy="44" r="2" fill="#6b5b50" opacity="0.4"/>
      <circle cx="47" cy="16" r="1.5" fill="#6b5b50" opacity="0.3"/>
    </svg>
    <svg class="botanical botanical-br" viewBox="0 0 90 90" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 80 Q 25 55, 45 45 Q 30 40, 15 50" stroke="#6b5b50" stroke-width="1.2" stroke-linecap="round" fill="none"/>
      <path d="M10 80 Q 20 60, 38 52 Q 22 48, 12 58" stroke="#6b5b50" stroke-width="0.8" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 50 30, 48 15" stroke="#6b5b50" stroke-width="1" stroke-linecap="round" fill="none"/>
      <path d="M45 45 Q 55 35, 60 20" stroke="#6b5b50" stroke-width="0.7" stroke-linecap="round" fill="none"/>
      <circle cx="45" cy="44" r="2" fill="#6b5b50" opacity="0.4"/>
      <circle cx="47" cy="16" r="1.5" fill="#6b5b50" opacity="0.3"/>
    </svg>

    <div class="content">
      <div class="sun-mark">
        <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="50" cy="50" r="16" fill="#5c4d43"/>
          <line x1="50" y1="28" x2="50" y2="10" stroke="#5c4d43" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="50" y1="72" x2="50" y2="90" stroke="#5c4d43" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="28" y1="50" x2="10" y2="50" stroke="#5c4d43" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="72" y1="50" x2="90" y2="50" stroke="#5c4d43" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="34.4" y1="34.4" x2="21.7" y2="21.7" stroke="#5c4d43" stroke-width="1.2" stroke-linecap="round"/>
          <line x1="65.6" y1="65.6" x2="78.3" y2="78.3" stroke="#5c4d43" stroke-width="1.2" stroke-linecap="round"/>
          <line x1="34.4" y1="65.6" x2="21.7" y2="78.3" stroke="#5c4d43" stroke-width="1.2" stroke-linecap="round"/>
          <line x1="65.6" y1="34.4" x2="78.3" y2="21.7" stroke="#5c4d43" stroke-width="1.2" stroke-linecap="round"/>
          <line x1="41" y1="30" x2="36" y2="18" stroke="#5c4d43" stroke-width="0.8" stroke-linecap="round"/>
          <line x1="59" y1="30" x2="64" y2="18" stroke="#5c4d43" stroke-width="0.8" stroke-linecap="round"/>
          <line x1="41" y1="70" x2="36" y2="82" stroke="#5c4d43" stroke-width="0.8" stroke-linecap="round"/>
          <line x1="59" y1="70" x2="64" y2="82" stroke="#5c4d43" stroke-width="0.8" stroke-linecap="round"/>
        </svg>
      </div>

      <div class="brand-name">Lumeway</div>
      <div class="divider divider-top"></div>

      <div class="gift-headline">Someone is thinking of you.</div>
      <div class="gift-subline">You've been gifted a Lumeway bundle<br>to help you through this change.</div>

      <p class="blurb">
        Lumeway helps people navigate life's hardest moments — job loss, divorce, loss of a loved one, disability, relocation, and retirement. With step-by-step worksheets, planning tools, and practical resources, we help you understand what comes next and find your way through.
      </p>

      <div class="code-section">
        <div class="code-label">Your Redemption Code</div>
        <div class="code-box">
          <span class="code-value">{{REDEMPTION_CODE}}</span>
        </div>
      </div>

      <div class="redeem-section">
        <div class="redeem-title">How to Redeem</div>
        <ol class="redeem-steps">
          <li>
            <span class="step-num">1.</span>
            <span class="step-text">Visit <a href="https://lumeway.co/gift/redeem">lumeway.co/gift/redeem</a></span>
          </li>
          <li>
            <span class="step-num">2.</span>
            <span class="step-text">Enter your code and email address</span>
          </li>
          <li>
            <span class="step-num">3.</span>
            <span class="step-text">Check your email for a login link</span>
          </li>
          <li>
            <span class="step-num">4.</span>
            <span class="step-text">Log in — your bundle and guide will be ready in your dashboard</span>
          </li>
        </ol>
        <p class="redeem-note">Your code never expires. Take your time.</p>
      </div>

      <p class="personal-note">
        Not sure where to start, or having trouble redeeming your code?<br>
        Our founder Cara is happy to help — reach out at <a href="mailto:cara@lumeway.co">cara@lumeway.co</a>.
      </p>

      <div class="divider divider-bottom"></div>

      <div class="footer">
        <div class="footer-tagline">When life changes, find your way through.</div>
        <div class="footer-url">lumeway.co</div>
      </div>
    </div>
  </div>
</body>
</html>"""
    return template.replace("{{REDEMPTION_CODE}}", code)


@app.route("/api/redeem-code", methods=["POST"])
def redeem_code():
    """Redeem a promo code or Etsy purchase code."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Please log in first."}), 401
    code = (request.get_json() or {}).get("code", "").strip().upper()

    # Demo reset code — wipes the account back to a fresh new user (demo account only)
    if code == "DEMOTEST":
        if user.get("email") != "demo@lumeway.co":
            print(f"DEMOTEST rejected: user email is {user.get('email')}, not demo@lumeway.co")
            return jsonify({"error": "This code is only for the demo account."}), 400
        uid = user["id"]
        print(f"DEMOTEST: Resetting demo account (user_id={uid})")
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        # Clear all user data
        try:
            db_execute(conn, f"DELETE FROM community_replies WHERE post_id IN (SELECT id FROM community_posts WHERE user_id = {param})", (uid,))
        except Exception:
            pass
        try:
            db_execute(conn, f"DELETE FROM community_replies WHERE user_id = {param}", (uid,))
        except Exception:
            pass
        # Delete chat_messages first (linked to chat_sessions by session_id, no cascade)
        try:
            db_execute(conn, f"DELETE FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE user_id = {param})", (uid,))
        except Exception as e:
            print(f"DEMOTEST: chat_messages cleanup error: {e}")
        for table in ["community_posts", "checklist_items", "user_deadlines", "user_documents_needed", "user_goals", "user_notes", "chat_sessions", "user_files"]:
            try:
                db_execute(conn, f"DELETE FROM {table} WHERE user_id = {param}", (uid,))
            except Exception as e:
                print(f"DEMOTEST: {table} cleanup error: {e}")
        # Reset user profile to fresh state
        try:
            db_execute(conn, f"UPDATE users SET tier = 'free', display_name = NULL, transition_type = NULL, us_state = NULL, active_transitions = '[]', credit_cents = 0 WHERE id = {param}", (uid,))
            conn.commit()
        except Exception:
            pass
        try:
            db_execute(conn, f"UPDATE users SET onboarding_source = NULL WHERE id = {param}", (uid,))
            conn.commit()
        except Exception:
            pass
        # Clear user_access (purchased bundles)
        try:
            db_execute(conn, f"DELETE FROM user_access WHERE user_id = {param}", (uid,))
        except Exception:
            pass
        # Clear purchases tied to this email
        try:
            db_execute(conn, f"DELETE FROM purchases WHERE email = {param}", (user["email"],))
        except Exception:
            pass
        # Un-redeem any gift codes so they can be reused for testing
        try:
            db_execute(conn, f"UPDATE gift_codes SET redeemed_by = NULL, redeemed_at = NULL WHERE redeemed_by = {param}", (uid,))
        except Exception:
            pass
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "Account reset to new user. Refreshing...", "reload": True})

    # Check gift codes first (LUME-XXXX-XXXX format)
    if code.startswith("LUME-"):
        conn_g = get_db()
        param_g = "%s" if USE_POSTGRES else "?"
        cur_g = db_execute(conn_g, f"SELECT id, gift_type, gift_label, redeemed_by, transition_category FROM gift_codes WHERE code = {param_g}", (code,))
        gift_row = cur_g.fetchone()
        if gift_row:
            gift_id, gift_type, gift_label, redeemed_by, gift_transition = gift_row
            if redeemed_by is not None:
                conn_g.close()
                return jsonify({"error": "This gift code has already been redeemed."}), 400
            now = datetime.now(timezone.utc).isoformat()
            uid = user["id"]
            db_execute(conn_g, f"UPDATE gift_codes SET redeemed_by = {param_g}, redeemed_at = {param_g} WHERE id = {param_g}",
                       (uid, now, gift_id))
            conn_g.commit()
            if gift_type == "all_transitions":
                for cat in VALID_CATEGORIES:
                    add_user_category(uid, cat, "full", conn_g)
                db_execute(conn_g, f"UPDATE users SET tier = 'all_transitions' WHERE id = {param_g}", (uid,))
                db_execute(conn_g, f"UPDATE users SET credit_cents = 12500 WHERE id = {param_g}", (uid,))
                conn_g.commit()
                # Auto-load templates for each transition
                for cat in VALID_CATEGORIES:
                    if cat in BUNDLE_FILES:
                        try:
                            preload_bundle_templates(uid, cat)
                        except Exception as e:
                            print(f"[gift] Error preloading {cat} templates: {e}")
                msg = "Gift redeemed! You now have All Access — every transition, every feature."
            elif gift_type == "one_transition":
                gift_cat = gift_transition if gift_transition in VALID_CATEGORIES else None
                if gift_cat:
                    add_user_category(uid, gift_cat, "full", conn_g)
                    db_execute(conn_g, f"UPDATE users SET transition_type = {param_g} WHERE id = {param_g}", (gift_cat, uid))
                    conn_g.commit()
                    if gift_cat in BUNDLE_FILES:
                        try:
                            preload_bundle_templates(uid, gift_cat)
                        except Exception as e:
                            print(f"[gift] Error preloading {gift_cat} templates: {e}")
                    cat_label = CATEGORY_LABELS.get(gift_cat, gift_cat)
                    msg = f"Gift redeemed! You have the {cat_label} bundle. If you'd like to switch, email cara@lumeway.co."
                else:
                    db_execute(conn_g, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + 3900 WHERE id = {param_g}", (uid,))
                    conn_g.commit()
                    msg = f"Gift redeemed! You have $39 in credit toward any transition plan."
            elif gift_type == "starter":
                db_execute(conn_g, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + 1600 WHERE id = {param_g}", (uid,))
                conn_g.commit()
                msg = "Gift redeemed! You have $16 in credit toward any bundle."
            else:
                msg = "Gift redeemed!"
            update_user_tier_from_access(uid, conn_g)
            conn_g.close()
            return jsonify({"ok": True, "category": "gift", "credit_cents": 0, "message": msg})
        conn_g.close()
        # Fall through to check other code types

    # Check promo codes first (full access grants)
    if code in PROMO_CODES:
        promo = PROMO_CODES[code]
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        # Check if already redeemed
        cur = db_execute(conn, f"SELECT id FROM etsy_redemptions WHERE user_id = {param} AND code = {param}", (user["id"], code))
        already_redeemed = cur.fetchone() is not None
        now = datetime.now(timezone.utc).isoformat()
        if not already_redeemed:
            # Record redemption
            db_execute(conn, f"INSERT INTO etsy_redemptions (user_id, code, category, credit_cents, redeemed_at) VALUES ({param}, {param}, {param}, {param}, {param})",
                       (user["id"], code, "promo-all", 0, now))
        # Always re-grant full access (ensures tier is correct even if redeemed before)
        for cat in VALID_CATEGORIES:
            add_user_category(user["id"], cat, "full", conn)
        update_user_tier_from_access(user["id"], conn)
        conn.commit()
        conn.close()
        msg = "You already have full access — you're all set!" if already_redeemed else "Code redeemed. You now have full access to everything — all guides, checklists, and tools for every life change."
        return jsonify({
            "ok": True,
            "category": "all",
            "credit_cents": 0,
            "message": msg
        })

    if code not in ETSY_CODES:
        return jsonify({"error": "That code doesn't look right. Double-check and try again."}), 400
    code_info = ETSY_CODES[code]
    category = code_info["category"]
    credit_amount = code_info["credit_cents"]
    # Check if already redeemed by this user for this category
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id FROM etsy_redemptions WHERE user_id = {param} AND category = {param}", (user["id"], category))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "You've already redeemed a code for this category."}), 400
    now = datetime.now(timezone.utc).isoformat()
    # Record redemption
    db_execute(conn, f"INSERT INTO etsy_redemptions (user_id, code, category, credit_cents, redeemed_at) VALUES ({param}, {param}, {param}, {param}, {param})",
               (user["id"], code, category, credit_amount, now))
    # Add credit
    db_execute(conn, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + {param} WHERE id = {param}", (credit_amount, user["id"]))
    conn.commit()
    # Grant starter access (templates only) for the category
    if category == "master":
        for cat in VALID_CATEGORIES:
            add_user_category(user["id"], cat, "starter", conn)
    else:
        add_user_category(user["id"], category, "starter", conn)
    update_user_tier_from_access(user["id"], conn)
    # Grant template bundle downloads
    cats_to_grant = VALID_CATEGORIES if category == "master" else [category]
    for cat in cats_to_grant:
        bundle_product = PRODUCTS.get(cat, {})
        if bundle_product:
            bundle_token = secrets.token_urlsafe(32)
            try:
                db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
                    """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user["email"], cat, bundle_product.get("name", f"{cat.title()} Bundle"), 0,
                     f"etsy-redeem-{cat}-{now}", None, now, bundle_token, True if USE_POSTGRES else 1))
                conn.commit()
            except Exception as e:
                print(f"Error granting etsy bundle {cat}: {e}")
    conn.close()
    # Preload individual template files into user's workspace
    try:
        preload_bundle_templates(user["id"], category)
    except Exception as e:
        print(f"[preload] Error during Etsy preload for user {user['id']}: {e}")
    return jsonify({
        "ok": True,
        "category": category,
        "credit_cents": credit_amount,
        "message": f"Code redeemed. Your {CATEGORY_LABELS.get(category, 'templates')} worksheets are ready in Files & Templates."
    })

@app.route("/api/account/upgrade-options")
def upgrade_options():
    """Return available upgrades with credit-adjusted pricing."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    cats = get_user_categories(user)
    credit = user.get("credit_cents", 0)
    full_count = sum(1 for v in cats.values() if v == "full")
    options = []
    # One Transition (if no full access yet)
    if full_count == 0:
        for cat in VALID_CATEGORIES:
            if cats.get(cat) != "full":
                charge = max(0, 3900 - credit)
                options.append({
                    "type": "one_transition",
                    "category": cat,
                    "label": CATEGORY_LABELS.get(cat, cat),
                    "base_price": 3900,
                    "credit": min(credit, 3900),
                    "charge": charge,
                })
    # Add a Transition (if already have at least one full)
    if full_count >= 1 and full_count < 6:
        for cat in VALID_CATEGORIES:
            if cats.get(cat) != "full":
                options.append({
                    "type": "add_transition",
                    "category": cat,
                    "label": CATEGORY_LABELS.get(cat, cat),
                    "base_price": 2000,
                    "credit": 0,
                    "charge": 2000,
                })
    # All Transitions
    if full_count < 6:
        charge = max(0, 12500 - credit)
        options.append({
            "type": "all_transitions",
            "category": "all",
            "label": "All Transitions",
            "base_price": 12500,
            "credit": min(credit, 12500),
            "charge": charge,
        })
    return jsonify({"options": options, "credit_cents": credit, "category_access": cats, "effective_tier": get_effective_tier(user)})

@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            print(f"Webhook signature verification failed: {e}")
            return "Invalid signature", 400
    else:
        event = json.loads(payload)
    # Stripe event objects use attribute access, not .get()
    event_type = event["type"] if isinstance(event, dict) else event.type
    if event_type == "checkout.session.completed":
        session_data = event["data"]["object"] if isinstance(event, dict) else event.data.object
        print(f"Webhook received: checkout.session.completed")
        # Route based on purchase type
        if isinstance(session_data, dict):
            metadata = session_data.get("metadata") or {}
        else:
            raw_meta = session_data.metadata
            if raw_meta and not isinstance(raw_meta, dict):
                try:
                    metadata = dict(raw_meta)
                except Exception:
                    metadata = {k: getattr(raw_meta, k, None) for k in ["purchase_type", "product_id", "transition", "user_id"] if getattr(raw_meta, k, None) is not None}
            else:
                metadata = raw_meta or {}
        purchase_type = metadata.get("purchase_type", "") if isinstance(metadata, dict) else getattr(metadata, "purchase_type", "")
        print(f"Webhook metadata: {metadata}, purchase_type: {purchase_type}")
        if purchase_type == "gift":
            handle_gift_webhook(session_data, metadata)
        elif purchase_type == "cart":
            handle_cart_webhook(session_data, metadata)
        elif purchase_type in ("one_transition", "add_transition"):
            handle_transition_webhook(session_data, metadata)
        elif purchase_type == "all_transitions":
            handle_all_transitions_webhook(session_data, metadata)
        elif purchase_type == "individual_template":
            handle_individual_template_webhook(session_data, metadata)
        elif purchase_type in ("pass", "unlimited"):
            # Legacy: handle old-style pass/unlimited purchases
            handle_tier_upgrade(session_data, metadata)
        else:
            fulfill_purchase(session_data)
    return "ok", 200

def fulfill_purchase(session_data):
    """Record purchase and send download email."""
    # Handle both Stripe objects and dicts
    if hasattr(session_data, 'customer_details'):
        email = getattr(session_data.customer_details, 'email', None) or getattr(session_data, 'customer_email', None)
        product_id = getattr(session_data.metadata, 'product_id', None) if hasattr(session_data, 'metadata') else None
        session_id = getattr(session_data, 'id', None)
        payment_intent = getattr(session_data, 'payment_intent', None)
    else:
        email = (session_data.get("customer_details") or {}).get("email") or session_data.get("customer_email")
        product_id = (session_data.get("metadata") or {}).get("product_id")
        session_id = session_data.get("id")
        payment_intent = session_data.get("payment_intent")
    if not email or not product_id or product_id not in PRODUCTS:
        print(f"Cannot fulfill: email={email}, product_id={product_id}")
        return
    product = PRODUCTS[product_id]
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = get_db()
        db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
            """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, product_id, product["name"], product["price"],
             session_id, payment_intent,
             now, token, True if USE_POSTGRES else 1))
        conn.commit()
        conn.close()
        print(f"Purchase recorded: {email} bought {product['name']}")
    except Exception as e:
        print(f"DB error recording purchase: {e}")
    # Grant starter-level category access for bundle purchases
    # Map product_id to category for starter access
    bundle_category_map = {
        "bundle-job-loss": "job-loss",
        "bundle-estate": "estate",
        "bundle-divorce": "divorce",
        "bundle-disability": "disability",
        "bundle-relocation": "relocation",
        "bundle-retirement": "retirement",
        "bundle-master": None,  # master bundle = all categories
    }
    category = bundle_category_map.get(product_id)
    try:
        conn2 = get_db()
        param2 = "%s" if USE_POSTGRES else "?"
        cur2 = db_execute(conn2, f"SELECT id FROM users WHERE email = {param2}", (email,))
        row2 = cur2.fetchone()
        if row2:
            uid = row2[0]
            if product_id == "bundle-master":
                # Master bundle grants starter access to all categories
                for cat in VALID_CATEGORIES:
                    add_user_category(uid, cat, "starter")
            elif category:
                add_user_category(uid, category, "starter")
            update_user_tier_from_access(uid)
            # Also add $16 credit for the bundle purchase
            db_execute(conn2, f"UPDATE users SET credit_cents = credit_cents + 1600 WHERE id = {param2}", (uid,))
            # Preload individual template files into user's workspace
            conn2.commit()
            conn2.close()
            try:
                bundle_cat = "master" if product_id == "bundle-master" else category
                if bundle_cat:
                    preload_bundle_templates(uid, bundle_cat)
            except Exception as pe:
                print(f"[preload] Error during purchase preload for user {uid}: {pe}")
        else:
            conn2.commit()
            conn2.close()
    except Exception as e:
        print(f"Error granting starter access: {e}")
    # Send email in background thread so it doesn't block the response
    threading.Thread(target=send_purchase_email, args=(email, product_id, product["name"], token), daemon=True).start()
    print(f"Email send initiated for {email}")
    # Schedule post-purchase email sequence
    threading.Thread(target=schedule_post_purchase_emails, args=(email, product["name"], False), daemon=True).start()

def handle_tier_upgrade(session_data, metadata):
    """Handle pass/unlimited purchases: update tier + create purchase record + send email."""
    print(f"handle_tier_upgrade called with metadata: {metadata}")
    if hasattr(session_data, 'customer_details'):
        email = getattr(session_data.customer_details, 'email', None) or getattr(session_data, 'customer_email', None)
        session_id = getattr(session_data, 'id', None)
        payment_intent = getattr(session_data, 'payment_intent', None)
        customer_id = getattr(session_data, 'customer', None)
        sub_id = getattr(session_data, 'subscription', None)
    else:
        email = (session_data.get("customer_details") or {}).get("email") or session_data.get("customer_email")
        session_id = session_data.get("id")
        payment_intent = session_data.get("payment_intent")
        customer_id = session_data.get("customer")
        sub_id = session_data.get("subscription")

    purchase_type = metadata.get("purchase_type", "")
    product_id = metadata.get("product_id", "")
    transition = metadata.get("transition", "")
    user_id_str = metadata.get("user_id", "")

    if not email:
        print(f"Cannot handle tier upgrade: no email")
        return

    # Determine tier, product name, and price
    if purchase_type == "pass" and product_id in PASS_PRODUCTS:
        product = PASS_PRODUCTS[product_id]
        tier = "pass"
        product_name = product["name"]
        amount_cents = product["price"]
    elif purchase_type == "unlimited":
        tier = "unlimited"
        product_id = "unlimited"
        product_name = "Unlimited Subscription"
        amount_cents = 999
    else:
        print(f"Unknown tier purchase type: {purchase_type}")
        return

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"

    # Update user tier
    try:
        if tier == "pass":
            db_execute(conn, f"UPDATE users SET tier = 'pass', tier_transition = {param} WHERE email = {param}", (transition, email))
        elif tier == "unlimited":
            db_execute(conn, f"UPDATE users SET tier = 'unlimited', stripe_customer_id = {param} WHERE email = {param}", (customer_id, email))
        conn.commit()
        print(f"User {email} upgraded to tier={tier}")
    except Exception as e:
        print(f"Error updating user tier: {e}")

    # Create purchase record so it shows in Purchases tab
    token = secrets.token_urlsafe(32)
    try:
        db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
            """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, product_id, product_name, amount_cents,
             session_id, payment_intent, now, token, True if USE_POSTGRES else 1))
        conn.commit()
        print(f"Tier purchase recorded: {email} bought {product_name}")
    except Exception as e:
        print(f"DB error recording tier purchase: {e}")

    # Grant template bundle downloads
    bundles_to_grant = []
    if tier == "pass" and transition and transition in BUNDLE_FILES:
        bundles_to_grant = [transition]
    elif tier == "unlimited":
        bundles_to_grant = [k for k in BUNDLE_FILES.keys() if k != "master"]  # 6 individual bundles, not master
    for bundle_id in bundles_to_grant:
        bundle_product = PRODUCTS.get(bundle_id, {})
        bundle_token = secrets.token_urlsafe(32)
        try:
            db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
                """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (email, bundle_id, bundle_product.get("name", f"{bundle_id.title()} Bundle"), 0,
                 (session_id or "") + "-bundle-" + bundle_id, None, now, bundle_token, True if USE_POSTGRES else 1))
            conn.commit()
            print(f"Bundle access granted: {email} got {bundle_id} templates")
        except Exception as e:
            print(f"DB error granting bundle {bundle_id}: {e}")

    # Get user ID for preloading
    uid = None
    try:
        conn_uid = get_db()
        cur_uid = db_execute(conn_uid, f"SELECT id FROM users WHERE email = {param}", (email,))
        row_uid = cur_uid.fetchone()
        if row_uid:
            uid = row_uid[0]
        conn_uid.close()
    except Exception:
        pass

    conn.close()

    # Preload template files into user's workspace
    if uid and bundles_to_grant:
        try:
            for bundle_cat in bundles_to_grant:
                preload_bundle_templates(uid, bundle_cat)
        except Exception as pe:
            print(f"[preload] Error during tier upgrade preload for user {uid}: {pe}")

    # Send confirmation email
    threading.Thread(target=send_tier_email, args=(email, tier, product_name), daemon=True).start()
    # Schedule post-purchase email sequence (plans are is_plan=True)
    threading.Thread(target=schedule_post_purchase_emails, args=(email, product_name, True), daemon=True).start()

def send_tier_email(to_email, tier, product_name):
    """Send tier upgrade confirmation email."""
    if not RESEND_API_KEY:
        print(f"RESEND_API_KEY not set, skipping tier email to {to_email}")
        return
    if tier == "all_transitions":
        body = "You now have full access to everything — all guides, scripts, and tools for every life change. Your dashboard is ready."
    elif tier == "unlimited":
        # Legacy
        body = "You have full access to everything — all guides, scripts, and tools for every life change."
    else:
        body = f"Your {product_name} is now active. Your dashboard is ready with the full guide, checklists, scripts, and tools."
    html = email_wrap(f"""
<p style="{_e_hi}">Hi there,</p>
<p style="{_e_p}">{body}</p>
{_e_btn('https://lumeway.co/dashboard', 'Go to Your Dashboard')}
<p style="{_e_muted}">If you have any questions, just reply to this email.</p>""")
    try:
        resp = http_requests.post("https://api.resend.com/emails", json={
            "from": "Lumeway <hello@lumeway.co>",
            "to": [to_email],
            "subject": f"Your {product_name} is active",
            "html": html,
        }, headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }, timeout=10)
        print(f"Tier email sent to {to_email}: {resp.status_code}")
    except Exception as e:
        print(f"Failed to send tier email to {to_email}: {e}")

def handle_transition_webhook(session_data, metadata):
    """Handle one_transition or add_transition purchase from webhook."""
    email = _get_session_email(session_data)
    session_id = _get_session_field(session_data, "id")
    payment_intent = _get_session_field(session_data, "payment_intent")
    category = metadata.get("category", "")
    purchase_type = metadata.get("purchase_type", "")
    user_id_str = metadata.get("user_id", "")
    base_price = int(metadata.get("base_price", "3900"))
    credit_applied = int(metadata.get("credit_applied", "0"))
    if not email or not category:
        print(f"Cannot handle transition purchase: email={email}, category={category}")
        return
    # Find user
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (email,))
    row = cur.fetchone()
    if not row:
        conn.close()
        print(f"User not found for {email}")
        return
    uid = row[0]
    _fulfill_transition_purchase_db(conn, uid, email, category, purchase_type, base_price, credit_applied, session_id, payment_intent)
    conn.close()

def handle_all_transitions_webhook(session_data, metadata):
    """Handle all_transitions purchase from webhook."""
    email = _get_session_email(session_data)
    session_id = _get_session_field(session_data, "id")
    payment_intent = _get_session_field(session_data, "payment_intent")
    credit_applied = int(metadata.get("credit_applied", "0"))
    user_id_str = metadata.get("user_id", "")
    if not email:
        print(f"Cannot handle all_transitions: no email")
        return
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (email,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    uid = row[0]
    _fulfill_all_transitions_db(conn, uid, email, 12500, credit_applied, session_id, payment_intent)
    conn.close()

def handle_individual_template_webhook(session_data, metadata):
    """Handle individual $3 template purchase from webhook."""
    email = _get_session_email(session_data)
    session_id = _get_session_field(session_data, "id")
    payment_intent = _get_session_field(session_data, "payment_intent")
    template_id = metadata.get("template_id", "")
    template_name = metadata.get("template_name", "Individual Template")
    if not email:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Record purchase
    token = secrets.token_urlsafe(32)
    try:
        db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
            """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, f"template-{template_id}", template_name, 300, session_id, payment_intent, now, token, True if USE_POSTGRES else 1))
        conn.commit()
    except Exception as e:
        print(f"Error recording individual template purchase: {e}")
    # Add $3 credit to user
    try:
        db_execute(conn, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + 300 WHERE email = {param}", (email,))
        conn.commit()
    except Exception as e:
        print(f"Error adding credit for individual template: {e}")
    conn.close()
    # Send download email
    threading.Thread(target=send_purchase_email, args=(email, f"template-{template_id}", template_name, token), daemon=True).start()
    print(f"Individual template purchased: {email} bought {template_name}")

def handle_cart_webhook(session_data, metadata):
    """Handle cart checkout from webhook — fulfills all items in cart."""
    email = _get_session_email(session_data)
    session_id = _get_session_field(session_data, "id")
    payment_intent = _get_session_field(session_data, "payment_intent")
    if not email:
        print("Cart webhook: no email found")
        return
    product_ids = metadata.get("product_ids", "").split(",")
    purchase_types = metadata.get("purchase_types", "").split(",")
    credit_used = int(metadata.get("credit_used", "0"))
    user_id_str = metadata.get("user_id", "")
    # Deduct credit if any was used
    if credit_used > 0 and user_id_str:
        try:
            conn = get_db()
            param = "%s" if USE_POSTGRES else "?"
            db_execute(conn, f"UPDATE users SET credit_cents = GREATEST(0, credit_cents - {param}) WHERE id = {param}" if USE_POSTGRES else
                       f"UPDATE users SET credit_cents = MAX(0, credit_cents - {param}) WHERE id = {param}", (credit_used, int(user_id_str)))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error deducting credit in cart webhook: {e}")
    # Look up user
    user_id = None
    try:
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (email,))
        row = cur.fetchone()
        if row:
            user_id = row[0]
        conn.close()
    except:
        pass
    # Fulfill each product
    for i, pid in enumerate(product_ids):
        ptype = purchase_types[i] if i < len(purchase_types) else "bundle"
        # Build an item dict for _fulfill_cart_item
        item = {"product_id": pid, "name": pid, "price": 0, "purchase_type": ptype}
        # Try to get proper name/price from PRODUCTS
        if pid in PRODUCTS:
            item["name"] = PRODUCTS[pid]["name"]
            item["price"] = PRODUCTS[pid]["price"] / 100
        # Extract category from product_id
        if pid.startswith("plan-"):
            cat = pid.replace("plan-", "")
            item["category"] = cat
        elif pid.startswith("bundle-"):
            item["category"] = pid.replace("bundle-", "")
        _fulfill_cart_item(email, item, user_id)
    print(f"Cart webhook fulfilled: {email} bought {product_ids}")

def _fulfill_transition_purchase(user, category, purchase_type, base_price, credit_applied, session_id, payment_intent):
    """Fulfill a transition purchase (called from route or webhook)."""
    conn = get_db()
    _fulfill_transition_purchase_db(conn, user["id"], user["email"], category, purchase_type, base_price, credit_applied, session_id, payment_intent)
    conn.close()

def _fulfill_transition_purchase_db(conn, user_id, email, category, purchase_type, base_price, credit_applied, session_id, payment_intent):
    """Core logic: record purchase, grant access, update credit."""
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    charge = max(0, base_price - credit_applied)
    product_name = f"{CATEGORY_LABELS.get(category, category)} — Full Access"
    # Record the purchase
    token = secrets.token_urlsafe(32)
    try:
        db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
            """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, f"transition-{category}", product_name, charge, session_id or f"credit-{now}", payment_intent, now, token, True if USE_POSTGRES else 1))
        conn.commit()
    except Exception as e:
        print(f"Error recording transition purchase: {e}")
    # Grant full access to this category
    add_user_category(user_id, category, "full", conn)
    update_user_tier_from_access(user_id, conn)
    # Update credit: add what they paid (charge = actual money spent)
    if charge > 0:
        try:
            db_execute(conn, f"UPDATE users SET credit_cents = COALESCE(credit_cents, 0) + {param} WHERE id = {param}", (charge, user_id))
            conn.commit()
        except Exception as e:
            print(f"Error updating credit: {e}")
    # Grant template bundle download
    bundle_product = PRODUCTS.get(category, {})
    if bundle_product and category in BUNDLE_FILES:
        bundle_token = secrets.token_urlsafe(32)
        try:
            db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
                """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (email, category, bundle_product.get("name", f"{category.title()} Bundle"), 0,
                 f"transition-bundle-{category}-{now}", None, now, bundle_token, True if USE_POSTGRES else 1))
            conn.commit()
        except Exception as e:
            print(f"Error granting transition bundle {category}: {e}")
    # Send confirmation email
    threading.Thread(target=send_tier_email, args=(email, "one_transition", product_name), daemon=True).start()
    print(f"Transition purchase fulfilled: {email} got full access to {category}")

def _fulfill_all_transitions(user, base_price, credit_applied, session_id, payment_intent):
    """Fulfill all-transitions purchase."""
    conn = get_db()
    _fulfill_all_transitions_db(conn, user["id"], user["email"], base_price, credit_applied, session_id, payment_intent)
    conn.close()

def _fulfill_all_transitions_db(conn, user_id, email, base_price, credit_applied, session_id, payment_intent):
    """Core: grant all 6 categories at full level."""
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    charge = max(0, base_price - credit_applied)
    # Record the purchase
    token = secrets.token_urlsafe(32)
    try:
        db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
            """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, "all-transitions", "All Transitions", charge, session_id or f"credit-{now}", payment_intent, now, token, True if USE_POSTGRES else 1))
        conn.commit()
    except Exception as e:
        print(f"Error recording all-transitions purchase: {e}")
    # Grant full access to all categories
    for cat in VALID_CATEGORIES:
        add_user_category(user_id, cat, "full", conn)
    db_execute(conn, f"UPDATE users SET tier = 'all_transitions' WHERE id = {param}", (user_id,))
    # Set credit to full price
    db_execute(conn, f"UPDATE users SET credit_cents = {param} WHERE id = {param}", (base_price, user_id))
    conn.commit()
    # Grant all bundle downloads
    for cat in VALID_CATEGORIES:
        bundle_product = PRODUCTS.get(cat, {})
        if bundle_product and cat in BUNDLE_FILES:
            bundle_token = secrets.token_urlsafe(32)
            try:
                db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
                    """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (email, cat, bundle_product.get("name", f"{cat.title()} Bundle"), 0,
                     f"all-trans-bundle-{cat}-{now}", None, now, bundle_token, True if USE_POSTGRES else 1))
                conn.commit()
            except Exception as e:
                print(f"Error granting all-trans bundle {cat}: {e}")
    threading.Thread(target=send_tier_email, args=(email, "all_transitions", "All Transitions"), daemon=True).start()
    print(f"All Transitions purchased: {email}")

def _get_session_email(session_data):
    """Extract email from Stripe session data (handles both dict and object)."""
    if hasattr(session_data, 'customer_details'):
        return getattr(session_data.customer_details, 'email', None) or getattr(session_data, 'customer_email', None)
    return (session_data.get("customer_details") or {}).get("email") or session_data.get("customer_email")

def _get_session_field(session_data, field):
    """Extract a field from Stripe session data."""
    if hasattr(session_data, field):
        return getattr(session_data, field, None)
    return session_data.get(field)

@app.route("/purchase-success")
def purchase_success():
    # Clear cart on successful purchase landing
    flask_session.pop("cart", None)
    session_id = request.args.get("session_id")
    print(f"Purchase success page hit, session_id={session_id}")
    if session_id:
        try:
            session_data = stripe.checkout.Session.retrieve(session_id)
            print(f"Session retrieved: payment_status={session_data.payment_status}, metadata={session_data.metadata}")
            if session_data.payment_status == "paid":
                metadata = session_data.metadata if isinstance(session_data.metadata, dict) else dict(session_data.metadata or {})
                product_id = metadata.get("product_id", "")
                purchase_type = metadata.get("purchase_type", "")

                # Check if already fulfilled (webhook may have handled it)
                conn = get_db()
                cur = db_execute(conn, "SELECT download_token FROM purchases WHERE stripe_session_id = %s" if USE_POSTGRES else "SELECT download_token FROM purchases WHERE stripe_session_id = ?", (session_id,))
                row = cur.fetchone()
                conn.close()

                if purchase_type in ("one_transition", "add_transition"):
                    if not row:
                        handle_transition_webhook(session_data, metadata)
                    category = metadata.get("category", "")
                    product_name = CATEGORY_LABELS.get(category, category)
                    return render_template_string(TIER_SUCCESS_HTML, product_name=product_name, tier=purchase_type)
                elif purchase_type == "all_transitions":
                    if not row:
                        handle_all_transitions_webhook(session_data, metadata)
                    return render_template_string(TIER_SUCCESS_HTML, product_name="All Transitions", tier="all_transitions")
                elif purchase_type == "individual_template":
                    if not row:
                        handle_individual_template_webhook(session_data, metadata)
                    template_name = metadata.get("template_name", "your template")
                    return render_template_string(PURCHASE_SUCCESS_HTML, product_name=template_name)
                elif purchase_type in ("pass", "unlimited"):
                    # Legacy support
                    if not row:
                        handle_tier_upgrade(session_data, metadata)
                    product_name = PASS_PRODUCTS.get(product_id, {}).get("name", "Your Plan")
                    return render_template_string(TIER_SUCCESS_HTML, product_name=product_name, tier=purchase_type)
                else:
                    # Template bundle purchase
                    product = PRODUCTS.get(product_id, {})
                    if not row:
                        print(f"No existing purchase found, fulfilling now...")
                        fulfill_purchase(session_data)
                    else:
                        print(f"Purchase already exists in DB, token={row[0]}")
                        email = getattr(session_data.customer_details, 'email', None) or getattr(session_data, 'customer_email', None)
                        if email:
                            print(f"Resending purchase email to {email}")
                            threading.Thread(target=send_purchase_email, args=(email, product_id, product.get("name", ""), row[0]), daemon=True).start()
                    return render_template_string(PURCHASE_SUCCESS_HTML, product_name=product.get("name", "your templates"))
        except Exception as e:
            import traceback
            print(f"Error in purchase-success: {e}")
            traceback.print_exc()
    print("Purchase success: no valid session, redirecting to templates")
    return redirect("/templates")

@app.route("/download/<token>")
def download_page(token):
    conn = get_db()
    cur = db_execute(conn, "SELECT product_id, product_name, email FROM purchases WHERE download_token = %s" if USE_POSTGRES else "SELECT product_id, product_name, email FROM purchases WHERE download_token = ?", (token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return "Invalid or expired download link.", 404
    product_id, product_name, email = row
    filename = BUNDLE_FILES.get(product_id, "")
    return render_template_string(DOWNLOAD_PAGE_HTML, product_name=product_name, product_id=product_id, filename=filename, token=token)

@app.route("/download/<token>/file")
def download_file_purchase(token):
    conn = get_db()
    cur = db_execute(conn, "SELECT product_id FROM purchases WHERE download_token = %s" if USE_POSTGRES else "SELECT product_id FROM purchases WHERE download_token = ?", (token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return "Invalid download link.", 404
    product_id = row[0]
    filename = BUNDLE_FILES.get(product_id)
    if not filename:
        return "File not found.", 404
    return send_from_directory("static/bundles", filename, as_attachment=True)

PURCHASE_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-QHWJDRDR9R"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-QHWJDRDR9R');gtag('event','purchase',{item_name:'{{ product_name }}'});</script>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Purchase Complete — Lumeway</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--cream:#F7F4EF;--warm-white:#FDFCFA;--text:#1B2A38;--navy:#1B3A5C;--gold:#B8977E;--muted:#6E7D8A;--border:#E4DDD3}
body{font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--text)}
nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:20px 48px;display:flex;align-items:center;justify-content:space-between;background:rgba(247,244,239,0.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
.nav-logo{display:flex;align-items:center;gap:10px;text-decoration:none}
.nav-logo-icon{width:32px;height:32px;background:var(--navy);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--cream);font-family:'Cormorant Garamond',serif;font-size:18px;font-weight:500}
.nav-logo-text{font-family:'Cormorant Garamond',serif;font-size:20px;font-weight:500;color:var(--text)}
.back{font-size:14px;color:var(--muted);text-decoration:none}
.back:hover{color:var(--navy)}
.wrap{max-width:560px;margin:0 auto;padding:120px 24px 64px;text-align:center}
.check{width:72px;height:72px;background:#2d6a4f;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 28px;font-size:32px;color:white}
h1{font-family:'Cormorant Garamond',serif;font-size:36px;font-weight:300;margin-bottom:8px}
.product-name{font-size:14px;color:var(--gold);font-weight:500;letter-spacing:0.05em;text-transform:uppercase;margin-bottom:32px}
.steps{background:var(--warm-white);border:1px solid var(--border);border-radius:20px;padding:32px;text-align:left;margin-bottom:32px}
.step{display:flex;gap:16px;margin-bottom:20px}
.step:last-child{margin-bottom:0}
.step-num{width:28px;height:28px;background:var(--navy);color:var(--cream);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;flex-shrink:0;margin-top:2px}
.step-text{font-size:14px;line-height:1.7;color:var(--text)}
.step-text strong{font-weight:500}
.step-text span{color:var(--muted);font-size:13px}
.contact-box{background:var(--warm-white);border:1px solid var(--border);border-radius:16px;padding:20px;margin-bottom:32px;font-size:14px;color:var(--muted);line-height:1.7}
.contact-box a{color:var(--navy);text-decoration:none;font-weight:500}
.btn{display:inline-block;padding:12px 28px;background:var(--navy);color:var(--cream);border-radius:100px;text-decoration:none;font-size:14px;font-weight:500;transition:all 0.2s;margin:0 6px}
.btn:hover{background:#244a6e}
.btn-ghost{display:inline-block;padding:12px 28px;border:1px solid var(--border);color:var(--text);border-radius:100px;text-decoration:none;font-size:14px;transition:all 0.2s;margin:0 6px}
.btn-ghost:hover{background:var(--navy);color:var(--cream)}
footer{padding:28px 48px;border-top:1px solid var(--border);text-align:center}
.footer-note{font-size:12px;color:var(--muted);font-weight:300}
.footer-note a{color:var(--muted);text-decoration:none}
@media(max-width:640px){nav{padding:16px 20px}.wrap{padding:100px 20px 48px}.steps{padding:24px 20px}}
</style></head><body>
<nav>
<a href="/" class="nav-logo"><div class="nav-logo-icon">L</div><span class="nav-logo-text">Lumeway</span></a>
<a href="/templates" class="back">← Templates</a>
</nav>
<div class="wrap">
<div class="check">✓</div>
<h1>Thank you for your purchase!</h1>
<div class="product-name">{{ product_name }}</div>
<div class="steps">
<div class="step"><div class="step-num">1</div><div class="step-text"><strong>Check your email</strong><br><span>We're sending a download link to the email you used at checkout. It should arrive within a few minutes.</span></div></div>
<div class="step"><div class="step-num">2</div><div class="step-text"><strong>Click the download link</strong><br><span>The email contains a unique link that takes you to your personal download page. This link does not expire.</span></div></div>
<div class="step"><div class="step-num">3</div><div class="step-text"><strong>Download your templates</strong><br><span>Your templates come as a .zip file containing editable .docx files. Open them in Microsoft Word or Google Docs.</span></div></div>
</div>
<div class="contact-box">
Didn't receive an email? Check your spam folder first.<br>
Still need help? Email us at <a href="mailto:hello@lumeway.co">hello@lumeway.co</a>
</div>
<a href="/templates" class="btn">Browse More Templates</a>
<a href="/" class="btn-ghost">Back to Lumeway</a>
</div>
<footer>
<img src="/static/logos/lockup-h-navy-cream-v2-transparent.png" alt="Lumeway" class="footer-logo">
<p class="footer-note">Lumeway is an AI guide, not a licensed professional. Always consult a qualified advisor.</p>
<p class="footer-note"><a href="/about">About</a> &middot; <a href="/privacy">Privacy Policy</a></p>
<div class="footer-social"><a href="https://www.pinterest.com/lumeway" rel="noopener" target="_blank" title="Pinterest"><svg viewBox="0 0 24 24"><path d="M12 0C5.373 0 0 5.373 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 01.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/></svg></a></div>
</footer>
</body></html>"""

TIER_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-QHWJDRDR9R"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-QHWJDRDR9R');gtag('event','purchase',{item_name:'{{ product_name }}'});</script>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>You're All Set — Lumeway</title>
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@300;400;700&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--cream:#FAF7F2;--warm-white:#FDFCFA;--text:#2C3E50;--navy:#2C4A5E;--gold:#B8977E;--accent:#C4704E;--muted:#6B7B8D;--border:#E8E0D6;--green:#6B8F5E}
body{font-family:'Plus Jakarta Sans',sans-serif;background:var(--cream);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.card{background:var(--warm-white);border:1px solid var(--border);border-radius:24px;padding:48px;max-width:520px;text-align:center;box-shadow:0 2px 40px rgba(44,62,80,0.06)}
.check{width:72px;height:72px;background:var(--green);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 28px;font-size:32px;color:white}
h1{font-family:'Libre Baskerville',serif;font-size:32px;font-weight:300;margin-bottom:8px}
.plan-badge{display:inline-block;padding:6px 20px;background:var(--navy);color:var(--cream);border-radius:100px;font-size:13px;font-weight:500;margin:16px 0 24px}
.desc{font-size:15px;color:var(--muted);line-height:1.7;margin-bottom:32px;font-weight:300}
.features{background:var(--cream);border-radius:16px;padding:24px;text-align:left;margin-bottom:32px}
.features li{font-size:14px;line-height:2;color:var(--text);font-weight:300;list-style:none;padding-left:24px;position:relative}
.features li::before{content:'✓';position:absolute;left:0;color:var(--green);font-weight:600}
.btn{display:inline-block;padding:14px 36px;background:var(--accent);color:var(--cream);border-radius:100px;text-decoration:none;font-size:15px;font-weight:500;transition:all 0.2s}
.btn:hover{filter:brightness(1.08)}
.secondary{display:block;margin-top:16px;font-size:13px;color:var(--muted);text-decoration:none}
.secondary:hover{color:var(--navy)}
@media(max-width:640px){.card{padding:32px 24px}h1{font-size:26px}}
</style></head><body>
<div class="card">
<div class="check">✓</div>
<h1>You're all set</h1>
<div class="plan-badge">{{ product_name }}</div>
<p class="desc">
{% if tier == 'unlimited' %}
Your Unlimited subscription is active. You have full access to every guide, checklist, script, and template across all six life changes.
{% else %}
Your plan is active. You have full access to your complete guide, checklists, scripts, and templates.
{% endif %}
</p>
<ul class="features">
<li>Full step-by-step guides and checklists</li>
<li>"What to say" phone and email scripts</li>
<li>State-specific guidance and resources</li>
<li>Template worksheets ready to download</li>
<li>Calendar deadlines and document tracker</li>
</ul>
<a href="/dashboard" class="btn">Go to Your Dashboard</a>
<a href="/chat" class="secondary">Or start a conversation with the Navigator →</a>
</div>
</body></html>"""

DOWNLOAD_PAGE_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Download {{ product_name }} — Lumeway</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--cream:#F7F4EF;--text:#1B2A38;--navy:#1B3A5C;--gold:#B8977E;--muted:#6E7D8A;--border:#E4DDD3}
body{font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.card{background:white;border-radius:24px;padding:48px;max-width:480px;text-align:center;box-shadow:0 2px 40px rgba(27,58,92,0.09)}
h1{font-family:'Cormorant Garamond',serif;font-size:32px;font-weight:300;margin-bottom:12px}
p{font-size:15px;color:var(--muted);line-height:1.7;margin-bottom:24px}
.btn{display:inline-block;padding:14px 32px;background:var(--navy);color:var(--cream);border-radius:100px;text-decoration:none;font-size:15px;font-weight:500;transition:all 0.2s}
.btn:hover{background:#244a6e;transform:translateY(-1px)}
.note{font-size:12px;color:var(--muted);margin-top:24px}
</style></head><body>
<div class="card">
<h1>{{ product_name }}</h1>
<p>Your templates are ready to download.</p>
<a href="/download/{{ token }}/file" class="btn">Download Templates</a>
<p class="note">This link is unique to your purchase and does not expire.<br>Questions? Email <a href="mailto:hello@lumeway.co" style="color:var(--navy)">hello@lumeway.co</a></p>
</div></body></html>"""

@app.route("/cart")
def cart_page():
    return send_from_directory(".", "cart.html")

@app.route("/api/cart", methods=["GET"])
def get_cart():
    cart = flask_session.get("cart", [])
    return jsonify({"items": cart})

@app.route("/api/cart/add", methods=["POST"])
def add_to_cart():
    data = request.get_json()
    product_id = data.get("product_id")
    name = data.get("name")
    price = data.get("price")
    item_type = data.get("type")  # "bundle", "individual", "plan"
    purchase_type = data.get("purchase_type", item_type)  # "bundle", "individual", "one_transition", "add_transition", "all_transitions"
    category = data.get("category", "")
    if not product_id or not name or price is None or item_type not in ("bundle", "individual", "plan"):
        return jsonify({"error": "Missing or invalid fields"}), 400
    cart = flask_session.get("cart", [])
    # Prevent duplicates
    for item in cart:
        if item["product_id"] == product_id:
            return jsonify({"items": cart, "message": "Already in cart"})
    cart_item = {"product_id": product_id, "name": name, "price": price, "type": item_type, "purchase_type": purchase_type}
    if category:
        cart_item["category"] = category
    cart.append(cart_item)
    flask_session["cart"] = cart
    return jsonify({"items": cart})

@app.route("/api/cart/remove", methods=["POST"])
def remove_from_cart():
    data = request.get_json()
    product_id = data.get("product_id")
    cart = flask_session.get("cart", [])
    cart = [item for item in cart if item["product_id"] != product_id]
    flask_session["cart"] = cart
    return jsonify({"items": cart})

@app.route("/api/cart/checkout", methods=["POST"])
def cart_checkout():
    cart = flask_session.get("cart", [])
    if not cart:
        return jsonify({"error": "Cart is empty"}), 400
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "Email is required"}), 400
    # Calculate total and build line items
    line_items = []
    product_ids = []
    purchase_types = []
    total_cents = 0
    for item in cart:
        amount_cents = int(item["price"] * 100)
        total_cents += amount_cents
        product_ids.append(item["product_id"])
        purchase_types.append(item.get("purchase_type", "bundle"))
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {"name": item["name"]},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        })
    # Check if logged-in user has credit to apply
    user = get_current_user()
    credit_cents = 0
    user_id = None
    if user:
        credit_cents = user.get("credit_cents", 0)
        user_id = user["id"]
    elif email:
        # Look up by email even if not logged in
        try:
            conn = get_db()
            param = "%s" if USE_POSTGRES else "?"
            cur = db_execute(conn, f"SELECT id, credit_cents FROM users WHERE email = {param}", (email,))
            row = cur.fetchone()
            if row:
                user_id = row[0]
                credit_cents = row[1] or 0
            conn.close()
        except:
            pass
    # Apply credit
    charge_cents = max(0, total_cents - credit_cents)
    credit_used = total_cents - charge_cents
    # If credit covers everything, fulfill immediately
    if charge_cents == 0 and user_id:
        try:
            conn = get_db()
            param = "%s" if USE_POSTGRES else "?"
            db_execute(conn, f"UPDATE users SET credit_cents = credit_cents - {param} WHERE id = {param}", (credit_used, user_id))
            conn.commit()
            conn.close()
            # Fulfill each item in cart
            for item in cart:
                _fulfill_cart_item(email, item, user_id)
            flask_session["cart"] = []
            return jsonify({"fulfilled": True, "redirect": "/dashboard"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    # Otherwise create Stripe checkout
    # If credit applies, adjust the line items
    if credit_used > 0 and len(line_items) > 0:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Account credit applied"},
                "unit_amount": -credit_used if credit_used > 0 else 0,
            },
            "quantity": 1,
        })
        # Stripe doesn't support negative amounts, so recalculate as single line
        line_items = [{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Lumeway — " + ", ".join(item["name"] for item in cart)},
                "unit_amount": charge_cents,
            },
            "quantity": 1,
        }]
    try:
        meta = {
            "product_ids": ",".join(product_ids),
            "purchase_types": ",".join(purchase_types),
            "purchase_type": "cart",
            "email": email,
            "credit_used": str(credit_used),
        }
        if user_id:
            meta["user_id"] = str(user_id)
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=email,
            line_items=line_items,
            mode="payment",
            allow_promotion_codes=True,
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "cart",
            metadata=meta,
        )
        # Don't clear cart here — clear on purchase-success page load so back button works
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _fulfill_cart_item(email, item, user_id):
    """Fulfill a single cart item after payment."""
    product_id = item["product_id"]
    purchase_type = item.get("purchase_type", "bundle")
    now = datetime.now(timezone.utc).isoformat()
    token = secrets.token_urlsafe(32)
    try:
        conn = get_db()
        db_execute(conn, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
            """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, product_id, item["name"], int(item["price"] * 100), "cart-credit-" + now, None, now, token, True if USE_POSTGRES else 1))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error recording cart purchase: {e}")
    # Grant appropriate access based on purchase type
    if purchase_type == "one_transition" and user_id:
        cat = item.get("category", "")
        if cat in VALID_CATEGORIES:
            add_user_category(user_id, cat, "full")
            update_user_tier_from_access(user_id)
    elif purchase_type == "add_transition" and user_id:
        cat = item.get("category", "")
        if cat in VALID_CATEGORIES:
            add_user_category(user_id, cat, "full")
            update_user_tier_from_access(user_id)
    elif purchase_type == "all_transitions" and user_id:
        for cat in VALID_CATEGORIES:
            add_user_category(user_id, cat, "full")
        update_user_tier_from_access(user_id)
    elif purchase_type == "bundle" and user_id:
        # Bundle = starter access for that category
        bundle_category_map = {
            "bundle-job-loss": "job-loss", "bundle-estate": "estate", "bundle-divorce": "divorce",
            "bundle-disability": "disability", "bundle-relocation": "relocation", "bundle-retirement": "retirement",
        }
        cat = bundle_category_map.get(product_id)
        if cat:
            add_user_category(user_id, cat, "starter")
            update_user_tier_from_access(user_id)

@app.route("/pricing")
def pricing():
    return send_from_directory(".", "pricing.html")

@app.route("/templates")
def templates():
    return send_from_directory(".", "templates.html")

@app.route("/templates/<product_id>")
def template_detail(product_id):
    if product_id not in PRODUCTS:
        return redirect("/templates")
    p = PRODUCTS[product_id]
    price_display = f"${p['price'] // 100}" if p['price'] % 100 == 0 else f"${p['price'] / 100:.2f}"
    includes_html = ""
    for i, item in enumerate(p.get("includes", [])):
        if isinstance(item, tuple):
            name, desc = item
            includes_html += f'<div class="doc-item"><button class="doc-toggle" onclick="toggleDoc(this)" aria-expanded="false"><span class="doc-name">{name}</span><span class="doc-chev">+</span></button><div class="doc-desc">{desc}</div></div>'
        else:
            includes_html += f'<div class="doc-item"><div class="doc-name-only">{item}</div></div>'
    features_html = "".join(f"<li>{item}</li>" for item in p.get("features", []))
    transition_link = ""
    if p.get("transition_page"):
        transition_link = f'<a href="{p["transition_page"]}" class="btn-link">Learn more about this transition →</a>'
    master_note = ""
    if product_id != "master":
        master_price = PRODUCTS["master"]["price"]
        master_display = f"${master_price // 100}"
        master_note = f'<div class="master-note"><p>This bundle is also included in the <a href="/templates/master">Life Transition Bundle</a> — all 89+ documents for just {master_display}.</p></div>'
    return render_template_string(BUNDLE_DETAIL_HTML,
        product_id=product_id, name=p["name"], price=price_display,
        headline=p.get("headline", ""), emoji=p.get("emoji", ""),
        count=p.get("count", ""), desc=p["desc"], long_desc=p.get("long_desc", ""),
        includes_html=includes_html, features_html=features_html,
        transition_link=transition_link, master_note=master_note)

BUNDLE_DETAIL_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-QHWJDRDR9R"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-QHWJDRDR9R');</script>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{ name }} — Lumeway</title>
<meta name="description" content="{{ desc }}">
<link rel="canonical" href="https://lumeway.co/templates/{{ product_id }}">
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--cream:#FAF7F2;--warm-white:#FDFCFA;--text:#2C3E50;--muted:#6B7B8D;--navy:#2C4A5E;--gold:#B8977E;--accent:#C4704E;--accent-light:#D4896C;--border:#E8E0D6;--shadow:0 2px 40px rgba(27,58,92,0.09)}
body{font-family:'Plus Jakarta Sans',sans-serif;background:var(--cream);color:var(--text);-webkit-font-smoothing:antialiased}
nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:20px 48px;display:flex;align-items:center;justify-content:space-between;background:rgba(247,244,239,0.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
.nav-logo{display:flex;align-items:center;gap:10px;text-decoration:none}
.sun-icon{display:inline-flex}.sun-icon svg{stroke:currentColor;fill:none;stroke-width:1.5;stroke-linecap:round}
.nav-logo-text{font-family:'Plus Jakarta Sans',sans-serif;font-size:16px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--navy)}
.nav-left{display:flex;align-items:center;gap:28px}
.nav-right{display:flex;gap:12px;align-items:center}
.nav-dropdown{position:relative}
.nav-drop-btn{background:none;border:none;font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;color:var(--muted);cursor:pointer;padding:6px 4px;transition:color 0.15s;display:flex;align-items:center;gap:4px}
.nav-drop-btn:hover{color:var(--navy)}
.nav-drop-btn .chev{display:inline-block;transition:transform 0.2s ease}
.nav-drop-btn[aria-expanded="true"] .chev{transform:rotate(180deg)}
.nav-drop-menu{display:none;position:absolute;top:calc(100% + 8px);left:0;background:var(--warm-white);border:1px solid var(--border);border-radius:12px;padding:6px;min-width:200px;box-shadow:0 8px 24px rgba(27,58,92,0.1);z-index:200}
.nav-drop-menu a{display:block;padding:9px 12px;font-size:13.5px;color:var(--text);text-decoration:none;border-radius:7px}
.nav-drop-menu a:hover{background:var(--cream);color:var(--navy)}
.nav-drop-menu .menu-div{height:1px;background:var(--border);margin:4px 6px}
.nav-dropdown:hover .nav-drop-menu,.nav-dropdown.open .nav-drop-menu{display:block}
.btn-ghost-nav{padding:8px 20px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text);font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;text-decoration:none;transition:all 0.2s}
.btn-ghost-nav:hover{background:var(--navy);color:var(--cream)}
.hero{padding:120px 24px 48px;max-width:720px;margin:0 auto;text-align:center}
.hero-subhead{font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:var(--gold);margin-bottom:16px}
.hero-title{font-family:'Libre Baskerville',serif;font-size:clamp(32px,5vw,52px);font-weight:300;line-height:1.12;margin-bottom:16px}
.hero-title em{font-style:italic;color:var(--gold)}
.hero-subtitle{font-size:16px;color:var(--muted);font-weight:300;line-height:1.7;max-width:520px;margin:0 auto 32px}
.price-block{display:flex;align-items:baseline;justify-content:center;gap:8px;margin-bottom:8px}
.price-big{font-family:'Libre Baskerville',serif;font-size:42px;font-weight:500;color:var(--navy)}
.price-note{font-size:14px;color:var(--muted)}
.count-badge{display:inline-block;background:var(--warm-white);border:1px solid var(--border);padding:4px 14px;border-radius:8px;font-size:13px;color:var(--muted);margin-bottom:24px}
.btn-buy{display:inline-block;padding:14px 36px;border:none;border-radius:8px;background:var(--accent);color:var(--cream);font-family:'Plus Jakarta Sans',sans-serif;font-size:15px;font-weight:500;cursor:pointer;transition:all 0.2s;text-decoration:none}
.btn-buy:hover{background:var(--accent-light);transform:translateY(-1px)}
.btn-buy:disabled{opacity:0.6;cursor:not-allowed;transform:none}
.content{max-width:720px;margin:0 auto;padding:0 24px 64px}
.section-card{background:var(--warm-white);border:1px solid var(--border);border-radius:20px;padding:32px 36px;margin-bottom:24px}
.section-label{font-size:11px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:var(--gold);margin-bottom:12px}
h2{font-family:'Libre Baskerville',serif;font-size:28px;font-weight:400;margin-bottom:16px}
.doc-item{border-bottom:1px solid var(--border)}
.doc-item:last-child{border-bottom:none}
.doc-toggle{width:100%;display:flex;justify-content:space-between;align-items:center;padding:14px 0;background:none;border:none;cursor:pointer;font-family:'Plus Jakarta Sans',sans-serif;text-align:left}
.doc-toggle:hover .doc-name{color:var(--navy)}
.doc-name{font-size:14px;color:var(--text);font-weight:400;line-height:1.5;padding-right:16px}
.doc-name-only{font-size:14px;color:var(--text);padding:14px 0;padding-left:20px;position:relative}
.doc-name-only::before{content:'✓';position:absolute;left:0;color:var(--gold);font-weight:600}
.doc-chev{font-size:18px;color:var(--muted);transition:transform 0.2s;flex-shrink:0}
.doc-desc{display:none;font-size:13px;color:var(--muted);line-height:1.7;padding:0 0 14px 0}
.doc-item.open .doc-desc{display:block}
.doc-item.open .doc-chev{transform:rotate(45deg)}
.features-list{list-style:none;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:8px}
.features-list li{font-size:13px;color:var(--muted);padding-left:20px;position:relative;line-height:1.6}
.features-list li::before{content:'·';position:absolute;left:6px;color:var(--gold);font-weight:700;font-size:18px}
.master-note{background:var(--navy);color:var(--cream);border-radius:16px;padding:20px 28px;margin-bottom:24px;text-align:center}
.master-note p{font-size:14px;line-height:1.6}
.master-note a{color:var(--gold);text-decoration:underline}
.btn-link{display:inline-block;font-size:14px;color:var(--navy);text-decoration:none;margin-top:16px;font-weight:500}
.btn-link:hover{text-decoration:underline}
.cta-block{background:var(--navy);border-radius:24px;padding:40px;text-align:center;max-width:720px;margin:0 auto 64px}
.cta-title{font-family:'Libre Baskerville',serif;font-size:32px;font-weight:300;color:var(--cream);margin-bottom:12px}
.cta-sub{font-size:14px;color:rgba(247,244,239,0.6);margin-bottom:24px}
.btn-cta{display:inline-block;padding:14px 32px;border-radius:8px;background:var(--cream);color:var(--text);font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;font-weight:500;text-decoration:none;transition:all 0.2s}
.btn-cta:hover{background:var(--gold);color:white}
.disclaimer{font-size:11px;color:var(--muted);text-align:center;max-width:520px;margin:0 auto 48px;line-height:1.6}
footer{padding:40px 48px 28px;border-top:1px solid var(--border);display:flex;flex-direction:column;align-items:center;gap:16px;text-align:center}
.footer-logo{height:120px;object-fit:contain;margin-bottom:4px}
.footer-note{font-size:12px;color:var(--muted);font-weight:300;line-height:1.6}
.footer-note a{color:var(--muted);text-decoration:none}
.footer-social{display:flex;gap:16px;align-items:center}
.footer-social a{display:flex;align-items:center;justify-content:center;width:36px;height:36px;border:1px solid var(--border);border-radius:50%;color:var(--muted);text-decoration:none;transition:all 0.15s}
.footer-social a:hover{border-color:var(--gold);color:var(--navy)}
.footer-social svg{width:16px;height:16px;fill:currentColor}
@media(max-width:640px){nav{padding:16px 20px}.section-card{padding:24px 20px}.features-list{grid-template-columns:1fr}.cta-block{margin:0 16px 64px;padding:32px 24px}}
</style></head><body>
<nav>
<div class="nav-left">
<a href="/" class="nav-logo"><span class="sun-icon" style="color:var(--accent)"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M2 12h3M19 12h3M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12"/></svg></span><span class="nav-logo-text">Lumeway</span></a>
<div class="nav-dropdown"><button class="nav-drop-btn" aria-expanded="false">Get help with <span class="chev">▾</span></button>
<div class="nav-drop-menu"><a href="/estate">Death &amp; Estate</a><a href="/divorce">Divorce &amp; Separation</a><a href="/job-loss">Job Loss &amp; Income Crisis</a><a href="/relocation">Moving &amp; Relocation</a><a href="/disability">Disability &amp; Benefits</a><a href="/retirement">Retirement</a></div></div>
<a href="/features" class="nav-link" style="font-size:14px;color:var(--muted);text-decoration:none;padding:6px 4px">Features</a>
<div class="nav-dropdown"><button class="nav-drop-btn" aria-expanded="false">Explore <span class="chev">▾</span></button>
<div class="nav-drop-menu"><a href="/templates">Templates</a><a href="/faq">FAQ</a><a href="/blog">Blog</a><div class="menu-div"></div><a href="/about">About</a><a href="/contact">Contact</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></div></div>
</div>
<div class="nav-right"><a href="/chat" target="_blank" class="btn-ghost-nav">Try it free</a><a href="/templates" class="btn-primary" style="padding:8px 20px;border:none;border-radius:8px;background:var(--accent);color:#fff;font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;text-decoration:none">Shop</a></div>
</nav>
<div class="hero">
<div class="hero-subhead">{{ name }}</div>
<h1 class="hero-title">{{ headline }}</h1>
<p class="hero-subtitle">{{ long_desc }}</p>
<div class="price-block"><span class="price-big">{{ price }}</span><span class="price-note">one-time purchase</span></div>
<div class="count-badge">{{ count }} documents included</div><br>
<button class="btn-buy" onclick="buyProduct('{{ product_id }}')">Buy Now — {{ price }}</button>
</div>
<div class="content">
{{ master_note|safe }}
<div class="section-card">
<div class="section-label">What's Included</div>
<h2>{{ count }} Documents</h2>
<div class="doc-list">{{ includes_html|safe }}</div>
</div>
<div class="section-card">
<div class="section-label">Features</div>
<ul class="features-list">{{ features_html|safe }}</ul>
</div>
{{ transition_link|safe }}
</div>
<div class="disclaimer">These templates are organizational tools designed to help you prepare — not legal documents or substitutes for professional advice. Always consult a qualified professional for decisions specific to your situation.</div>
<div class="cta-block">
<div class="cta-title">Not sure where to start?</div>
<p class="cta-sub">Lumeway's free Transition Navigator can help you understand what comes next.</p>
<a href="/chat" target="_blank" class="btn-cta">Talk to Lumeway free →</a>
</div>
<footer>
<img src="/static/logos/lockup-h-navy-cream-v2-transparent.png" alt="Lumeway" class="footer-logo">
<p class="footer-note">Lumeway is a guidance tool, not a licensed professional. Always consult a qualified advisor.</p>
<p class="footer-note"><a href="/about">About</a> &middot; <a href="/privacy">Privacy Policy</a></p>
<div class="footer-social"><a href="https://www.pinterest.com/lumeway" rel="noopener" target="_blank" title="Pinterest"><svg viewBox="0 0 24 24"><path d="M12 0C5.373 0 0 5.373 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 01.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/></svg></a></div>
</footer>
<script>
function toggleDoc(btn){var item=btn.parentElement;item.classList.toggle('open');btn.setAttribute('aria-expanded',item.classList.contains('open'));}
function buyProduct(productId){var btn=event.target;btn.disabled=true;btn.textContent='Processing...';fetch('/api/create-checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:productId})}).then(function(r){return r.json()}).then(function(data){if(data.url){window.location.href=data.url}else{alert('Something went wrong. Please try again.');btn.disabled=false;btn.textContent='Buy Now — {{ price }}';}}).catch(function(){alert('Something went wrong. Please try again.');btn.disabled=false;btn.textContent='Buy Now — {{ price }}';});}
(function(){var dds=document.querySelectorAll('.nav-dropdown');dds.forEach(function(dd){var btn=dd.querySelector('.nav-drop-btn');btn.addEventListener('click',function(e){e.stopPropagation();dds.forEach(function(o){if(o!==dd){o.classList.remove('open');o.querySelector('.nav-drop-btn').setAttribute('aria-expanded','false');}});dd.classList.toggle('open');btn.setAttribute('aria-expanded',dd.classList.contains('open'));});});document.addEventListener('click',function(){dds.forEach(function(dd){dd.classList.remove('open');dd.querySelector('.nav-drop-btn').setAttribute('aria-expanded','false');});});})();
</script>
</body></html>"""

@app.route("/contact")
def contact():
    return send_from_directory(".", "contact.html")

@app.route("/api/contact", methods=["POST"])
def contact_form():
    import smtplib
    from email.mime.text import MIMEText
    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    subject = data.get("subject", "general")
    message = data.get("message", "").strip()
    if not name or not email or not message:
        return jsonify({"error": "All fields are required."}), 400
    # Store in database for backup
    try:
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        db_execute(conn, f"""CREATE TABLE IF NOT EXISTS contact_messages (
            id {'SERIAL' if USE_POSTGRES else 'INTEGER'} PRIMARY KEY{'  AUTOINCREMENT' if not USE_POSTGRES else ''},
            name TEXT, email TEXT, subject TEXT, message TEXT, created_at TEXT
        )""")
        db_execute(conn, f"INSERT INTO contact_messages (name, email, subject, message, created_at) VALUES ({param},{param},{param},{param},{param})",
            (name, email, subject, message, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return jsonify({"ok": True})

@app.route("/robots.txt")
def robots_txt():
    return Response("""User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/

Sitemap: https://lumeway.co/sitemap.xml
""", mimetype="text/plain")

@app.route("/sitemap.xml")
def sitemap_xml():
    pages = [
        ("https://lumeway.co/", "weekly", "1.0"),
        ("https://lumeway.co/about", "monthly", "0.7"),
        ("https://lumeway.co/blog", "daily", "0.8"),
        ("https://lumeway.co/chat", "monthly", "0.9"),
        ("https://lumeway.co/job-loss", "weekly", "0.9"),
        ("https://lumeway.co/divorce", "weekly", "0.9"),
        ("https://lumeway.co/estate", "weekly", "0.9"),
        ("https://lumeway.co/relocation", "weekly", "0.9"),
        ("https://lumeway.co/disability", "weekly", "0.9"),
        ("https://lumeway.co/retirement", "weekly", "0.9"),
        ("https://lumeway.co/templates", "weekly", "0.8"),
        ("https://lumeway.co/faq", "monthly", "0.6"),
        ("https://lumeway.co/contact", "monthly", "0.6"),
        ("https://lumeway.co/emergency-kit", "monthly", "0.8"),
        ("https://lumeway.co/privacy", "monthly", "0.3"),
        ("https://lumeway.co/terms", "monthly", "0.3"),
    ]
    # Add blog posts dynamically
    blog_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog-posts")
    for f in globmod.glob(os.path.join(blog_dir, "*.html")) + globmod.glob(os.path.join(blog_dir, "*.md")):
        slug = os.path.splitext(os.path.basename(f))[0]
        pages.append((f"https://lumeway.co/blog/{slug}", "monthly", "0.7"))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, freq, priority in pages:
        xml += f"  <url><loc>{url}</loc><changefreq>{freq}</changefreq><priority>{priority}</priority></url>\n"
    xml += "</urlset>"
    return Response(xml, mimetype="application/xml")

BLOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog-posts")

def parse_html_post(filepath):
    """Parse a cowork-generated HTML blog post, extract content and metadata."""
    with open(filepath, "r") as f:
        raw = f.read()
    meta = {}
    slug = os.path.splitext(os.path.basename(filepath))[0]
    meta["slug"] = slug
    # Extract date from slug (e.g., 2026-03-25-first-30-days...)
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", slug)
    if date_match:
        meta["date"] = date_match.group(1)
    # Extract title from <h1>
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.DOTALL)
    if title_match:
        meta["title"] = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
    # Extract meta description
    desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', raw)
    if desc_match:
        meta["excerpt"] = desc_match.group(1)
    # Extract category from blog-category div or category-tag span
    cat_match = re.search(r'class="[^"]*blog-category[^"]*"[^>]*>(.*?)</div>', raw, re.DOTALL)
    if not cat_match:
        cat_match = re.search(r'class="[^"]*category-tag[^"]*"[^>]*>(.*?)</(?:span|div)>', raw, re.DOTALL)
    if cat_match:
        meta["category"] = re.sub(r"<[^>]+>", "", cat_match.group(1)).strip().title()
    # Extract blog-content div (the actual post body)
    content_match = re.search(r'<div class="blog-content">(.*?)</div>\s*</article>', raw, re.DOTALL)
    if content_match:
        meta["body_html"] = content_match.group(1).strip()
    else:
        # Fallback: grab everything between </nav> and <footer>
        fallback = re.search(r"</nav>(.*?)<footer>", raw, re.DOTALL)
        meta["body_html"] = fallback.group(1).strip() if fallback else ""
    return meta

def parse_md_post(filepath):
    """Parse a markdown blog post with frontmatter."""
    with open(filepath, "r") as f:
        content = f.read()
    meta = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip()
            content = parts[2].strip()
    slug = os.path.splitext(os.path.basename(filepath))[0]
    meta["slug"] = slug
    meta["body_html"] = markdown.markdown(content, extensions=["extra", "toc"])
    return meta

def get_all_posts():
    posts = []
    for f in globmod.glob(os.path.join(BLOG_DIR, "*.html")) + globmod.glob(os.path.join(BLOG_DIR, "*.md")):
        try:
            if f.endswith(".html"):
                posts.append(parse_html_post(f))
            else:
                posts.append(parse_md_post(f))
        except Exception:
            continue
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    return posts

@app.route("/blog")
def blog():
    posts = get_all_posts()
    if not posts:
        return send_from_directory(".", "blog.html")
    cards_html = ""
    for p in posts:
        cards_html += f'''<div class="blog-card">
          <a href="/blog/{p['slug']}" style="text-decoration:none;color:inherit;display:flex;flex-direction:column;height:100%">
            <span class="blog-tag">{p.get("category", "General")}</span>
            <h2 class="blog-card-title">{p.get("title", "Untitled")}</h2>
            <p class="blog-card-excerpt">{p.get("excerpt", "")}</p>
            <span class="blog-card-date" style="font-size:12px;color:#6E7D8A;margin-top:auto">{p.get("date", "")}</span>
          </a>
        </div>'''
    blog_html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog.html")
    with open(blog_html_path, "r") as f:
        html = f.read()
    html = html.replace('<div class="blog-grid reveal-stagger">', '<div class="blog-grid reveal-stagger">' + cards_html)
    return html

@app.route("/blog/<slug>")
def blog_post(slug):
    html_path = os.path.join(BLOG_DIR, f"{slug}.html")
    md_path = os.path.join(BLOG_DIR, f"{slug}.md")
    if os.path.exists(html_path):
        post = parse_html_post(html_path)
    elif os.path.exists(md_path):
        post = parse_md_post(md_path)
    else:
        return "Post not found", 404
    return render_template_string(BLOG_POST_TEMPLATE, post=post)

BLOG_POST_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-QHWJDRDR9R"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'G-QHWJDRDR9R');
  </script>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{{ post.get('title', 'Blog') }} — Lumeway Blog</title>
  <meta name="description" content="{{ post.get('excerpt', '') }}"/>
  <meta name="p:domain_verify" content="730a746e44038ebaf9f0330e062795d6"/>
  <link rel="canonical" href="https://lumeway.co/blog/{{ post.get('slug', '') }}"/>
  <meta property="og:type" content="article"/>
  <meta property="og:site_name" content="Lumeway"/>
  <meta property="og:title" content="{{ post.get('title', 'Blog') }} — Lumeway"/>
  <meta property="og:description" content="{{ post.get('excerpt', '') }}"/>
  <meta property="og:url" content="https://lumeway.co/blog/{{ post.get('slug', '') }}"/>
  <meta name="twitter:card" content="summary"/>
  <meta name="twitter:title" content="{{ post.get('title', 'Blog') }} — Lumeway"/>
  <meta name="twitter:description" content="{{ post.get('excerpt', '') }}"/>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "headline": "{{ post.get('title', '') }}",
    "description": "{{ post.get('excerpt', '') }}",
    "datePublished": "{{ post.get('date', '') }}",
    "author": {"@type": "Organization", "name": "Lumeway", "url": "https://lumeway.co"},
    "publisher": {"@type": "Organization", "name": "Lumeway", "url": "https://lumeway.co"},
    "mainEntityOfPage": "https://lumeway.co/blog/{{ post.get('slug', '') }}"
  }
  </script>
  <script type="application/ld+json">
  {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"Home","item":"https://lumeway.co/"},{"@type":"ListItem","position":2,"name":"Blog","item":"https://lumeway.co/blog"},{"@type":"ListItem","position":3,"name":"{{ post.get('title', '') }}","item":"https://lumeway.co/blog/{{ post.get('slug', '') }}"}]}
  </script>
  <link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet"/>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{--cream:#FAF7F2;--warm-white:#FDFCFA;--text:#2C3E50;--muted:#6B7B8D;--navy:#2C4A5E;--gold:#B8977E;--accent:#C4704E;--accent-light:#D4896C;--border:#E8E0D6}
    body{font-family:'Plus Jakarta Sans',sans-serif;background:var(--cream);color:var(--text);-webkit-font-smoothing:antialiased;line-height:1.7;font-size:17px;font-weight:300}
    nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:20px 48px;display:flex;align-items:center;justify-content:space-between;background:rgba(250,247,242,0.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
    .nav-logo{display:flex;align-items:center;gap:10px;text-decoration:none}
    .sun-icon{display:flex;align-items:center}
    .nav-logo-text{font-family:'Plus Jakarta Sans',sans-serif;font-size:18px;font-weight:600;color:var(--text);text-transform:uppercase;letter-spacing:0.08em}
    .nav-left{display:flex;align-items:center;gap:28px}
    .nav-right{display:flex;gap:12px;align-items:center}
    .btn-ghost{padding:8px 20px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text);font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;text-decoration:none;transition:all 0.2s}
    .btn-ghost:hover{background:var(--accent);color:white}
    .btn-primary{padding:8px 20px;border:none;border-radius:8px;background:var(--accent);color:white;font-family:'Plus Jakarta Sans',sans-serif;font-size:14px;text-decoration:none;transition:all 0.2s}
    .post-wrapper{padding:0 5%}
    article{max-width:720px;margin:0 auto;padding:120px 0 64px}
    .post-meta{margin-bottom:32px}
    .post-tag{display:inline-block;font-size:11px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:var(--gold);background:var(--warm-white);border:1px solid var(--border);padding:3px 10px;border-radius:100px;margin-bottom:16px}
    .post-title{font-family:'Libre Baskerville',serif;font-size:clamp(28px,4vw,42px);font-weight:400;line-height:1.2;letter-spacing:-0.02em;margin-bottom:12px}
    .post-date{font-size:13px;color:var(--muted)}
    .post-divider{width:60px;height:2px;background:var(--gold);margin-bottom:40px}
    .post-body{font-size:16px;line-height:1.85;font-weight:300;color:var(--text)}
    .post-body h2{font-family:'Libre Baskerville',serif;font-size:24px;font-weight:400;margin:48px 0 20px;color:var(--navy);line-height:1.3}
    .post-body h3{font-size:18px;font-weight:500;margin:28px 0 12px;color:var(--text)}
    .post-body p{margin-bottom:18px}
    .post-body ul,.post-body ol{margin:0 0 20px 24px}
    .post-body li{margin-bottom:8px;line-height:1.7}
    .post-body strong{font-weight:500}
    .post-body a{color:var(--accent);text-decoration:underline;text-decoration-color:var(--border);text-underline-offset:3px}
    .post-body a:hover{text-decoration-color:var(--accent)}
    .post-body .template-callout{background:var(--warm-white);border-left:3px solid var(--gold);padding:20px 24px;margin:28px 0;border-radius:0 8px 8px 0}
    .post-body .template-callout p{font-size:15px;color:var(--muted);margin-bottom:0}
    .post-body .cta-box{background:var(--warm-white);border:1px solid var(--border);border-radius:12px;padding:32px;margin:40px 0;text-align:center}
    .post-body .cta-box h3{font-family:'Libre Baskerville',serif;font-size:22px;font-weight:400;color:var(--navy);margin-bottom:12px}
    .post-body .cta-box p{font-size:15px;color:var(--muted);margin-bottom:20px}
    .post-body .cta-button{display:inline-block;font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:500;text-transform:uppercase;letter-spacing:1.5px;color:white;background:var(--accent);padding:14px 32px;border-radius:8px;text-decoration:none;transition:background 0.2s}
    .post-body .cta-button:hover{background:var(--accent-light);color:white}
    .post-body .disclaimer{font-size:13px;font-style:italic;color:var(--muted);border-top:1px solid var(--border);padding-top:32px;margin-top:48px;line-height:1.6}
    .post-back{display:inline-block;margin-top:48px;font-size:14px;color:var(--muted);text-decoration:none}
    .post-back:hover{color:var(--accent)}
    footer{padding:28px 48px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-top:64px}
    .footer-logo{height:80px;object-fit:contain}
    .footer-note{font-size:12px;color:var(--muted);font-weight:300}
    .footer-note a{color:var(--muted)}
    @media(max-width:768px){nav{padding:14px 20px}article{padding:85px 0 48px}footer{padding:20px;flex-direction:column;text-align:center}}
    @media(max-width:480px){nav{padding:12px 16px}.btn-ghost,.btn-primary{font-size:12px;padding:6px 14px}article{padding:75px 0 36px}}
  </style>
</head>
<body>
  <nav>
    <div class="nav-left">
      <a href="/" class="nav-logo">
        <span class="sun-icon" style="color:var(--accent)"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M2 12h3M19 12h3M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12"/></svg></span>
        <span class="nav-logo-text">Lumeway</span>
      </a>
      <a href="/features" style="font-size:14px;color:var(--muted);text-decoration:none;padding:6px 4px">Features</a>
    </div>
    <div class="nav-right">
      <a href="/chat" target="_blank" class="btn-ghost">Try it free</a>
      <a href="/templates" class="btn-primary">Shop</a>
    </div>
  </nav>
  <div class="post-wrapper">
  <article>
    <div class="post-meta">
      <span class="post-tag">{{ post.get('category', 'General') }}</span>
      <h1 class="post-title">{{ post.get('title', 'Untitled') }}</h1>
      <p class="post-date">{{ post.get('date', '') }}</p>
    </div>
    <div class="post-divider"></div>
    <div class="post-body">
      {{ post.get('body_html', '') | safe }}
    </div>
    {% set category_links = {
      'Job Loss': ('/job-loss', 'Job Loss & Income Crisis Guide'),
      'Job Loss Worksheet': ('/job-loss', 'Job Loss & Income Crisis Guide'),
      'Estate': ('/estate', 'Death & Estate Guide'),
      'Death': ('/estate', 'Death & Estate Guide'),
      'Divorce': ('/divorce', 'Divorce & Separation Guide'),
      'Relocation': ('/relocation', 'Moving & Relocation Guide'),
      'Moving': ('/relocation', 'Moving & Relocation Guide'),
      'Disability': ('/disability', 'Disability & Benefits Guide'),
      'Retirement': ('/retirement', 'Retirement Planning Guide')
    } %}
    {% set cat = post.get('category', '') %}
    {% if cat in category_links %}
    <div style="background:var(--warm-white);border:1px solid var(--border);border-radius:12px;padding:28px;margin-top:48px;text-align:center">
      <p style="font-family:'Libre Baskerville',serif;font-size:20px;color:var(--navy);margin-bottom:8px">Need a full step-by-step plan?</p>
      <p style="font-size:14px;color:var(--muted);margin-bottom:16px">Our {{ category_links[cat][1] }} walks you through timelines, deadlines, and resources.</p>
      <a href="{{ category_links[cat][0] }}" style="display:inline-block;padding:12px 28px;background:var(--accent);color:white;border-radius:8px;font-size:14px;text-decoration:none">View the guide</a>
    </div>
    {% endif %}
    <a href="/blog" class="post-back">&larr; Back to all posts</a>
  </article>
  </div>
  <footer>
    <img src="/static/logos/lockup-h-navy-cream-v2-transparent.png" alt="Lumeway" class="footer-logo">
    <p class="footer-note">Lumeway is a guidance tool, not a licensed professional. Always consult a qualified advisor.</p>
    <p class="footer-note"><a href="/about">About</a> &middot; <a href="/privacy">Privacy Policy</a></p>
    <div class="footer-social"><a href="https://www.pinterest.com/lumeway" rel="noopener" target="_blank" title="Pinterest"><svg viewBox="0 0 24 24"><path d="M12 0C5.373 0 0 5.373 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 01.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/></svg></a></div>
  </footer>
</body>
</html>"""

@app.route("/static/data/state-rules.json")
def state_rules():
    return send_from_directory("data", "state-rules.json")

# ── Auth routes ──

@app.route("/login")
def login_page():
    if get_current_user():
        return redirect("/dashboard")
    return send_from_directory(".", "login.html")

@app.route("/api/auth/send-code", methods=["POST"])
def auth_send_code():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    # Rate limit: max 5 codes per email per hour
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    cur = db_execute(conn, f"SELECT COUNT(*) FROM auth_codes WHERE email = {param} AND created_at > {param}", (email, one_hour_ago))
    count = cur.fetchone()[0]
    if count >= 5:
        conn.close()
        return jsonify({"error": "Too many attempts. Please try again later."}), 429

    code = str(random.randint(100000, 999999))
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    # Demo account: use fixed code, skip email
    if email == "demo@lumeway.co":
        code = "000000"
        db_execute(conn, f"INSERT INTO auth_codes (email, code, created_at, expires_at) VALUES ({param}, {param}, {param}, {param})", (email, code, now, expires))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "Demo account — use code 000000.", "demo": True, "demo_code": "000000"})

    db_execute(conn, f"INSERT INTO auth_codes (email, code, created_at, expires_at) VALUES ({param}, {param}, {param}, {param})", (email, code, now, expires))
    conn.commit()
    conn.close()

    if not send_auth_code(email, code):
        return jsonify({"error": "Failed to send code. Please try again."}), 500

    return jsonify({"ok": True, "message": "Code sent! Check your email."})

DEMO_EMAIL = "demo@lumeway.co"

@app.route("/api/auth/verify-code", methods=["POST"])
def auth_verify_code():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    claim_session_id = data.get("session_id")

    if not email or not code:
        return jsonify({"error": "Email and code are required."}), 400

    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()

    # Find valid unused code
    false_val = "FALSE" if USE_POSTGRES else "0"
    cur = db_execute(conn, f"SELECT id FROM auth_codes WHERE email = {param} AND code = {param} AND used = {false_val} AND expires_at > {param} ORDER BY created_at DESC LIMIT 1", (email, code, now))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Invalid or expired code. Please try again."}), 401

    # Mark code as used
    code_id = row[0]
    true_val = "TRUE" if USE_POSTGRES else "1"
    db_execute(conn, f"UPDATE auth_codes SET used = {true_val} WHERE id = {param}", (code_id,))

    # Find or create user
    cur = db_execute(conn, f"SELECT id, email, display_name, transition_type, us_state FROM users WHERE email = {param}", (email,))
    user_row = cur.fetchone()
    is_new = False
    if user_row:
        user_id = user_row[0]
        db_execute(conn, f"UPDATE users SET last_login_at = {param} WHERE id = {param}", (now, user_id))
    else:
        is_new = True
        db_execute(conn, f"INSERT INTO users (email, created_at, last_login_at) VALUES ({param}, {param}, {param})", (email, now, now))
        cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (email,))
        user_id = cur.fetchone()[0]

    # Demo account: full reset on every login so it feels like a fresh free user
    if email == DEMO_EMAIL and not is_new:
        # Clear all user data
        db_execute(conn, f"DELETE FROM community_replies WHERE post_id IN (SELECT id FROM community_posts WHERE user_id = {param})", (user_id,))
        db_execute(conn, f"DELETE FROM community_replies WHERE user_id = {param}", (user_id,))
        for table in ["community_posts", "checklist_items", "user_deadlines", "user_documents_needed", "user_goals", "user_notes", "chat_sessions"]:
            db_execute(conn, f"DELETE FROM {table} WHERE user_id = {param}", (user_id,))
        try:
            db_execute(conn, f"DELETE FROM user_files WHERE user_id = {param}", (user_id,))
        except Exception:
            pass
        try:
            db_execute(conn, f"DELETE FROM etsy_redemptions WHERE user_id = {param}", (user_id,))
        except Exception:
            pass
        try:
            db_execute(conn, f"DELETE FROM activity_log WHERE user_id = {param}", (user_id,))
        except Exception:
            pass
        # Reset user back to free tier with no transition selected
        db_execute(conn, f"UPDATE users SET tier = 'free', tier_transition = NULL, tier_expires_at = NULL, stripe_customer_id = NULL, active_transitions = '[]', transition_type = NULL, display_name = NULL, us_state = NULL WHERE id = {param}", (user_id,))
        is_new = True  # Force onboarding flow

    # Claim anonymous chat session if provided
    if claim_session_id:
        db_execute(conn, f"UPDATE chat_sessions SET user_id = {param} WHERE id = {param} AND user_id IS NULL", (user_id, claim_session_id))

    conn.commit()
    conn.close()

    # Set session cookie (for web)
    flask_session["user_id"] = user_id
    flask_session.permanent = True

    audit_log(user_id, "login", "user", str(user_id), email)

    # Build user object for response
    conn2 = get_db()
    cur2 = db_execute(conn2, f"SELECT id, email, display_name, transition_type, us_state FROM users WHERE id = {param}", (user_id,))
    u_row = cur2.fetchone()
    conn2.close()
    user_obj = None
    if u_row:
        user_obj = {"id": u_row[0], "email": u_row[1], "display_name": u_row[2], "transition_type": u_row[3], "us_state": u_row[4]}

    # Generate JWT tokens for mobile clients
    response_data = {"ok": True, "is_new": is_new, "user_id": user_id, "user": user_obj,
                     "needs_onboarding": is_new or (user_obj and not user_obj.get("transition_type"))}
    access_token = generate_jwt(user_id, JWT_ACCESS_EXPIRY)
    refresh_token = generate_jwt(user_id, JWT_REFRESH_EXPIRY)
    if access_token:
        response_data["token"] = access_token
        response_data["refresh_token"] = refresh_token

    return jsonify(response_data)

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    # If demo account, reset all data so it's fresh next login
    user = get_current_user()
    if user and user.get("email") == DEMO_EMAIL:
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        uid = user["id"]
        # Delete replies on demo user's posts first (foreign key)
        db_execute(conn, f"DELETE FROM community_replies WHERE post_id IN (SELECT id FROM community_posts WHERE user_id = {param})", (uid,))
        # Then delete demo user's own replies on other posts
        db_execute(conn, f"DELETE FROM community_replies WHERE user_id = {param}", (uid,))
        for table in ["community_posts", "checklist_items", "user_deadlines", "user_documents_needed", "user_goals", "user_notes", "chat_sessions"]:
            db_execute(conn, f"DELETE FROM {table} WHERE user_id = {param}", (uid,))
        # Also clear uploaded files
        try:
            db_execute(conn, f"DELETE FROM user_files WHERE user_id = {param}", (uid,))
        except Exception:
            pass
        conn.commit()
        conn.close()
    flask_session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/refresh", methods=["POST"])
def auth_refresh_token():
    """Exchange a refresh token for a new access token (mobile app)."""
    data = request.json or {}
    refresh = data.get("refresh_token", "")
    user_id = decode_jwt(refresh)
    if not user_id:
        return jsonify({"error": "Invalid or expired refresh token."}), 401
    new_access = generate_jwt(user_id, JWT_ACCESS_EXPIRY)
    new_refresh = generate_jwt(user_id, JWT_REFRESH_EXPIRY)
    return jsonify({"ok": True, "token": new_access, "refresh_token": new_refresh})

@app.route("/api/push/register", methods=["POST"])
def register_push_token():
    """Store a device push token for sending notifications."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    token = data.get("token", "").strip()
    platform = data.get("platform", "ios").strip()
    if not token:
        return jsonify({"error": "Token required"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    # Upsert: update existing token or insert new
    cur = db_execute(conn, f"SELECT id FROM push_tokens WHERE user_id = {param} AND token = {param}", (user["id"], token))
    if cur.fetchone():
        db_execute(conn, f"UPDATE push_tokens SET updated_at = {param} WHERE user_id = {param} AND token = {param}", (now, user["id"], token))
    else:
        db_execute(conn, f"INSERT INTO push_tokens (user_id, token, platform, created_at, updated_at) VALUES ({param},{param},{param},{param},{param})", (user["id"], token, platform, now, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# ── In-App Purchase verification ──

# Map App Store product IDs to transition categories
IAP_PRODUCT_MAP = {
    "co.lumeway.pass.estate": "estate",
    "co.lumeway.pass.divorce": "divorce",
    "co.lumeway.pass.jobloss": "job-loss",
    "co.lumeway.pass.disability": "disability",
    "co.lumeway.pass.relocation": "relocation",
    "co.lumeway.pass.retirement": "retirement",
    "co.lumeway.pass.addiction": "addiction",
    "co.lumeway.bundle.pick3": "__pick3__",
    "co.lumeway.bundle.all": "__all__",
}

@app.route("/api/iap/verify", methods=["POST"])
def verify_iap():
    """Verify an in-app purchase and grant access."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    product_id = data.get("product_id", "")
    transaction_id = data.get("transaction_id", "")

    if product_id not in IAP_PRODUCT_MAP:
        return jsonify({"error": "Unknown product"}), 400

    category = IAP_PRODUCT_MAP[product_id]
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()

    # Grant access based on product type
    active = user.get("active_transitions") or []
    if category == "__all__":
        # All transitions access
        active = list(VALID_CATEGORIES)
    elif category == "__pick3__":
        # Pick 3 — user chooses later, for now grant a flag
        pass  # handled client-side
    else:
        if category not in active:
            active.append(category)

    active_json = json.dumps(active)
    db_execute(conn, f"UPDATE users SET active_transitions = {param} WHERE id = {param}", (active_json, user["id"]))

    # Log the purchase
    db_execute(conn, f"INSERT INTO purchases (email, product_id, product_name, amount, purchased_at, download_token) VALUES ({param},{param},{param},{param},{param},{param})",
               (user["email"], product_id, product_id, 0, now, transaction_id))

    conn.commit()
    conn.close()

    audit_log(user["id"], "iap_purchase", "purchase", product_id, f"txn={transaction_id}")
    return jsonify({"ok": True, "active_transitions": active})

@app.route("/api/auth/me")
def auth_me():
    user = get_current_user()
    if not user:
        return jsonify({"logged_in": False})
    # Normalize active_transitions to flat list of strings for mobile app
    safe_user = dict(user)
    safe_user["active_transitions"] = [item["cat"] if isinstance(item, dict) else item for item in (user.get("active_transitions") or [])]
    return jsonify({"logged_in": True, "user": safe_user})

# ── Demo / test dashboard ──

@app.route("/demo")
def demo_dashboard():
    """One-click demo login — creates or reuses a demo account with full access and sample data."""
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()

    # Find or create demo user
    cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (DEMO_EMAIL,))
    row = cur.fetchone()
    if row:
        user_id = row[0]
        db_execute(conn, f"UPDATE users SET last_login_at = {param} WHERE id = {param}", (now, user_id))
    else:
        db_execute(conn, f"INSERT INTO users (email, display_name, created_at, last_login_at) VALUES ({param}, {param}, {param}, {param})", (DEMO_EMAIL, "Demo User", now, now))
        cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (DEMO_EMAIL,))
        user_id = cur.fetchone()[0]

    # Grant full access
    db_execute(conn, f"UPDATE users SET tier = 'all_transitions', active_transitions = {param} WHERE id = {param}",
               ('["estate","divorce","job-loss","relocation","disability","retirement"]', user_id))

    # Seed sample checklist if empty
    cur = db_execute(conn, f"SELECT COUNT(*) FROM checklist_items WHERE user_id = {param}", (user_id,))
    if cur.fetchone()[0] == 0:
        demo_items = DEFAULT_CHECKLISTS.get("job-loss", {})
        for phase, items in demo_items.items():
            for i, text in enumerate(items):
                # Mark first few items as completed for demo
                if USE_POSTGRES:
                    is_done = "TRUE" if i < 2 else "FALSE"
                else:
                    is_done = "1" if i < 2 else "0"
                db_execute(conn, f"INSERT INTO checklist_items (user_id, transition_type, phase, item_text, is_completed, sort_order) VALUES ({param},{param},{param},{param},{is_done},{param})",
                           (user_id, "job-loss", phase, text, i))

    # Seed a sample deadline if empty
    cur = db_execute(conn, f"SELECT COUNT(*) FROM user_deadlines WHERE user_id = {param}", (user_id,))
    if cur.fetchone()[0] == 0:
        from datetime import timedelta as td
        deadlines = [
            ("File for unemployment benefits", (datetime.now(timezone.utc) + td(days=3)).strftime("%Y-%m-%d"), "job-loss"),
            ("COBRA election deadline", (datetime.now(timezone.utc) + td(days=45)).strftime("%Y-%m-%d"), "job-loss"),
            ("Review severance agreement", (datetime.now(timezone.utc) + td(days=14)).strftime("%Y-%m-%d"), "job-loss"),
        ]
        for title, date, ttype in deadlines:
            db_execute(conn, f"INSERT INTO user_deadlines (user_id, title, deadline_date, transition_type, source, created_at) VALUES ({param},{param},{param},{param},'demo',{param})",
                       (user_id, title, date, ttype, now))

    conn.commit()
    conn.close()

    # Log them in
    flask_session["user_id"] = user_id
    flask_session.permanent = True
    return redirect("/dashboard")


@app.route("/demo/reset", methods=["POST"])
def demo_reset():
    """Reset the demo account — clears all data and re-seeds."""
    user = get_current_user()
    if not user or user.get("email") != DEMO_EMAIL:
        return jsonify({"error": "Not the demo account"}), 403
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    uid = user["id"]
    # Community cleanup (foreign key order matters)
    db_execute(conn, f"DELETE FROM community_replies WHERE post_id IN (SELECT id FROM community_posts WHERE user_id = {param})", (uid,))
    db_execute(conn, f"DELETE FROM community_replies WHERE user_id = {param}", (uid,))
    for table in ["community_posts", "checklist_items", "user_deadlines", "user_documents_needed", "user_goals", "user_notes", "chat_sessions"]:
        db_execute(conn, f"DELETE FROM {table} WHERE user_id = {param}", (uid,))
    try:
        db_execute(conn, f"DELETE FROM user_files WHERE user_id = {param}", (uid,))
    except Exception:
        pass
    conn.commit()
    conn.close()
    return redirect("/demo")


# ── Dashboard routes ──


@app.route("/api/account/settings", methods=["POST"])
def update_account_settings():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    display_name = data.get("display_name", "").strip()[:100]
    us_state = data.get("us_state", "").strip()[:5]
    transition_type = data.get("transition_type", "").strip().lower()[:30]
    community_icon = data.get("community_icon", "").strip()[:10]
    community_icon_bg = data.get("community_icon_bg", "").strip()[:10]
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    if transition_type and transition_type in VALID_CATEGORIES:
        db_execute(conn, f"UPDATE users SET display_name = {param}, us_state = {param}, transition_type = {param}, community_icon = {param}, community_icon_bg = {param} WHERE id = {param}",
                   (display_name or None, us_state or None, transition_type, community_icon or None, community_icon_bg or None, user["id"]))
    else:
        db_execute(conn, f"UPDATE users SET display_name = {param}, us_state = {param}, community_icon = {param}, community_icon_bg = {param} WHERE id = {param}",
                   (display_name or None, us_state or None, community_icon or None, community_icon_bg or None, user["id"]))
    conn.commit()
    conn.close()
    audit_log(user["id"], "settings_update", "user", str(user["id"]), f"name={display_name}, state={us_state}, transition={transition_type}, icon={community_icon}")
    return jsonify({"ok": True})

@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory(".", "manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def serve_sw():
    return send_from_directory(".", "sw.js", mimetype="application/javascript")

@app.route("/dashboard")
def dashboard_page():
    if not get_current_user():
        return redirect("/login")
    return send_from_directory(".", "dashboard.html")

@app.route("/api/dashboard/data")
def dashboard_data():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"

    # Recent chat sessions
    cur = db_execute(conn, f"""SELECT id, started_at, ended_at, transition_category, user_state
        FROM chat_sessions WHERE user_id = {param} ORDER BY started_at DESC LIMIT 10""", (user["id"],))
    sessions = []
    for row in cur.fetchall():
        sid = row[0]
        # Get first user message as preview
        msg_cur = db_execute(conn, f"SELECT content FROM chat_messages WHERE session_id = {param} AND role = 'user' ORDER BY created_at LIMIT 1", (sid,))
        msg_row = msg_cur.fetchone()
        preview = msg_row[0][:100] + "..." if msg_row and len(msg_row[0]) > 100 else (msg_row[0] if msg_row else "")
        sessions.append({
            "id": row[0], "started_at": row[1], "ended_at": row[2],
            "transition_category": row[3], "user_state": row[4], "preview": preview
        })

    # Checklist stats
    cur = db_execute(conn, f"SELECT COUNT(*) FROM checklist_items WHERE user_id = {param}", (user["id"],))
    total_items = cur.fetchone()[0]
    true_val = "TRUE" if USE_POSTGRES else "1"
    cur = db_execute(conn, f"SELECT COUNT(*) FROM checklist_items WHERE user_id = {param} AND is_completed = {true_val}", (user["id"],))
    completed_items = cur.fetchone()[0]

    # Purchases
    cur = db_execute(conn, f"SELECT product_id, product_name, purchased_at, download_token FROM purchases WHERE email = {param} ORDER BY purchased_at DESC", (user["email"],))
    purchases = [{"product_id": r[0], "product_name": r[1], "purchased_at": r[2], "download_token": r[3]} for r in cur.fetchall()]

    # Goals
    cur = db_execute(conn, f"SELECT id, title, timeframe, target_date, is_completed, created_at FROM user_goals WHERE user_id = {param} ORDER BY target_date", (user["id"],))
    goals = [{"id": r[0], "title": r[1], "timeframe": r[2], "target_date": r[3], "is_completed": bool(r[4]), "created_at": r[5]} for r in cur.fetchall()]

    # Deadlines
    cur = db_execute(conn, f"SELECT id, transition_type, title, deadline_date, note, is_completed, source FROM user_deadlines WHERE user_id = {param} ORDER BY deadline_date", (user["id"],))
    deadlines = [{"id": r[0], "transition_type": r[1], "title": r[2], "deadline_date": r[3], "note": r[4], "is_completed": bool(r[5]), "source": r[6]} for r in cur.fetchall()]

    # Documents needed
    cur = db_execute(conn, f"SELECT id, transition_type, document_name, description, is_gathered FROM user_documents_needed WHERE user_id = {param} ORDER BY id", (user["id"],))
    documents_needed = [{"id": r[0], "transition_type": r[1], "document_name": r[2], "description": r[3], "is_gathered": bool(r[4])} for r in cur.fetchall()]

    # Notes
    cur = db_execute(conn, f"SELECT id, content, created_at, updated_at FROM user_notes WHERE user_id = {param} ORDER BY created_at DESC", (user["id"],))
    notes = [{"id": r[0], "content": r[1], "created_at": r[2], "updated_at": r[3]} for r in cur.fetchall()]

    # Full checklist items (for mobile app)
    cur = db_execute(conn, f"SELECT id, transition_type, phase, item_text, is_completed, completed_at, sort_order FROM checklist_items WHERE user_id = {param} ORDER BY sort_order, id", (user["id"],))
    checklist_items = [{"id": r[0], "transition_type": r[1], "phase": r[2], "task_text": r[3], "completed": bool(r[4]), "completed_at": r[5], "sort_order": r[6]} for r in cur.fetchall()]

    # Compute days_remaining for deadlines
    now_dt = datetime.now(timezone.utc)
    for d in deadlines:
        if d.get("deadline_date"):
            try:
                due = datetime.fromisoformat(d["deadline_date"].replace("Z", "+00:00"))
                d["days_remaining"] = max(0, (due - now_dt).days)
            except (ValueError, TypeError):
                d["days_remaining"] = None

    # Fetch onboarding_source
    onboarding_source = None
    try:
        conn_obs = get_db()
        cur_obs = db_execute(conn_obs, f"SELECT onboarding_source FROM users WHERE id = {param}", (user["id"],))
        obs_row = cur_obs.fetchone()
        if obs_row:
            onboarding_source = obs_row[0]
        conn_obs.close()
    except Exception:
        pass
    # Fallback: check if user has redeemed a gift code
    if not onboarding_source:
        try:
            conn_gc = get_db()
            cur_gc = db_execute(conn_gc, f"SELECT id FROM gift_codes WHERE redeemed_by = {param} LIMIT 1", (user["id"],))
            if cur_gc.fetchone():
                onboarding_source = "gift"
            conn_gc.close()
        except Exception:
            pass

    conn.close()
    # Sanitize user dict for JSON response — normalize active_transitions to string list
    user_response = dict(user)
    user_response["active_transitions"] = [item["cat"] if isinstance(item, dict) else item for item in (user.get("active_transitions") or [])]
    return jsonify({
        "user": user_response,
        "sessions": sessions,
        "checklist": {"total": total_items, "completed": completed_items, "items": checklist_items},
        "purchases": purchases,
        "goals": goals,
        "deadlines": deadlines,
        "documents_needed": documents_needed,
        "notes": notes,
        "effective_tier": get_effective_tier(user),
        "category_access": get_user_categories(user),
        "credit_cents": user.get("credit_cents", 0),
        "active_transitions": [item["cat"] if isinstance(item, dict) else item for item in (user.get("active_transitions") or [])],
        "is_admin": user.get("email") in ["hello@lumeway.co", "lumeway.co@gmail.com"],
        "onboarding_source": onboarding_source,
    })

    # Subscription management removed — all purchases are one-time

@app.route("/api/dashboard/history/<session_id>")
def dashboard_history_detail(session_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Verify session belongs to user
    cur = db_execute(conn, f"SELECT id FROM chat_sessions WHERE id = {param} AND user_id = {param}", (session_id, user["id"]))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Session not found"}), 404
    cur = db_execute(conn, f"SELECT role, content, created_at FROM chat_messages WHERE session_id = {param} ORDER BY created_at", (session_id,))
    messages = [{"role": r[0], "content": r[1], "created_at": r[2]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"messages": messages})

@app.route("/api/chat/sessions")
def chat_sessions_list():
    """Return user's chat sessions for the mobile app chat history screen."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"""SELECT id, started_at, ended_at, transition_category
        FROM chat_sessions WHERE user_id = {param} ORDER BY started_at DESC LIMIT 50""", (user["id"],))
    sessions = []
    for row in cur.fetchall():
        sid = row[0]
        msg_cur = db_execute(conn, f"SELECT content FROM chat_messages WHERE session_id = {param} AND role = 'user' ORDER BY created_at LIMIT 1", (sid,))
        msg_row = msg_cur.fetchone()
        preview = msg_row[0][:100] + "..." if msg_row and len(msg_row[0]) > 100 else (msg_row[0] if msg_row else "")
        sessions.append({
            "id": row[0], "started_at": row[1], "ended_at": row[2],
            "transition_category": row[3], "preview": preview
        })
    conn.close()
    return jsonify({"sessions": sessions})

# ── Community Forum API ──

COMMUNITY_CATEGORIES = [
    {"id": "general", "label": "General"},
    {"id": "emotional-support", "label": "Emotional Support"},
    {"id": "legal-questions", "label": "Legal Questions"},
    {"id": "financial", "label": "Financial"},
    {"id": "success-stories", "label": "Success Stories"},
    {"id": "ask-cara", "label": "Ask Cara"},
]

@app.route("/api/community/posts", methods=["GET"])
def community_list_posts():
    """List community posts. All logged-in users can read."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    category = request.args.get("category", "")
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    offset = (page - 1) * per_page

    # Build query
    where = "WHERE p.is_hidden = 0"
    params = []
    if category:
        where += f" AND p.category = {param}"
        params.append(category)
    transition = request.args.get("transition", "")
    if transition:
        where += f" AND p.transition_category = {param}"
        params.append(transition)

    # Count total
    cur = db_execute(conn, f"SELECT COUNT(*) FROM community_posts p {where}", tuple(params))
    total = cur.fetchone()[0]

    # Fetch posts with reply counts
    cur = db_execute(conn, f"""
        SELECT p.id, p.user_id, p.display_name, p.category, p.title, p.body,
               p.is_pinned, p.created_at, p.updated_at,
               (SELECT COUNT(*) FROM community_replies r WHERE r.post_id = p.id AND r.is_hidden = 0) as reply_count,
               p.transition_category,
               (SELECT COUNT(*) FROM community_likes l WHERE l.post_id = p.id AND l.reply_id IS NULL) as like_count,
               p.icon
        FROM community_posts p {where}
        ORDER BY p.is_pinned DESC, p.created_at DESC
        LIMIT {param} OFFSET {param}
    """, tuple(params + [per_page, offset]))
    posts = []
    for r in cur.fetchall():
        posts.append({
            "id": r[0], "user_id": r[1], "display_name": r[2], "category": r[3],
            "title": r[4], "body": r[5], "is_pinned": bool(r[6]),
            "created_at": r[7], "updated_at": r[8], "reply_count": r[9],
            "transition_category": r[10], "like_count": r[11],
            "icon": r[12] or "😊",
            "is_author": r[1] == user["id"]
        })
    conn.close()
    transition_labels = [{"id": k, "label": v} for k, v in CATEGORY_LABELS.items()]
    return jsonify({"posts": posts, "total": total, "page": page, "per_page": per_page, "categories": COMMUNITY_CATEGORIES, "transitions": transition_labels})


@app.route("/api/community/posts", methods=["POST"])
def community_create_post():
    """Create a new community post. Requires paid tier."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    tier = get_effective_tier(user)
    if tier == "free":
        return jsonify({"error": "Upgrade your plan to post in the community."}), 403
    data = request.get_json()
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    category = data.get("category", "general")
    transition_category = (data.get("transition_category") or "").strip() or None
    display_name = (data.get("display_name") or "").strip()
    icon = (data.get("icon") or "😊").strip()
    if not title or not body:
        return jsonify({"error": "Title and body are required."}), 400
    if len(title) > 200:
        return jsonify({"error": "Title is too long (max 200 characters)."}), 400
    if len(body) > 5000:
        return jsonify({"error": "Post is too long (max 5000 characters)."}), 400
    if not display_name:
        display_name = user.get("display_name") or "Anonymous"
    # Validate category
    valid_cats = [c["id"] for c in COMMUNITY_CATEGORIES]
    if category not in valid_cats:
        category = "general"
    # Validate transition category
    valid_transitions = list(CATEGORY_LABELS.keys())
    if transition_category and transition_category not in valid_transitions:
        transition_category = None
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.utcnow().isoformat()
    db_execute(conn, f"""INSERT INTO community_posts (user_id, display_name, category, transition_category, title, body, icon, created_at)
        VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param})""",
        (user["id"], display_name, category, transition_category, title, body, icon, now))
    conn.commit()
    conn.close()
    # Notify admin of new post
    try:
        send_community_notification("post", display_name, title, body, 0)
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/community/posts/<int:post_id>", methods=["GET"])
def community_get_post(post_id):
    """Get a single post with its replies."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"""SELECT id, user_id, display_name, category, title, body, is_pinned, created_at, updated_at, transition_category, icon
        FROM community_posts WHERE id = {param} AND is_hidden = 0""", (post_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Post not found"}), 404
    post = {
        "id": row[0], "user_id": row[1], "display_name": row[2], "category": row[3],
        "title": row[4], "body": row[5], "is_pinned": bool(row[6]),
        "created_at": row[7], "updated_at": row[8], "transition_category": row[9],
        "icon": row[10] or "😊",
        "is_author": row[1] == user["id"]
    }
    # Get post like count + whether current user liked it
    cur = db_execute(conn, f"SELECT COUNT(*) FROM community_likes WHERE post_id = {param} AND reply_id IS NULL", (post_id,))
    post["like_count"] = cur.fetchone()[0]
    cur = db_execute(conn, f"SELECT COUNT(*) FROM community_likes WHERE post_id = {param} AND reply_id IS NULL AND user_id = {param}", (post_id, user["id"]))
    post["user_liked"] = cur.fetchone()[0] > 0

    # Get replies
    cur = db_execute(conn, f"""SELECT id, user_id, display_name, body, created_at, parent_reply_id, icon
        FROM community_replies WHERE post_id = {param} AND is_hidden = 0 ORDER BY created_at""", (post_id,))
    replies = []
    for r in cur.fetchall():
        rid = r[0]
        # Like counts for this reply
        cur2 = db_execute(conn, f"SELECT COUNT(*) FROM community_likes WHERE reply_id = {param}", (rid,))
        rlike_count = cur2.fetchone()[0]
        cur2 = db_execute(conn, f"SELECT COUNT(*) FROM community_likes WHERE reply_id = {param} AND user_id = {param}", (rid, user["id"]))
        ruser_liked = cur2.fetchone()[0] > 0
        replies.append({
            "id": rid, "user_id": r[1], "display_name": r[2], "body": r[3],
            "created_at": r[4], "parent_reply_id": r[5],
            "icon": r[6] or "😊",
            "is_author": r[1] == user["id"],
            "like_count": rlike_count, "user_liked": ruser_liked
        })
    conn.close()
    return jsonify({"post": post, "replies": replies})


@app.route("/api/community/posts/<int:post_id>/replies", methods=["POST"])
def community_create_reply(post_id):
    """Reply to a community post. Requires paid tier."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    tier = get_effective_tier(user)
    if tier == "free":
        return jsonify({"error": "Upgrade your plan to reply in the community."}), 403
    data = request.get_json()
    body = (data.get("body") or "").strip()
    display_name = (data.get("display_name") or "").strip()
    icon = (data.get("icon") or "😊").strip()
    parent_reply_id = data.get("parent_reply_id")  # For threaded replies
    if not body:
        return jsonify({"error": "Reply cannot be empty."}), 400
    if len(body) > 3000:
        return jsonify({"error": "Reply is too long (max 3000 characters)."}), 400
    if not display_name:
        display_name = user.get("display_name") or "Anonymous"
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Verify post exists and get title for notification
    cur = db_execute(conn, f"SELECT id, title FROM community_posts WHERE id = {param} AND is_hidden = 0", (post_id,))
    post_row = cur.fetchone()
    if not post_row:
        conn.close()
        return jsonify({"error": "Post not found"}), 404
    post_title = post_row[1]
    now = datetime.utcnow().isoformat()
    db_execute(conn, f"""INSERT INTO community_replies (post_id, parent_reply_id, user_id, display_name, body, icon, created_at)
        VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param})""",
        (post_id, parent_reply_id, user["id"], display_name, body, icon, now))
    conn.commit()
    conn.close()
    # Notify admin of new reply
    try:
        send_community_notification("reply", display_name, post_title, body, post_id)
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/community/report", methods=["POST"])
def community_report():
    """Report a post or reply for moderation."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    post_id = data.get("post_id")
    reply_id = data.get("reply_id")
    reason = (data.get("reason") or "").strip()
    if not post_id and not reply_id:
        return jsonify({"error": "Must specify post_id or reply_id"}), 400
    if not reason:
        return jsonify({"error": "Please provide a reason for reporting."}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.utcnow().isoformat()
    db_execute(conn, f"""INSERT INTO community_reports (reporter_user_id, post_id, reply_id, reason, created_at)
        VALUES ({param}, {param}, {param}, {param}, {param})""",
        (user["id"], post_id, reply_id, reason, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Thank you for reporting. We'll review this shortly."})


@app.route("/api/community/like", methods=["POST"])
def community_like():
    """Like or unlike a post or reply."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    post_id = data.get("post_id")
    reply_id = data.get("reply_id")
    if not post_id and not reply_id:
        return jsonify({"error": "Must specify post_id or reply_id"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Check if already liked
    if reply_id:
        cur = db_execute(conn, f"SELECT id FROM community_likes WHERE user_id = {param} AND reply_id = {param}", (user["id"], reply_id))
    else:
        cur = db_execute(conn, f"SELECT id FROM community_likes WHERE user_id = {param} AND post_id = {param} AND reply_id IS NULL", (user["id"], post_id))
    existing = cur.fetchone()
    if existing:
        # Unlike
        db_execute(conn, f"DELETE FROM community_likes WHERE id = {param}", (existing[0],))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "liked": False})
    else:
        # Like
        now = datetime.utcnow().isoformat()
        try:
            db_execute(conn, f"""INSERT INTO community_likes (user_id, post_id, reply_id, created_at)
                VALUES ({param}, {param}, {param}, {param})""",
                (user["id"], post_id, reply_id, now))
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()
        return jsonify({"ok": True, "liked": True})


@app.route("/api/community/posts/<int:post_id>", methods=["DELETE"])
def community_delete_post(post_id):
    """Delete (hide) a post. Author or admin only."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT user_id FROM community_posts WHERE id = {param}", (post_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Post not found"}), 404
    # Allow author or admin (Carol)
    is_admin = user.get("email") in ["hello@lumeway.co", "lumeway.co@gmail.com"]
    if row[0] != user["id"] and not is_admin:
        conn.close()
        return jsonify({"error": "Not authorized"}), 403
    db_execute(conn, f"UPDATE community_posts SET is_hidden = 1 WHERE id = {param}", (post_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/community/replies/<int:reply_id>", methods=["DELETE"])
def community_delete_reply(reply_id):
    """Delete (hide) a reply. Author or admin only."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT user_id FROM community_replies WHERE id = {param}", (reply_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Reply not found"}), 404
    is_admin = user.get("email") in ["hello@lumeway.co", "lumeway.co@gmail.com"]
    if row[0] != user["id"] and not is_admin:
        conn.close()
        return jsonify({"error": "Not authorized"}), 403
    db_execute(conn, f"UPDATE community_replies SET is_hidden = 1 WHERE id = {param}", (reply_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/community/generate-reply", methods=["POST"])
def community_generate_reply():
    """Generate a reply using Claude. Admin only."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    is_admin = user.get("email") in ["hello@lumeway.co", "lumeway.co@gmail.com"]
    if not is_admin:
        return jsonify({"error": "Not authorized"}), 403
    data = request.get_json()
    post_id = data.get("post_id")
    reply_id = data.get("reply_id")  # If replying to a specific reply
    if not post_id:
        return jsonify({"error": "post_id required"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Get the post
    cur = db_execute(conn, f"SELECT title, body, category, transition_category FROM community_posts WHERE id = {param}", (post_id,))
    post_row = cur.fetchone()
    if not post_row:
        conn.close()
        return jsonify({"error": "Post not found"}), 404
    # Get all replies for context
    cur = db_execute(conn, f"SELECT display_name, body FROM community_replies WHERE post_id = {param} AND is_hidden = 0 ORDER BY created_at", (post_id,))
    replies = [{"name": r[0], "body": r[1]} for r in cur.fetchall()]
    conn.close()
    # Build context for Claude
    context = f"Post title: {post_row[0]}\nPost body: {post_row[1]}"
    if post_row[2]:
        context += f"\nCategory: {post_row[2]}"
    if post_row[3]:
        trans_label = CATEGORY_LABELS.get(post_row[3], post_row[3])
        context += f"\nLife transition: {trans_label}"
    if replies:
        context += "\n\nExisting replies:"
        for r in replies:
            context += f"\n{r['name']}: {r['body']}"
    if reply_id:
        # Find the specific reply being responded to
        for r in replies:
            pass  # Context already includes all replies
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            system="""You are Cara, founder of Lumeway — a platform helping people through major life transitions (divorce, job loss, estate, disability, relocation, retirement).

TONE: You sound like a knowledgeable friend who's helped many people through this before. Warm but direct. Get to the point. No fluff, no filler, no corporate speak. Never use exclamation points.

STYLE:
- Keep it short: 2-3 brief paragraphs max. Favor short sentences and bullet points.
- Lead with validation — acknowledge what they're going through in one sentence, then move to practical help.
- Give clear, actionable suggestions. "Here's what I'd do" or "A good first step would be."
- Cite specific resources when relevant: government sites (ssa.gov, healthcare.gov, unemployment offices), legal aid (lawhelp.org, americanbar.org), hotlines, or well-known nonprofits.
- If it's a legal, medical, or financial question, still be helpful with general process info, then say something like "A family law attorney in your state can give you the specifics" — don't just deflect.
- Don't repeat what the person already said back to them.
- Don't start with "Hi" or "Hey there" — just jump in naturally.
- Never say "I understand how you feel" or "That must be so hard" as standalone sentences. Weave empathy into practical guidance instead.""",
            messages=[{"role": "user", "content": f"Write a community forum reply as Cara. Be concise, friendly, and practical. Include specific resources or next steps where possible.\n\n{context}"}]
        )
        generated = response.content[0].text
        return jsonify({"ok": True, "reply": generated})
    except Exception as e:
        print(f"[community] Claude generate error: {e}")
        return jsonify({"error": "Could not generate reply. Please try again."}), 500


@app.route("/api/community/seed", methods=["POST"])
def community_seed():
    """Seed starter conversations. Admin only."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    is_admin = user.get("email") in ["hello@lumeway.co", "lumeway.co@gmail.com"]
    if not is_admin:
        return jsonify({"error": "Not authorized"}), 403
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Check if any posts exist already
    cur = db_execute(conn, "SELECT COUNT(*) FROM community_posts")
    if cur.fetchone()[0] > 0:
        conn.close()
        return jsonify({"ok": True, "message": "Posts already exist, skipping seed."})
    now = datetime.utcnow().isoformat()
    seeds = [
        {"name": "Cara", "icon": "✨", "cat": "general", "trans": None, "title": "Welcome to the Lumeway community",
         "body": "Hey, so glad you are here.\n\nI built Lumeway because when I was going through my own life transition, I kept wishing someone would just tell me what to do next. Not in a preachy way, just like a friend who had been through it and could walk me through the steps.\n\nThat is what this community is for. Whether you are dealing with a divorce, a job loss, an estate, or something else entirely — you are not alone and there are people here who genuinely get it.\n\nNo question is too small, no vent is too messy. Jump in whenever you are ready.", "pin": 1},
        {"name": "Sarah", "icon": "🌸", "cat": "emotional-support", "trans": "divorce", "title": "How do you handle the loneliness?",
         "body": "I am about three months into my separation and the evenings are the hardest. The house feels so quiet. I know it gets better but some days it is really hard to believe that.\n\nAnyone else going through this? What has helped you?", "pin": 0},
        {"name": "James", "icon": "🌊", "cat": "financial", "trans": "job-loss", "title": "Negotiating severance - what I wish I knew",
         "body": "Just went through a layoff and wanted to share something I learned the hard way. Your initial severance offer is almost always negotiable. I asked for an extra two weeks and they said yes immediately.\n\nThings worth asking about: extended health insurance coverage, outplacement services, a neutral reference letter, and keeping your laptop.\n\nHas anyone else had luck negotiating? Would love to hear what worked for you.", "pin": 0},
        {"name": "Maria", "icon": "🌿", "cat": "legal-questions", "trans": "estate", "title": "Probate timeline - how long did yours take?",
         "body": "My mom passed away two months ago and the attorney said probate could take 6 to 12 months. That feels like forever when you are trying to handle everything.\n\nHow long did the process take for others? Any tips for keeping things moving?", "pin": 0},
        {"name": "David", "icon": "🎯", "cat": "success-stories", "trans": "job-loss", "title": "Landed a new role after 4 months",
         "body": "Just wanted to share some hope for anyone in the thick of a job search. I was laid off in December and it was honestly one of the lowest points of my life. But I just accepted an offer that is actually a better fit than my old job.\n\nWhat helped me most was having a system. The checklist on here kept me from spiraling and just taking it one task at a time made a huge difference.\n\nHang in there. It does get better.", "pin": 0},
        {"name": "Anonymous", "icon": "🦋", "cat": "ask-cara", "trans": "divorce", "title": "Do I need a lawyer if we agree on everything?",
         "body": "My spouse and I are splitting amicably. We have already agreed on how to divide everything and we do not have kids. Do we still need to hire lawyers or can we just file the paperwork ourselves?\n\nTrying to keep costs down but also do not want to make a mistake.", "pin": 0},
    ]
    for s in seeds:
        db_execute(conn, f"""INSERT INTO community_posts (user_id, display_name, category, transition_category, title, body, is_pinned, icon, created_at)
            VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param})""",
            (user["id"], s["name"], s["cat"], s["trans"], s["title"], s["body"], s["pin"], s["icon"], now))
    conn.commit()
    # Get seed post IDs by title
    seed_post_ids = []
    for s in seeds:
        cur = db_execute(conn, f"SELECT id FROM community_posts WHERE title = {param} ORDER BY id DESC LIMIT 1", (s["title"],))
        row = cur.fetchone()
        seed_post_ids.append(row[0] if row else None)
    seed_replies = {
        0: [
            {"name": "Sarah", "body": "This is exactly what I needed. Just knowing other people are going through the same thing makes such a difference."},
            {"name": "James", "body": "Really glad this exists. Sometimes you just need to talk to people who get it."},
            {"name": "Cara", "body": "So happy you are both here. Seriously, do not be shy about posting. Even if it is just to vent. That is what this space is for."},
        ],
        1: [
            {"name": "Cara", "body": "Three months in is still so early, so please be gentle with yourself. The quiet evenings are the worst part for a lot of people.\n\nA few things that have helped others: a small after-dinner routine (even just a walk or a podcast), keeping a text thread going with a friend, or picking up one low-effort hobby that gets you out of your head. You do not have to fill the silence with anything productive. Just something that is yours."},
            {"name": "David", "body": "I went through something similar after my divorce. What helped me was finding one thing to look forward to each evening, even something small. A show, a call with a friend, cooking something new. It does get easier."},
            {"name": "Maria", "body": "Sending you a hug. The evenings were the hardest for me too. I started journaling before bed and it honestly helped more than I expected."},
        ],
        2: [
            {"name": "Cara", "body": "This is such good advice. A lot of people do not realize severance is negotiable because they are in shock when it happens.\n\nOne thing to add: if your company offered a severance agreement, you usually have 21 days to review it (45 days if you are over 40 — that is federal law). So do not feel pressured to sign on the spot. Use that time to negotiate or have an employment attorney look it over."},
            {"name": "Sarah", "body": "I wish I had known this. I signed mine the same day because I was so overwhelmed. Great share."},
        ],
        3: [
            {"name": "Cara", "body": "6 to 12 months is pretty standard, but it really depends on the state and how complex the estate is. A few things that can speed things up:\n\n- Stay on top of deadlines your attorney gives you. A lot of delays happen because paperwork sits.\n- Get multiple copies of the death certificate early (you will need more than you think).\n- If there are no disputes among heirs, things tend to move faster.\n\nAlso worth asking your attorney about small estate shortcuts — some states let you skip formal probate if the estate is under a certain value."},
            {"name": "James", "body": "My family went through probate last year. Took about 8 months in our case. The biggest thing that helped was having one person be the point of contact for the attorney so nothing fell through the cracks."},
        ],
        4: [
            {"name": "Cara", "body": "Love hearing this. And you are so right about having a system. When everything feels out of control, just having a list of what to do next makes a huge difference. Congrats on the new role."},
            {"name": "Sarah", "body": "This gives me so much hope. Thank you for sharing."},
            {"name": "Maria", "body": "Congrats. Four months is tough but you made it through. Inspiring."},
        ],
        5: [
            {"name": "Cara", "body": "So this is one of those situations where a little money upfront can save you a lot of headaches later. Even if you agree on everything, there are things you might not think of — like how retirement accounts get divided (that needs a special court order called a QDRO), tax filing status for the year, and whether your state requires specific language in the agreement.\n\nYou probably do not need full representation. A lot of family law attorneys offer a one-time document review for a flat fee. It is worth it just for the peace of mind.\n\nCheck out your state bar association or lawhelp.org for lower-cost options."},
            {"name": "David", "body": "We did ours without lawyers and regretted it later when we realized we missed some retirement account stuff. Definitely get at least a consultation."},
        ],
    }
    seed_icons = {"Cara": "✨", "Sarah": "🌸", "James": "🌊", "Maria": "🌿", "David": "🎯", "Anonymous": "🦋"}
    for idx, reply_list in seed_replies.items():
        pid = seed_post_ids[idx] if idx < len(seed_post_ids) else None
        if pid:
            for rpl in reply_list:
                rpl_icon = seed_icons.get(rpl["name"], "😊")
                db_execute(conn, f"""INSERT INTO community_replies (post_id, user_id, display_name, body, icon, created_at)
                    VALUES ({param}, {param}, {param}, {param}, {param}, {param})""",
                    (pid, user["id"], rpl["name"], rpl["body"], rpl_icon, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Seeded 6 conversations with replies."})


@app.route("/api/community/posts/<int:post_id>/pin", methods=["POST"])
def community_pin_post(post_id):
    """Pin/unpin a post. Admin only."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    is_admin = user.get("email") in ["hello@lumeway.co", "lumeway.co@gmail.com"]
    if not is_admin:
        return jsonify({"error": "Not authorized"}), 403
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT is_pinned FROM community_posts WHERE id = {param}", (post_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Post not found"}), 404
    new_val = 0 if row[0] else 1
    db_execute(conn, f"UPDATE community_posts SET is_pinned = {param} WHERE id = {param}", (new_val, post_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "is_pinned": bool(new_val)})


# ── Help Resources (professional referrals per transition) ──

HELP_RESOURCES = {
    "estate": [
        {"name": "American Bar Association", "url": "https://www.americanbar.org", "desc": "Find an estate attorney in your area"},
        {"name": "LawHelp.org", "url": "https://www.lawhelp.org", "desc": "Free legal aid for low-income individuals"},
        {"name": "National Academy of Elder Law Attorneys", "url": "https://www.naela.org", "desc": "Attorneys specializing in elder law and estate planning"},
    ],
    "divorce": [
        {"name": "ABA Family Law Section", "url": "https://www.americanbar.org/groups/family_law", "desc": "Find a family law attorney"},
        {"name": "WomensLaw.org", "url": "https://www.womenslaw.org", "desc": "Legal information for domestic violence survivors"},
        {"name": "LawHelp.org", "url": "https://www.lawhelp.org", "desc": "Free legal aid resources"},
    ],
    "job-loss": [
        {"name": "CareerOneStop", "url": "https://www.careeronestop.org", "desc": "Job search and career resources"},
        {"name": "Department of Labor", "url": "https://www.dol.gov/unemployment", "desc": "Unemployment insurance information by state"},
        {"name": "USA.gov Benefits", "url": "https://www.usa.gov/benefits", "desc": "Government benefit programs you may qualify for"},
    ],
    "disability": [
        {"name": "Social Security Administration", "url": "https://www.ssa.gov/disability", "desc": "Apply for SSDI or SSI benefits"},
        {"name": "NOSSCR", "url": "https://www.nosscr.org", "desc": "Find a Social Security disability attorney"},
        {"name": "Disability Rights", "url": "https://www.disabilityrightsca.org", "desc": "Know your rights under the ADA"},
    ],
    "relocation": [
        {"name": "USPS Change of Address", "url": "https://www.usps.com/manage/forward.htm", "desc": "Forward your mail to your new address"},
        {"name": "Moving.org", "url": "https://www.moving.org", "desc": "Licensed mover directory and moving resources"},
    ],
    "retirement": [
        {"name": "SSA Retirement", "url": "https://www.ssa.gov/retirement", "desc": "Social Security retirement benefit calculator"},
        {"name": "FINRA Investor Tools", "url": "https://www.finra.org/investors", "desc": "Investment education and broker verification"},
        {"name": "Medicare.gov", "url": "https://www.medicare.gov", "desc": "Medicare enrollment and coverage information"},
    ],
    "addiction": [
        {"name": "SAMHSA Helpline", "url": "https://www.samhsa.gov/find-help/national-helpline", "desc": "Free 24/7 referral service: 1-800-662-4357"},
        {"name": "FindTreatment.gov", "url": "https://findtreatment.gov", "desc": "Search for treatment facilities near you"},
        {"name": "Al-Anon", "url": "https://al-anon.org", "desc": "Support groups for families of people with addiction"},
    ],
}

@app.route("/api/help/resources/<transition>")
def get_help_resources(transition):
    """Return professional help resources for a transition type."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    resources = HELP_RESOURCES.get(transition, [])
    return jsonify({"transition": transition, "resources": resources})

# ── Checklist API ──

@app.route("/api/checklist")
def get_checklist():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, transition_type, phase, item_text, is_completed, completed_at, sort_order FROM checklist_items WHERE user_id = {param} ORDER BY sort_order, id", (user["id"],))
    items = [{"id": r[0], "transition_type": r[1], "phase": r[2], "item_text": r[3], "is_completed": bool(r[4]), "completed_at": r[5], "sort_order": r[6]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"items": items})

@app.route("/api/checklist/<int:item_id>/toggle", methods=["POST"])
def toggle_checklist_item(item_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    true_val = "TRUE" if USE_POSTGRES else "1"
    false_val = "FALSE" if USE_POSTGRES else "0"
    cur = db_execute(conn, f"SELECT is_completed FROM checklist_items WHERE id = {param} AND user_id = {param}", (item_id, user["id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Item not found"}), 404
    now = datetime.now(timezone.utc).isoformat()
    if row[0]:
        db_execute(conn, f"UPDATE checklist_items SET is_completed = {false_val}, completed_at = NULL WHERE id = {param}", (item_id,))
    else:
        db_execute(conn, f"UPDATE checklist_items SET is_completed = {true_val}, completed_at = {param} WHERE id = {param}", (now, item_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "is_completed": not bool(row[0])})

@app.route("/api/checklist/<int:item_id>/skip", methods=["POST"])
def skip_checklist_item(item_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Verify ownership and get item's phase info
    cur = db_execute(conn, f"SELECT transition_type, phase FROM checklist_items WHERE id = {param} AND user_id = {param}", (item_id, user["id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Item not found"}), 404
    t_type, phase = row[0], row[1]
    # Find max sort_order in this phase and move item to end
    cur = db_execute(conn, f"SELECT COALESCE(MAX(sort_order), 0) FROM checklist_items WHERE user_id = {param} AND transition_type = {param} AND phase = {param}", (user["id"], t_type, phase))
    max_sort = cur.fetchone()[0]
    db_execute(conn, f"UPDATE checklist_items SET sort_order = {param} WHERE id = {param}", (max_sort + 1, item_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/checklist/<int:item_id>/guide")
def checklist_item_guide(item_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT item_text, transition_type, phase FROM checklist_items WHERE id = {param} AND user_id = {param}", (item_id, user["id"]))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Item not found"}), 404
    item_text, transition_type, phase = row[0], row[1], row[2]
    phase_urgency = {"First 24 Hours": "Within 24 hours", "First Week": "Within 7 days", "First Month": "Within 30 days", "This Week": "Within 7 days", "This Month": "Within 30 days"}
    urgency = phase_urgency.get(phase, "Ongoing")
    try:
        from guide_data import ITEM_GUIDES
        # Exact match first
        guide = ITEM_GUIDES.get(item_text)
        if guide:
            return jsonify({"found": True, "item_text": item_text, "transition_type": transition_type, **guide})
        # Fuzzy match: check if any key is substantially contained in this item or vice versa
        item_lower = item_text.lower().strip()
        for key, val in ITEM_GUIDES.items():
            key_lower = key.lower().strip()
            if item_lower in key_lower or key_lower in item_lower:
                return jsonify({"found": True, "item_text": item_text, "transition_type": transition_type, **val})
    except ImportError:
        pass
    # Generate guide on-the-fly for personalized/chat-created items
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system="You help people through life transitions. Return ONLY valid JSON with these keys: urgency (string like 'Within 7 days'), how_to (2-3 practical sentences), steps (array of 3-5 short action steps). Be warm, specific, and actionable. No markdown, just JSON.",
            messages=[{"role": "user", "content": f"Generate a practical guide for someone going through a {transition_type or 'life'} transition who needs to: \"{item_text}\". Phase: {phase}."}]
        )
        import json as _json
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        generated = _json.loads(text)
        return jsonify({
            "found": True,
            "item_text": item_text,
            "transition_type": transition_type,
            "urgency": generated.get("urgency", urgency),
            "how_to": generated.get("how_to", ""),
            "steps": generated.get("steps", []),
            "related_worksheet": generated.get("related_worksheet")
        })
    except Exception:
        pass
    return jsonify({"found": False, "item_text": item_text, "transition_type": transition_type, "urgency": urgency})

@app.route("/api/checklist/init", methods=["POST"])
def init_checklist():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    transition_type = data.get("transition_type", "").strip().lower()
    if transition_type not in DEFAULT_CHECKLISTS:
        return jsonify({"error": "Invalid transition type"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Don't re-init if items already exist for this transition
    cur = db_execute(conn, f"SELECT COUNT(*) FROM checklist_items WHERE user_id = {param} AND transition_type = {param}", (user["id"], transition_type))
    if cur.fetchone()[0] > 0:
        conn.close()
        return jsonify({"ok": True, "message": "Checklist already exists"})
    order = 0
    for phase, items in DEFAULT_CHECKLISTS[transition_type].items():
        for item_text in items:
            db_execute(conn, f"INSERT INTO checklist_items (user_id, transition_type, phase, item_text, sort_order) VALUES ({param},{param},{param},{param},{param})", (user["id"], transition_type, phase, item_text, order))
            order += 1
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Checklist created"})

# ── Guide Library API (serves guide content to mobile app) ──

@app.route("/api/guides/<transition>")
def get_guides(transition):
    """Serve guide library content for a given transition type. Used by mobile app."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    if transition not in VALID_CATEGORIES:
        return jsonify({"error": "Invalid transition type"}), 400

    # Load guide data from JSON file
    guide_path = os.path.join(os.path.dirname(__file__), "data", "guides", f"{transition}.json")
    if os.path.exists(guide_path):
        with open(guide_path, "r") as f:
            guide_data = json.load(f)
    else:
        guide_data = {"categories": []}

    # Check tier access
    effective_tier = get_effective_tier(user)
    cat_access = get_user_categories(user)
    has_access = cat_access.get(transition) == "full" or effective_tier in ("unlimited", "all_transitions")

    return jsonify({
        "transition": transition,
        "has_full_access": has_access,
        "effective_tier": effective_tier,
        "guide": guide_data,
    })

@app.route("/api/guides")
def list_guides():
    """List available guide transitions for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    cat_access = get_user_categories(user)
    effective_tier = get_effective_tier(user)
    transitions = []
    for key, label in CATEGORY_LABELS.items():
        has_access = cat_access.get(key) == "full" or effective_tier in ("unlimited", "all_transitions")
        transitions.append({"key": key, "label": label, "has_access": has_access})
    return jsonify({"transitions": transitions, "effective_tier": effective_tier})

DEFAULT_CHECKLISTS = {
    # Emotional pacing: quick wins first within each phase (simpler tasks before complex ones)
    "estate": {
        "First 24 Hours": [
            "Notify immediate family and close friends",
            "Secure the deceased's home and property",
            "Contact the funeral home or cremation service",
            "Obtain the death certificate (request 10+ certified copies)",
            "Locate the will and any estate planning documents",
        ],
        "First Week": [
            "Notify the post office to forward mail",
            "Contact utility companies about accounts",
            "Notify the deceased's employer and request final paycheck",
            "Contact Social Security Administration (1-800-772-1213)",
            "Contact life insurance companies to file claims",
            "Notify banks and financial institutions",
        ],
        "First Month": [
            "Cancel subscriptions and memberships",
            "Notify credit agencies (Equifax, Experian, TransUnion)",
            "Apply for survivor benefits (Social Security, VA, pension)",
            "Transfer vehicle titles",
            "Update property deeds if applicable",
            "Meet with an estate attorney if needed",
            "File for probate if required",
        ],
        "Ongoing": [
            "Keep records of all estate transactions",
            "Close remaining accounts",
            "File the deceased's final tax return",
            "Distribute assets according to the will",
        ],
    },
    "divorce": {
        "First 24 Hours": [
            "Change passwords on personal accounts",
            "Open individual bank account if you don't have one",
            "Secure copies of all important financial documents",
            "Document all shared assets and debts",
            "Consult with a family law attorney",
        ],
        "First Week": [
            "Review and understand your household budget",
            "Gather tax returns from the last 3 years",
            "List all joint accounts (bank, credit cards, investments)",
            "Research local family law attorneys (consultations are often free)",
            "Understand your state's divorce filing requirements",
        ],
        "First Month": [
            "Set up mail forwarding if moving out",
            "Update beneficiaries on insurance policies",
            "Begin the asset and property inventory",
            "File for divorce or respond to petition if served",
            "Request temporary orders if needed (custody, support, exclusive use)",
            "Understand how retirement accounts will be divided (QDRO)",
        ],
        "Ongoing": [
            "Keep detailed records of all expenses",
            "Establish credit in your own name",
            "Update your name on documents if applicable",
            "Update your estate plan (will, power of attorney)",
            "Attend all court dates and mediation sessions",
        ],
    },
    "job-loss": {
        "First 24 Hours": [
            "Secure copies of important work documents and contacts",
            "Review your last paycheck for accuracy",
            "File for unemployment benefits",
            "Understand your COBRA health insurance options",
            "Review your severance agreement (don't sign immediately)",
        ],
        "First Week": [
            "Update your resume and LinkedIn profile",
            "Create a detailed budget based on reduced income",
            "Contact creditors if you anticipate payment difficulties",
            "Apply for any applicable state or local assistance programs",
            "Review your 401(k) options (leave it, roll over, or cash out)",
        ],
        "First Month": [
            "Cut non-essential expenses",
            "Begin active job searching",
            "Decide on COBRA vs. marketplace health insurance",
            "Consider whether to roll over your 401(k) to an IRA",
            "File for any applicable tax credits or deductions",
        ],
        "Ongoing": [
            "Maintain a record of all job applications",
            "Monitor your unemployment benefits and renew if needed",
            "Network actively — attend events, reach out to contacts",
            "Consider skills training or certifications",
        ],
    },
    "relocation": {
        "First 24 Hours": [
            "Create a moving timeline and checklist",
            "Research your new state's requirements (license, registration, voting)",
            "Research schools in the new area if applicable",
            "Notify your landlord or list your home for sale",
            "Get quotes from moving companies or plan a DIY move",
        ],
        "First Week": [
            "Set up mail forwarding through USPS",
            "Notify your employer and update payroll address",
            "Transfer or set up utilities at new address",
            "Update address with banks and financial institutions",
            "Transfer medical records and find new healthcare providers",
        ],
        "First Month": [
            "Register to vote at your new address",
            "Get a new driver's license in your new state",
            "Register your vehicle in the new state",
            "Update your address with the IRS",
            "Find new local services (doctor, dentist, vet, etc.)",
        ],
        "Ongoing": [
            "Update all remaining subscriptions and accounts",
            "Explore your new community — join local groups",
            "File taxes correctly for the year you moved (may need to file in both states)",
        ],
    },
    "disability": {
        "First 24 Hours": [
            "Begin documenting your condition and limitations daily",
            "Request FMLA leave from your employer if applicable",
            "Contact your employer about short-term disability benefits",
            "Gather all medical records and documentation",
            "Understand the difference between SSDI and SSI",
        ],
        "First Week": [
            "Contact your health insurance to understand coverage",
            "Review your employer's disability insurance policy",
            "Identify all sources of income and benefits available to you",
            "Gather work history for the past 15 years",
            "Apply for Social Security disability benefits (online or by phone)",
        ],
        "First Month": [
            "Keep all medical appointments and document everything",
            "Create a budget based on reduced income",
            "Follow up on your SSDI/SSI application status",
            "Apply for any state disability programs",
            "Look into Medicaid eligibility if applicable",
        ],
        "Ongoing": [
            "Continue medical treatment and keep records",
            "Monitor your benefits and report any changes",
            "Prepare for a potential denial and appeal process",
            "Consider working with a disability attorney if denied",
        ],
    },
    "retirement": {
        "First 24 Hours": [
            "Review your employer's retirement benefits package",
            "Review all retirement account balances (401k, IRA, pension)",
            "Understand your Medicare enrollment timeline",
            "Decide when to start Social Security benefits",
            "Create a retirement income plan (Social Security + pension + savings)",
        ],
        "First Week": [
            "Create a detailed retirement budget",
            "Review your estate plan and update beneficiaries",
            "Begin consolidating retirement accounts if needed",
            "Compare Medicare Supplement vs. Medicare Advantage plans",
            "Enroll in Medicare if you're 65+ (Parts A, B, D)",
        ],
        "First Month": [
            "Plan for healthcare costs in retirement",
            "Apply for Social Security benefits (3 months before desired start)",
            "Decide on pension payout options (lump sum vs. annuity)",
            "Set up Required Minimum Distributions if 73+",
            "Consider long-term care insurance",
        ],
        "Ongoing": [
            "Review Medicare coverage during annual enrollment",
            "Update your estate plan annually",
            "Monitor your withdrawal rate and adjust as needed",
            "Take Required Minimum Distributions on time",
            "Stay active in your community — retirement is a transition too",
        ],
    },
}

# ── Personalized checklist from chat ──

@app.route("/api/checklist/init-from-chat", methods=["POST"])
def init_checklist_from_chat():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    history = data.get("history", [])
    transition_type = data.get("transition_type", "general").strip().lower()
    if not history:
        return jsonify({"error": "No conversation to analyze"}), 400
    try:
        import json as _json
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system="""You are extracting a personalized action plan from a Lumeway conversation. Return ONLY valid JSON.

Based on what was actually discussed, create a checklist of tasks the user needs to do. Also extract:
- Documents/info they need to gather (specific items like SS card, insurance policy numbers, etc.)
- Deadlines mentioned or implied
Use this exact structure:
{
  "transition_type": "estate|divorce|job-loss|relocation|disability|retirement",
  "user_state": "Two-letter state abbreviation if mentioned (e.g. CA, NY) or null",
  "tasks": [
    {"phase": "This Week", "items": ["Specific task from conversation"]},
    {"phase": "This Month", "items": ["Another specific task"]},
    {"phase": "Ongoing", "items": ["Long-term task"]}
  ],
  "documents_needed": [
    {"name": "Social Security card", "description": "Needed for benefits application"},
    {"name": "Insurance policy number", "description": "For COBRA election"}
  ],
  "deadlines": [
    {"title": "File for unemployment", "days_from_now": 7, "note": "Don't wait — benefits start from filing date"},
    {"title": "COBRA election deadline", "days_from_now": 60, "note": "60-day window from job loss"}
  ]
}

Make tasks SPECIFIC to what was discussed — not generic. If they mentioned kids, include kid-related tasks. If they mentioned a specific state, include state-specific items. If they mentioned specific concerns, address those directly.""",
            messages=[{"role": "user", "content": "Extract a personalized action plan from this conversation:\n\n" + _json.dumps(history[-20:])}]
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        plan = _json.loads(text)

        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        true_val = "TRUE" if USE_POSTGRES else "1"
        now = datetime.now(timezone.utc).isoformat()
        t_type = plan.get("transition_type", transition_type)

        # Clear previous uncompleted chat-generated items for this transition
        # (keeps user-completed items, replaces uncompleted ones with fresh extraction)
        false_val = "FALSE" if USE_POSTGRES else "0"
        db_execute(conn, f"DELETE FROM checklist_items WHERE user_id = {param} AND transition_type = {param} AND is_completed = {false_val}",
            (user["id"], t_type))
        # Clear previous documents/deadlines/goals from chat for this transition (not user-created ones)
        db_execute(conn, f"DELETE FROM user_documents_needed WHERE user_id = {param} AND transition_type = {param} AND is_gathered = {false_val}",
            (user["id"], t_type))
        db_execute(conn, f"DELETE FROM user_deadlines WHERE user_id = {param} AND transition_type = {param} AND source = 'chat'",
            (user["id"], t_type))

        # Save checklist items
        order = 0
        for phase_group in plan.get("tasks", []):
            phase = phase_group.get("phase", "General")
            for item_text in phase_group.get("items", []):
                db_execute(conn, f"INSERT INTO checklist_items (user_id, transition_type, phase, item_text, sort_order) VALUES ({param},{param},{param},{param},{param})",
                    (user["id"], t_type, phase, item_text, order))
                order += 1

        # Save documents needed
        for doc in plan.get("documents_needed", []):
            db_execute(conn, f"INSERT INTO user_documents_needed (user_id, transition_type, document_name, description, created_at) VALUES ({param},{param},{param},{param},{param})",
                (user["id"], t_type, doc.get("name", ""), doc.get("description", ""), now))

        # Save deadlines
        for dl in plan.get("deadlines", []):
            days = dl.get("days_from_now", 30)
            deadline_date = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
            db_execute(conn, f"INSERT INTO user_deadlines (user_id, transition_type, title, deadline_date, note, source, created_at) VALUES ({param},{param},{param},{param},{param},{param},{param})",
                (user["id"], t_type, dl.get("title", ""), deadline_date, dl.get("note", ""), "chat", now))

        # Auto-populate user state and transition type from chat
        extracted_state = plan.get("user_state")
        if extracted_state or t_type != "general":
            update_fields = []
            update_vals = []
            if t_type and t_type != "general" and not user.get("transition_type"):
                update_fields.append(f"transition_type = {param}")
                update_vals.append(t_type)
            if extracted_state and not user.get("us_state"):
                update_fields.append(f"us_state = {param}")
                update_vals.append(extracted_state.upper()[:5])
            if update_fields:
                update_vals.append(user["id"])
                db_execute(conn, f"UPDATE users SET {', '.join(update_fields)} WHERE id = {param}", tuple(update_vals))

        conn.commit()
        conn.close()
        return jsonify({"ok": True, "plan": plan})
    except Exception as e:
        print(f"Personalized checklist error: {e}")
        return jsonify({"error": str(e)}), 500


# ── Notes API ──

@app.route("/api/notes")
def get_notes():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, content, created_at, updated_at FROM user_notes WHERE user_id = {param} ORDER BY created_at DESC", (user["id"],))
    notes = [{"id": r[0], "content": r[1], "created_at": r[2], "updated_at": r[3]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"notes": notes})

@app.route("/api/notes", methods=["POST"])
def save_note():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "Empty note"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    db_execute(conn, f"INSERT INTO user_notes (user_id, content, created_at) VALUES ({param},{param},{param})", (user["id"], content, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/notes/<int:note_id>", methods=["PUT"])
def update_note(note_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    content = data.get("content", "").strip()
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    db_execute(conn, f"UPDATE user_notes SET content = {param}, updated_at = {param} WHERE id = {param} AND user_id = {param}", (content, now, note_id, user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/notes/<int:note_id>", methods=["DELETE"])
def delete_note(note_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM user_notes WHERE id = {param} AND user_id = {param}", (note_id, user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Deadlines API ──

@app.route("/api/deadlines")
def get_deadlines():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, transition_type, title, deadline_date, note, is_completed, source, created_at FROM user_deadlines WHERE user_id = {param} ORDER BY deadline_date", (user["id"],))
    deadlines = [{"id": r[0], "transition_type": r[1], "title": r[2], "deadline_date": r[3], "note": r[4], "is_completed": bool(r[5]), "source": r[6], "created_at": r[7]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"deadlines": deadlines})

@app.route("/api/deadlines", methods=["POST"])
def add_deadline():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    title = data.get("title", "").strip()
    deadline_date = data.get("deadline_date", "").strip()
    if not title or not deadline_date:
        return jsonify({"error": "Title and date required"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    db_execute(conn, f"INSERT INTO user_deadlines (user_id, transition_type, title, deadline_date, note, source, created_at) VALUES ({param},{param},{param},{param},{param},{param},{param})",
        (user["id"], data.get("transition_type"), title, deadline_date, data.get("note", ""), "manual", now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/deadlines/<int:deadline_id>/toggle", methods=["POST"])
def toggle_deadline(deadline_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    true_val = "TRUE" if USE_POSTGRES else "1"
    false_val = "FALSE" if USE_POSTGRES else "0"
    cur = db_execute(conn, f"SELECT is_completed FROM user_deadlines WHERE id = {param} AND user_id = {param}", (deadline_id, user["id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    new_val = false_val if row[0] else true_val
    db_execute(conn, f"UPDATE user_deadlines SET is_completed = {new_val} WHERE id = {param}", (deadline_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "is_completed": not bool(row[0])})

@app.route("/api/deadlines/<int:deadline_id>", methods=["DELETE"])
def delete_deadline(deadline_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM user_deadlines WHERE id = {param} AND user_id = {param}", (deadline_id, user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/deadlines/<int:deadline_id>", methods=["PUT"])
def update_deadline(deadline_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    updates = []
    values = []
    for field in ["title", "deadline_date", "note"]:
        if field in data:
            updates.append(f"{field} = {param}")
            values.append(data[field])
    if not updates:
        conn.close()
        return jsonify({"error": "No fields to update"}), 400
    values.extend([deadline_id, user["id"]])
    db_execute(conn, f"UPDATE user_deadlines SET {', '.join(updates)} WHERE id = {param} AND user_id = {param}", tuple(values))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/deadlines/export.ics")
def export_deadlines_ics():
    user = get_current_user()
    if not user:
        return "Not logged in", 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, transition_type, title, deadline_date, note, is_completed FROM user_deadlines WHERE user_id = {param} ORDER BY deadline_date", (user["id"],))
    rows = cur.fetchall()
    conn.close()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lumeway//Deadlines//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Lumeway Deadlines",
    ]
    for r in rows:
        dl_id, t_type, title, dl_date, note, is_completed = r
        if not dl_date:
            continue
        date_clean = dl_date.replace("-", "")
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:deadline-{dl_id}@lumeway.co")
        lines.append(f"DTSTART;VALUE=DATE:{date_clean}")
        lines.append(f"SUMMARY:{_ics_escape(title)}")
        if note:
            lines.append(f"DESCRIPTION:{_ics_escape(note)}")
        if t_type:
            lines.append(f"CATEGORIES:{t_type}")
        lines.append(f"STATUS:{'COMPLETED' if is_completed else 'CONFIRMED'}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    ics_text = "\r\n".join(lines)
    return Response(ics_text, mimetype="text/calendar", headers={"Content-Disposition": "attachment; filename=lumeway-deadlines.ics"})

def _ics_escape(text):
    """Escape text for iCalendar format."""
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


# ── Documents Needed API ──

@app.route("/api/documents-needed")
def get_documents_needed():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, transition_type, document_name, description, is_gathered FROM user_documents_needed WHERE user_id = {param} ORDER BY id", (user["id"],))
    docs = [{"id": r[0], "transition_type": r[1], "document_name": r[2], "description": r[3], "is_gathered": bool(r[4])} for r in cur.fetchall()]
    conn.close()
    return jsonify({"documents": docs})

@app.route("/api/documents-needed/<int:doc_id>/toggle", methods=["POST"])
def toggle_document_needed(doc_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    true_val = "TRUE" if USE_POSTGRES else "1"
    false_val = "FALSE" if USE_POSTGRES else "0"
    cur = db_execute(conn, f"SELECT is_gathered FROM user_documents_needed WHERE id = {param} AND user_id = {param}", (doc_id, user["id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    new_val = false_val if row[0] else true_val
    db_execute(conn, f"UPDATE user_documents_needed SET is_gathered = {new_val} WHERE id = {param}", (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "is_gathered": not bool(row[0])})

@app.route("/api/documents-needed", methods=["POST"])
def add_document_needed():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    name = data.get("document_name", "").strip()
    if not name:
        return jsonify({"error": "Document name required"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"INSERT INTO user_documents_needed (user_id, transition_type, document_name, description) VALUES ({param},{param},{param},{param})",
        (user["id"], data.get("transition_type"), name, data.get("description", "")))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/documents-needed/<int:doc_id>", methods=["DELETE"])
def delete_document_needed(doc_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM user_documents_needed WHERE id = {param} AND user_id = {param}", (doc_id, user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/documents-needed/<int:doc_id>", methods=["PUT"])
def update_document_needed(doc_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    updates = []
    values = []
    for field in ["document_name", "description"]:
        if field in data:
            updates.append(f"{field} = {param}")
            values.append(data[field])
    if not updates:
        conn.close()
        return jsonify({"error": "No fields to update"}), 400
    values.extend([doc_id, user["id"]])
    db_execute(conn, f"UPDATE user_documents_needed SET {', '.join(updates)} WHERE id = {param} AND user_id = {param}", tuple(values))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Goals API ──

@app.route("/api/goals")
def get_goals():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, title, timeframe, target_date, is_completed, created_at FROM user_goals WHERE user_id = {param} ORDER BY target_date", (user["id"],))
    goals = [{"id": r[0], "title": r[1], "timeframe": r[2], "target_date": r[3], "is_completed": bool(r[4]), "created_at": r[5]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"goals": goals})

@app.route("/api/goals", methods=["POST"])
def add_goal():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    title = data.get("title", "").strip()
    timeframe = data.get("timeframe", "weekly").strip()
    if not title:
        return jsonify({"error": "Title required"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    db_execute(conn, f"INSERT INTO user_goals (user_id, title, timeframe, target_date, created_at) VALUES ({param},{param},{param},{param},{param})",
        (user["id"], title, timeframe, data.get("target_date"), now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/goals/<int:goal_id>/toggle", methods=["POST"])
def toggle_goal(goal_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    true_val = "TRUE" if USE_POSTGRES else "1"
    false_val = "FALSE" if USE_POSTGRES else "0"
    cur = db_execute(conn, f"SELECT is_completed FROM user_goals WHERE id = {param} AND user_id = {param}", (goal_id, user["id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    new_val = false_val if row[0] else true_val
    db_execute(conn, f"UPDATE user_goals SET is_completed = {new_val} WHERE id = {param}", (goal_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "is_completed": not bool(row[0])})

@app.route("/api/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM user_goals WHERE id = {param} AND user_id = {param}", (goal_id, user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    updates = []
    values = []
    for field in ["title", "timeframe", "target_date"]:
        if field in data:
            updates.append(f"{field} = {param}")
            values.append(data[field])
    if not updates:
        conn.close()
        return jsonify({"error": "No fields to update"}), 400
    values.extend([goal_id, user["id"]])
    db_execute(conn, f"UPDATE user_goals SET {', '.join(updates)} WHERE id = {param} AND user_id = {param}", tuple(values))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Activity Log API ──

@app.route("/api/activity-log")
def get_activity_log():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, action_type, contact_name, organization, description, date, created_at FROM user_activity_log WHERE user_id = {param} ORDER BY date DESC, created_at DESC", (user["id"],))
    entries = [{"id": r[0], "action_type": r[1], "contact_name": r[2], "organization": r[3], "description": r[4], "date": r[5], "created_at": r[6]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"entries": entries})

@app.route("/api/activity-log", methods=["POST"])
def add_activity_log():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    action_type = data.get("action_type", "").strip()
    description = data.get("description", "").strip()
    date = data.get("date", "").strip()
    if not action_type or not description or not date:
        return jsonify({"error": "action_type, description, and date are required"}), 400
    contact_name = data.get("contact_name", "").strip() or None
    organization = data.get("organization", "").strip() or None
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    db_execute(conn, f"INSERT INTO user_activity_log (user_id, action_type, contact_name, organization, description, date, created_at) VALUES ({param},{param},{param},{param},{param},{param},{param})", (user["id"], action_type, contact_name, organization, description, date, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/activity-log/<int:entry_id>", methods=["DELETE"])
def delete_activity_log(entry_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM user_activity_log WHERE id = {param} AND user_id = {param}", (entry_id, user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── File upload / storage ──

@app.route("/api/files/upload", methods=["POST"])
def upload_file():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401

    if not check_upload_rate(user["id"]):
        return jsonify({"error": "Upload limit reached. Please try again later."}), 429

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files['file']
    if f.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # 10MB limit
    MAX_SIZE = 10 * 1024 * 1024
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > MAX_SIZE:
        return jsonify({"error": "File too large. Maximum size is 10MB."}), 400

    # Allowed types
    allowed_ext = {'.pdf', '.doc', '.docx', '.txt', '.jpg', '.jpeg', '.png', '.gif', '.xlsx', '.xls', '.csv'}
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({"error": "File type not allowed."}), 400

    # Validate file magic bytes
    if not validate_file_type(f, f.filename):
        return jsonify({"error": "File content doesn't match its extension."}), 400

    category = request.form.get('category', 'other')

    # Store with unique name
    stored_name = f"{uuid.uuid4().hex}{ext}"

    # Encrypt and save to storage (S3 or local)
    file_data = f.read()
    encrypted_data = file_cipher.encrypt(file_data)
    storage_save(user["id"], stored_name, encrypted_data)

    # Save to DB
    now = datetime.utcnow().isoformat()
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"""INSERT INTO user_files (user_id, original_name, stored_name, category, file_size, content_type, uploaded_at)
        VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param})""",
        (user["id"], f.filename, stored_name, category, size, f.content_type, now))
    conn.commit()

    # Get the inserted ID
    if USE_POSTGRES:
        cur = db_execute(conn, "SELECT lastval()")
    else:
        cur = db_execute(conn, "SELECT last_insert_rowid()")
    file_id = cur.fetchone()[0]
    conn.close()

    audit_log(user["id"], "file_upload", "file", str(file_id), f"{f.filename} ({category}, {size} bytes)")

    return jsonify({"ok": True, "file": {
        "id": file_id, "original_name": f.filename, "category": category,
        "file_size": size, "content_type": f.content_type, "uploaded_at": now
    }})


@app.route("/api/files")
def list_files():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, original_name, stored_name, category, file_size, content_type, uploaded_at FROM user_files WHERE user_id = {param} ORDER BY uploaded_at DESC", (user["id"],))
    files = [{"id": r[0], "original_name": r[1], "category": r[3], "file_size": r[4], "content_type": r[5], "uploaded_at": r[6]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"files": files})


@app.route("/api/files/<int:file_id>/download")
def download_user_file(file_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT original_name, stored_name, content_type FROM user_files WHERE id = {param} AND user_id = {param}", (file_id, user["id"]))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "File not found"}), 404
    encrypted_data = storage_load(user["id"], row[1])
    if encrypted_data is None:
        return jsonify({"error": "File not found in storage"}), 404
    decrypted_data = file_cipher.decrypt(encrypted_data)
    audit_log(user["id"], "file_download", "file", str(file_id), row[0])
    return send_file(io.BytesIO(decrypted_data), as_attachment=True, download_name=row[0], mimetype=row[2] if '/' in str(row[2]) else 'application/octet-stream')


@app.route("/api/files/<int:file_id>/preview")
def preview_user_file(file_id):
    """Serve file inline for in-browser preview (not as download attachment)."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT original_name, stored_name, content_type FROM user_files WHERE id = {param} AND user_id = {param}", (file_id, user["id"]))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "File not found"}), 404
    encrypted_data = storage_load(user["id"], row[1])
    if encrypted_data is None:
        return jsonify({"error": "File not found in storage"}), 404
    try:
        decrypted_data = file_cipher.decrypt(encrypted_data)
    except Exception:
        return jsonify({"error": "Could not decrypt file"}), 500
    mime = row[2] if row[2] and '/' in str(row[2]) else 'application/octet-stream'
    # Use send_file for proper streaming of binary data
    return send_file(
        io.BytesIO(decrypted_data),
        mimetype=mime,
        as_attachment=False,
        download_name=row[0]
    )


@app.route("/api/files/<int:file_id>/convert")
def convert_docx_to_html(file_id):
    """Convert a .docx file to HTML with proper table support using python-docx."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    if not HAS_DOCX:
        return jsonify({"error": "Document conversion not available", "html": None})
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT original_name, stored_name FROM user_files WHERE id = {param} AND user_id = {param}", (file_id, user["id"]))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "File not found"}), 404
    ext = os.path.splitext(row[0])[1].lower()
    if ext not in ('.docx',):
        return jsonify({"error": "Only .docx files can be converted", "html": None})
    encrypted_data = storage_load(user["id"], row[1])
    if encrypted_data is None:
        return jsonify({"error": "File not found in storage"}), 404
    try:
        decrypted_data = file_cipher.decrypt(encrypted_data)
        doc = DocxDocument(io.BytesIO(decrypted_data))
        html_parts = []
        for element in doc.element.body:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag == 'p':
                # Paragraph — preserve formatting, colors, sizes, alignment
                p = element
                style_name = ''
                p_styles = []
                pPr = p.find(qn('w:pPr'))
                if pPr is not None:
                    pStyle = pPr.find(qn('w:pStyle'))
                    if pStyle is not None:
                        style_name = pStyle.get(qn('w:val'), '')
                    # Paragraph alignment
                    jc = pPr.find(qn('w:jc'))
                    if jc is not None:
                        align_val = jc.get(qn('w:val'), '')
                        align_map = {'center': 'center', 'right': 'right', 'both': 'justify', 'left': 'left'}
                        if align_val in align_map:
                            p_styles.append('text-align:{}'.format(align_map[align_val]))
                    # Paragraph background/shading
                    pShd = pPr.find(qn('w:shd'))
                    if pShd is not None:
                        pfill = pShd.get(qn('w:fill'), '')
                        if pfill and pfill not in ('auto', 'FFFFFF'):
                            p_styles.append('background-color:#{}'.format(pfill))
                            p_styles.append('padding:8px 12px')
                    # Paragraph indentation
                    ind = pPr.find(qn('w:ind'))
                    if ind is not None:
                        left_ind = ind.get(qn('w:left'), '')
                        if left_ind:
                            try:
                                p_styles.append('margin-left:{}pt'.format(round(int(left_ind) / 20)))
                            except ValueError:
                                pass
                text_parts = []
                for run in p.findall(qn('w:r')):
                    rPr = run.find(qn('w:rPr'))
                    bold = rPr is not None and rPr.find(qn('w:b')) is not None
                    italic = rPr is not None and rPr.find(qn('w:i')) is not None
                    underline = rPr is not None and rPr.find(qn('w:u')) is not None
                    t = run.find(qn('w:t'))
                    txt = t.text if t is not None and t.text else ''
                    # Run-level formatting: color, size, font, highlight
                    run_styles = []
                    if rPr is not None:
                        color_el = rPr.find(qn('w:color'))
                        if color_el is not None:
                            cval = color_el.get(qn('w:val'), '')
                            if cval and cval not in ('auto', '000000'):
                                run_styles.append('color:#{}'.format(cval))
                        sz_el = rPr.find(qn('w:sz'))
                        if sz_el is not None:
                            szval = sz_el.get(qn('w:val'), '')
                            if szval:
                                try:
                                    # w:sz is in half-points
                                    run_styles.append('font-size:{}pt'.format(round(int(szval) / 2)))
                                except ValueError:
                                    pass
                        rFonts = rPr.find(qn('w:rFonts'))
                        if rFonts is not None:
                            font_name = rFonts.get(qn('w:ascii'), '') or rFonts.get(qn('w:hAnsi'), '')
                            if font_name and font_name not in ('Calibri', 'Arial', 'Times New Roman'):
                                run_styles.append("font-family:'{}'".format(font_name))
                        highlight = rPr.find(qn('w:highlight'))
                        if highlight is not None:
                            hl_val = highlight.get(qn('w:val'), '')
                            hl_colors = {'yellow': '#FFFF00', 'green': '#00FF00', 'cyan': '#00FFFF',
                                         'magenta': '#FF00FF', 'blue': '#0000FF', 'red': '#FF0000',
                                         'darkBlue': '#00008B', 'darkCyan': '#008B8B', 'darkGreen': '#006400',
                                         'darkMagenta': '#8B008B', 'darkRed': '#8B0000', 'darkYellow': '#808000',
                                         'darkGray': '#A9A9A9', 'lightGray': '#D3D3D3', 'black': '#000000'}
                            if hl_val in hl_colors:
                                run_styles.append('background-color:{}'.format(hl_colors[hl_val]))
                    if bold: txt = '<strong>' + txt + '</strong>'
                    if italic: txt = '<em>' + txt + '</em>'
                    if underline: txt = '<u>' + txt + '</u>'
                    if run_styles:
                        txt = '<span style="{}">{}</span>'.format('; '.join(run_styles), txt)
                    text_parts.append(txt)
                content = ''.join(text_parts)
                p_attr = ''
                if p_styles:
                    p_attr = ' style="{}"'.format('; '.join(p_styles))
                if not content.strip():
                    html_parts.append('<p><br></p>')
                elif 'Heading1' in style_name or 'Title' in style_name:
                    html_parts.append('<h1{}>{}</h1>'.format(p_attr, content))
                elif 'Heading2' in style_name:
                    html_parts.append('<h2{}>{}</h2>'.format(p_attr, content))
                elif 'Heading3' in style_name:
                    html_parts.append('<h3{}>{}</h3>'.format(p_attr, content))
                else:
                    html_parts.append('<p{}>{}</p>'.format(p_attr, content))
            elif tag == 'tbl':
                # Table — preserve column widths from Word
                # Read grid column widths (w:tblGrid/w:gridCol)
                col_widths = []
                tbl_grid = element.find(qn('w:tblGrid'))
                if tbl_grid is not None:
                    for grid_col in tbl_grid.findall(qn('w:gridCol')):
                        w_val = grid_col.get(qn('w:w'), '')
                        if w_val:
                            try:
                                # Convert twips to points (1 inch = 1440 twips = 72pt)
                                pt = round(int(w_val) / 20)
                                col_widths.append(pt)
                            except ValueError:
                                col_widths.append(0)
                # Check table width
                tbl_style = ''
                tblPr = element.find(qn('w:tblPr'))
                if tblPr is not None:
                    tblW = tblPr.find(qn('w:tblW'))
                    if tblW is not None:
                        tw = tblW.get(qn('w:w'), '0')
                        tw_type = tblW.get(qn('w:type'), 'auto')
                        if tw_type == 'pct':
                            pct = round(int(tw) / 50)  # 5000 = 100%
                            tbl_style = ' style="width:{}%"'.format(min(pct, 100))
                        elif tw_type == 'dxa' and tw != '0':
                            try:
                                tbl_pt = round(int(tw) / 20)
                                tbl_style = ' style="width:{}pt"'.format(tbl_pt)
                            except ValueError:
                                pass
                if not tbl_style:
                    tbl_style = ' style="width:100%"'
                rows_html = []
                for tr in element.findall(qn('w:tr')):
                    cells_html = []
                    col_idx = 0
                    for tc in tr.findall(qn('w:tc')):
                        cell_text = []
                        for cp in tc.findall(qn('w:p')):
                            parts = []
                            for run in cp.findall(qn('w:r')):
                                rPr = run.find(qn('w:rPr'))
                                bold = rPr is not None and rPr.find(qn('w:b')) is not None
                                italic = rPr is not None and rPr.find(qn('w:i')) is not None
                                underline = rPr is not None and rPr.find(qn('w:u')) is not None
                                t = run.find(qn('w:t'))
                                txt = t.text if t is not None and t.text else ''
                                if bold: txt = '<strong>' + txt + '</strong>'
                                if italic: txt = '<em>' + txt + '</em>'
                                if underline: txt = '<u>' + txt + '</u>'
                                parts.append(txt)
                            cell_text.append(''.join(parts))
                        # Build cell style: width + shading + colspan
                        styles = []
                        tcPr = tc.find(qn('w:tcPr'))
                        colspan = 1
                        if tcPr is not None:
                            # Cell width
                            tcW = tcPr.find(qn('w:tcW'))
                            if tcW is not None:
                                cw = tcW.get(qn('w:w'), '0')
                                cw_type = tcW.get(qn('w:type'), 'auto')
                                if cw_type == 'dxa' and cw != '0':
                                    try:
                                        cell_pt = round(int(cw) / 20)
                                        styles.append('width:{}pt'.format(cell_pt))
                                    except ValueError:
                                        pass
                                elif cw_type == 'pct' and cw != '0':
                                    try:
                                        cell_pct = round(int(cw) / 50)
                                        styles.append('width:{}%'.format(min(cell_pct, 100)))
                                    except ValueError:
                                        pass
                            elif col_idx < len(col_widths) and col_widths[col_idx] > 0:
                                styles.append('width:{}pt'.format(col_widths[col_idx]))
                            # Shading
                            shd = tcPr.find(qn('w:shd'))
                            if shd is not None:
                                fill = shd.get(qn('w:fill'), '')
                                if fill and fill != 'auto' and fill != 'FFFFFF':
                                    styles.append('background:#{}'.format(fill))
                            # Column span
                            gridSpan = tcPr.find(qn('w:gridSpan'))
                            if gridSpan is not None:
                                try:
                                    colspan = int(gridSpan.get(qn('w:val'), '1'))
                                except ValueError:
                                    colspan = 1
                            # Vertical merge (detect header of merged cell)
                            vMerge = tcPr.find(qn('w:vMerge'))
                            if vMerge is not None:
                                vm_val = vMerge.get(qn('w:val'), '')
                                if vm_val != 'restart':
                                    col_idx += colspan
                                    continue  # Skip continuation cells
                        else:
                            if col_idx < len(col_widths) and col_widths[col_idx] > 0:
                                styles.append('width:{}pt'.format(col_widths[col_idx]))
                        attrs = ''
                        if styles:
                            attrs += ' style="{}"'.format('; '.join(styles))
                        if colspan > 1:
                            attrs += ' colspan="{}"'.format(colspan)
                        cells_html.append('<td{}>{}</td>'.format(attrs, '<br>'.join(cell_text)))
                        col_idx += colspan
                    rows_html.append('<tr>' + ''.join(cells_html) + '</tr>')
                html_parts.append('<table{}>{}</table>'.format(tbl_style, ''.join(rows_html)))
        return jsonify({"ok": True, "html": '\n'.join(html_parts)})
    except Exception as e:
        return jsonify({"error": str(e), "html": None})


@app.route("/api/files/<int:file_id>/edit", methods=["GET"])
def get_file_edit(file_id):
    """Get saved HTML edit for a file."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT html_content, updated_at FROM file_edits WHERE user_id = {param} AND file_id = {param}", (user["id"], file_id))
    row = cur.fetchone()
    conn.close()
    if row:
        return jsonify({"ok": True, "html": row[0], "updated_at": row[1]})
    return jsonify({"ok": True, "html": None})


@app.route("/api/files/<int:file_id>/edit", methods=["POST"])
def save_file_edit(file_id):
    """Save HTML edit for a file (auto-save from editor)."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json() or {}
    html_content = data.get("html", "")
    if not html_content:
        return jsonify({"error": "No content"}), 400
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Upsert
    if USE_POSTGRES:
        db_execute(conn, f"""INSERT INTO file_edits (user_id, file_id, html_content, updated_at)
            VALUES ({param}, {param}, {param}, {param})
            ON CONFLICT (user_id, file_id) DO UPDATE SET html_content = EXCLUDED.html_content, updated_at = EXCLUDED.updated_at""",
            (user["id"], file_id, html_content, now))
    else:
        db_execute(conn, f"""INSERT OR REPLACE INTO file_edits (user_id, file_id, html_content, updated_at)
            VALUES ({param}, {param}, {param}, {param})""",
            (user["id"], file_id, html_content, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/files/<int:file_id>/category", methods=["POST"])
def update_file_category(file_id):
    """Change the category of an uploaded file."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json() or {}
    category = data.get("category", "other")
    valid = ['legal', 'financial', 'insurance', 'medical', 'personal', 'other']
    if category not in valid:
        return jsonify({"error": "Invalid category"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"UPDATE user_files SET category = {param} WHERE id = {param} AND user_id = {param}", (category, file_id, user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/files/<int:file_id>", methods=["DELETE"])
def delete_file(file_id):
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT stored_name FROM user_files WHERE id = {param} AND user_id = {param}", (file_id, user["id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "File not found"}), 404
    # Delete file from storage (S3 or local)
    storage_delete(user["id"], row[0])
    db_execute(conn, f"DELETE FROM user_files WHERE id = {param} AND user_id = {param}", (file_id, user["id"]))
    db_execute(conn, f"DELETE FROM file_edits WHERE user_id = {param} AND file_id = {param}", (user["id"], file_id))
    conn.commit()
    conn.close()
    audit_log(user["id"], "file_delete", "file", str(file_id))
    return jsonify({"ok": True})


# ── Auto-calculate deadlines from key date ──

DEADLINE_TEMPLATES = {
    "retirement": [
        {"title": "Apply for Social Security", "days_before": 90, "note": "Apply 3 months before desired start date. Docs: Social Security card, birth certificate, W-2 or self-employment tax return. Contact: SSA at 1-800-772-1213 or ssa.gov"},
        {"title": "Enroll in Medicare Part A & B", "days_before": 90, "note": "Initial enrollment starts 3 months before turning 65. Docs: Social Security card, proof of citizenship or residency. Contact: SSA at 1-800-772-1213 or medicare.gov"},
        {"title": "Choose Medicare Part D plan", "days_before": 60, "note": "Drug coverage — compare plans at medicare.gov/plan-compare. Docs: current prescription list. Contact: 1-800-MEDICARE (1-800-633-4227)"},
        {"title": "Submit employer retirement notification", "days_before": 60, "note": "Give employer adequate notice. Docs: written resignation letter with retirement date. Contact: your HR department"},
        {"title": "Decide pension payout option", "days_before": 45, "note": "Lump sum vs annuity — get advice before choosing. Docs: pension plan summary, spousal consent form if married. Contact: your pension plan administrator or a fee-only financial advisor"},
        {"title": "Roll over or consolidate 401(k)", "days_before": 30, "note": "Decide before your last day of work. Docs: most recent 401(k) statement, new IRA account number. Contact: your 401(k) plan provider and receiving IRA custodian"},
        {"title": "Set up retirement income withdrawals", "days_before": 14, "note": "Ensure income starts when paychecks stop. Docs: bank routing/account numbers for direct deposit. Contact: your IRA or brokerage custodian"},
        {"title": "Final day — confirm benefits end dates", "days_before": 0, "note": "Verify health insurance continuation, final paycheck. Docs: benefits summary, COBRA election notice. Contact: HR department"},
        {"title": "Start Required Minimum Distributions if 73+", "days_before": -30, "note": "RMDs must begin by April 1 after turning 73. Docs: account statements for all retirement accounts. Contact: each account custodian (Fidelity, Vanguard, etc.)"},
    ],
    "job-loss": [
        {"title": "File for unemployment benefits", "days_before": -1, "note": "File immediately — benefits start from filing date. Docs: Social Security number, driver's license, last employer info (name, address, dates), W-2 or pay stubs. Contact: your state's unemployment office website"},
        {"title": "Review severance agreement", "days_before": -7, "note": "Don't sign before consulting an attorney if possible. Docs: severance offer letter, employment contract, any non-compete agreements. Contact: an employment attorney (many offer free consultations)"},
        {"title": "Decide on COBRA or marketplace insurance", "days_before": -14, "note": "You have 60 days but don't wait. Docs: COBRA election notice from employer, current prescription list, doctor info. Contact: healthcare.gov or your state exchange for marketplace; former employer's HR for COBRA"},
        {"title": "Roll over 401(k) to IRA", "days_before": -30, "note": "Avoid penalties — roll over, don't cash out. Docs: most recent 401(k) statement, new IRA account info. Contact: your 401(k) plan provider"},
        {"title": "COBRA election deadline", "days_before": -60, "note": "60-day window from loss of coverage. Docs: COBRA election form, first premium payment. Contact: your former employer's benefits administrator"},
        {"title": "Apply for marketplace insurance", "days_before": -60, "note": "Special enrollment period lasts 60 days. Docs: proof of job loss (termination letter), income estimate, Social Security numbers for household. Contact: healthcare.gov or 1-800-318-2596"},
    ],
    "estate": [
        {"title": "Obtain certified death certificates (10+)", "days_before": -3, "note": "You'll need many copies for banks, insurance, etc. Docs: deceased's ID, your ID proving relationship. Contact: funeral home (they usually order these) or county vital records office"},
        {"title": "Notify Social Security Administration", "days_before": -7, "note": "Docs: death certificate, deceased's Social Security number. Contact: SSA at 1-800-772-1213 (funeral home may also notify them)"},
        {"title": "File life insurance claims", "days_before": -14, "note": "Docs: death certificate, policy numbers, claimant ID, beneficiary designation forms. Contact: each life insurance company's claims department"},
        {"title": "Notify banks and financial institutions", "days_before": -14, "note": "Freeze joint accounts if needed. Docs: death certificate, your ID, Letters Testamentary or court appointment. Contact: each bank/brokerage branch or their estate services department"},
        {"title": "File for probate if required", "days_before": -30, "note": "Docs: original will, death certificate, petition for probate, list of assets and heirs. Contact: an estate/probate attorney in the deceased's county of residence"},
        {"title": "Apply for survivor benefits", "days_before": -30, "note": "Docs: death certificate, marriage certificate, deceased's Social Security number, your birth certificate. Contact: SSA at 1-800-772-1213 for Social Security; VA at 1-800-827-1000 for veterans benefits"},
        {"title": "File final tax return for deceased", "days_before": -365, "note": "Due by April 15 of following year. Docs: W-2s, 1099s, prior year tax returns, Social Security number. Contact: a CPA or tax preparer experienced with estate returns"},
    ],
    "divorce": [
        {"title": "Secure copies of all financial documents", "days_before": -3, "note": "Docs needed: last 3 years of tax returns, bank/investment statements, mortgage statements, credit card statements, pay stubs, retirement account statements. Store copies in a safe place outside the home."},
        {"title": "Consult with a family law attorney", "days_before": -7, "note": "Many offer free initial consultations. Docs: financial documents gathered above, prenuptial agreement if any, timeline of marriage. Contact: your state bar association's lawyer referral service"},
        {"title": "File for divorce or respond to petition", "days_before": -30, "note": "Response deadlines vary by state — check yours. Docs: petition/complaint for divorce, filing fee, marriage certificate. Contact: your county courthouse clerk's office or your attorney"},
        {"title": "Request temporary orders if needed", "days_before": -30, "note": "Custody, support, exclusive use of home. Docs: financial affidavit, proposed parenting plan. Contact: your attorney or county family court clerk"},
        {"title": "Complete asset and property inventory", "days_before": -45, "note": "Document everything — real estate, vehicles, accounts. Docs: property deeds, vehicle titles, account statements, appraisals. Contact: your attorney; may need a property appraiser"},
        {"title": "Update beneficiaries on all accounts", "days_before": -60, "note": "Docs: beneficiary change forms for each account. Contact: each insurance company, 401(k)/IRA provider, bank, and investment firm individually"},
    ],
    "relocation": [
        {"title": "Give landlord written notice", "days_before": 60, "note": "Check your lease for required notice period. Docs: written notice letter (keep a copy), lease agreement. Contact: your landlord or property management company"},
        {"title": "Book moving company or reserve truck", "days_before": 45, "note": "Prices go up closer to move date. Docs: home inventory list, get 3+ quotes in writing. Contact: licensed movers (check FMCSA for interstate) or U-Haul/Penske/Budget for DIY"},
        {"title": "Set up mail forwarding through USPS", "days_before": 14, "note": "Start 2 weeks before move. Docs: current and new address, payment method. Contact: usps.com/move or your local post office"},
        {"title": "Transfer or set up utilities at new address", "days_before": 7, "note": "Electric, gas, water, internet. Docs: new address, lease or purchase agreement, ID. Contact: each utility provider at new address; cancel old ones"},
        {"title": "Get new driver's license", "days_before": -30, "note": "Most states require within 30-90 days. Docs: current license, proof of new address (lease/utility bill), Social Security card, birth certificate. Contact: new state's DMV"},
        {"title": "Register vehicle in new state", "days_before": -30, "note": "Check your state's deadline. Docs: current title, current registration, proof of insurance in new state, emissions test if required. Contact: new state's DMV"},
        {"title": "Register to vote at new address", "days_before": -30, "note": "Update before next election. Docs: driver's license or Social Security number. Contact: vote.gov or your county elections office"},
    ],
    "disability": [
        {"title": "Request FMLA leave from employer", "days_before": -3, "note": "You're entitled to 12 weeks unpaid leave. Docs: FMLA request form, medical certification from your doctor. Contact: your HR department; doctor for certification form"},
        {"title": "Apply for SSDI or SSI", "days_before": -14, "note": "Apply as soon as possible — processing takes months. Docs: Social Security card, birth certificate, medical records, doctor contact info, work history (last 15 years), W-2s/tax returns. Contact: SSA at 1-800-772-1213 or apply at ssa.gov"},
        {"title": "File short-term disability claim", "days_before": -7, "note": "Through your employer's insurance. Docs: claim form, attending physician's statement, proof of employment. Contact: your employer's disability insurance carrier (check with HR)"},
        {"title": "Gather medical records", "days_before": -14, "note": "Complete records strengthen your application. Docs: treatment records, test results, prescriptions, doctor's notes on functional limitations. Contact: each doctor, hospital, and specialist you've seen"},
        {"title": "SSDI initial decision expected", "days_before": -150, "note": "Average wait is 3-5 months. Contact: SSA at 1-800-772-1213 to check status, or check online at ssa.gov/myaccount"},
        {"title": "File appeal if denied", "days_before": -210, "note": "You have 60 days to appeal a denial. Docs: denial letter, additional medical evidence, attorney representation recommended. Contact: a disability attorney (most work on contingency) or your local Legal Aid"},
    ],
}

@app.route("/api/deadlines/calculate", methods=["POST"])
def calculate_deadlines():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    transition_type = data.get("transition_type", "").strip().lower()
    key_date = data.get("key_date", "").strip()  # YYYY-MM-DD
    if not transition_type or not key_date or transition_type not in DEADLINE_TEMPLATES:
        return jsonify({"error": "Valid transition type and date required"}), 400
    try:
        base = datetime.strptime(key_date, "%Y-%m-%d")
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        now = datetime.now(timezone.utc).isoformat()
        deadlines_created = []
        for tmpl in DEADLINE_TEMPLATES[transition_type]:
            # days_before > 0 means before the key date, < 0 means after
            dl_date = (base - timedelta(days=tmpl["days_before"])).strftime("%Y-%m-%d")
            db_execute(conn, f"INSERT INTO user_deadlines (user_id, transition_type, title, deadline_date, note, source, created_at) VALUES ({param},{param},{param},{param},{param},{param},{param})",
                (user["id"], transition_type, tmpl["title"], dl_date, tmpl["note"], "calculated", now))
            deadlines_created.append({"title": tmpl["title"], "deadline_date": dl_date, "note": tmpl["note"]})
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "deadlines": deadlines_created})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    source = data.get("source", "popup")
    category = data.get("transition_category")
    param = "%s" if USE_POSTGRES else "?"
    sql = f"INSERT INTO subscribers (email, source, transition_category, subscribed_at) VALUES ({param}, {param}, {param}, {param})"
    try:
        conn = get_db()
        db_execute(conn, sql, (email, source, category, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "You're on the list!"})
    except Exception as e:
        if "UNIQUE" in str(e) or "unique" in str(e) or "duplicate key" in str(e):
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
            return jsonify({"ok": True, "message": "You're already on the list!"})
        return jsonify({"error": "Something went wrong. Please try again."}), 500

@app.route("/api/subscribers/count")
def subscriber_count():
    conn = get_db()
    count = db_execute(conn, "SELECT COUNT(*) FROM subscribers WHERE unsubscribed_at IS NULL").fetchone()[0]
    conn.close()
    return jsonify({"count": count})

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

@app.route("/admin")
def admin_login_page():
    return """<!DOCTYPE html><html><head><title>Lumeway Admin</title>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
    <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'DM Sans',sans-serif;background:#F7F4EF;min-height:100vh;display:flex;align-items:center;justify-content:center}
    .login-card{background:#fff;border-radius:12px;padding:48px 40px;max-width:400px;width:100%;box-shadow:0 4px 24px rgba(0,0,0,0.08)}
    .login-card h1{font-family:'Cormorant Garamond',serif;font-size:28px;color:#1B2A38;margin-bottom:8px}
    .login-card p{color:#6E7D8A;font-size:14px;margin-bottom:24px}
    label{font-size:13px;color:#1B2A38;font-weight:500;display:block;margin-bottom:6px}
    input[type=password]{width:100%;padding:10px 14px;border:1px solid #d1cdc7;border-radius:8px;font-size:14px;font-family:'DM Sans',sans-serif;outline:none}
    input[type=password]:focus{border-color:#1B2A38}
    button{width:100%;padding:12px;background:#1B2A38;color:#fff;border:none;border-radius:8px;font-size:14px;font-family:'DM Sans',sans-serif;cursor:pointer;margin-top:16px}
    button:hover{background:#2a3d4f}
    .error{color:#c0392b;font-size:13px;margin-top:12px;display:none}
    </style></head><body>
    <div class="login-card">
      <h1>Lumeway Admin</h1>
      <p>Enter your admin key to continue.</p>
      <form onsubmit="return doLogin(event)">
        <label for="key">Admin Key</label>
        <input type="password" id="key" placeholder="Enter admin key" autofocus/>
        <button type="submit">Sign In</button>
        <p class="error" id="err">Invalid admin key. Please try again.</p>
      </form>
    </div>
    <script>
    function doLogin(e){
      e.preventDefault();
      var key=document.getElementById('key').value;
      fetch('/admin/subscribers?key='+encodeURIComponent(key)).then(function(r){
        if(r.ok){sessionStorage.setItem('admin_key',key);window.location='/admin/subscribers?key='+encodeURIComponent(key)}
        else{document.getElementById('err').style.display='block'}
      });
      return false;
    }
    </script></body></html>"""

@app.route("/admin/subscribers")
def admin_subscribers():
    key = request.args.get("key", "")
    if not ADMIN_KEY or key != ADMIN_KEY:
        return "Unauthorized", 401
    conn = get_db()
    rows = db_execute(conn, "SELECT email, source, transition_category, subscribed_at, unsubscribed_at FROM subscribers ORDER BY subscribed_at DESC").fetchall()
    conn.close()
    active_count = sum(1 for r in rows if r[4] is None)
    row_html = ""
    for r in rows:
        status = "Active" if r[4] is None else f"Unsubscribed {r[4]}"
        row_html += f"<tr><td>{r[0]}</td><td>{r[1] or ''}</td><td>{r[2] or ''}</td><td>{r[3] or ''}</td><td>{status}</td></tr>"
    return f"""<!DOCTYPE html><html><head><title>Lumeway Subscribers</title>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
    <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'DM Sans',sans-serif;background:#F7F4EF;min-height:100vh;padding:40px 20px}}
    .container{{max-width:960px;margin:0 auto}}
    h1{{font-family:'Cormorant Garamond',serif;font-size:28px;color:#1B2A38;margin-bottom:4px}}
    .count{{color:#6E7D8A;font-size:14px;margin-bottom:20px}}
    .topbar{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}}
    .logout{{color:#6E7D8A;font-size:13px;text-decoration:none;margin-left:16px}}
    .logout:hover{{color:#1B2A38}}
    .export-btn{{display:inline-block;padding:8px 16px;background:#1B2A38;color:#fff;border-radius:6px;font-size:13px;text-decoration:none}}
    .export-btn:hover{{background:#2a3d4f}}
    table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.06)}}
    th,td{{padding:10px 14px;text-align:left;font-size:13px}}
    th{{background:#1B2A38;color:#fff;font-weight:500}}
    tr:nth-child(even){{background:#faf9f7}}
    td{{border-bottom:1px solid #eee;color:#1B2A38}}
    .badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px}}
    .badge-active{{background:#e8f5e9;color:#2e7d32}}
    .badge-unsub{{background:#fce4ec;color:#c62828}}
    </style></head><body>
    <div class="container">
      <div class="topbar">
        <div><h1>Subscribers</h1><p class="count">{active_count} active subscribers</p></div>
        <div><a href="/admin/subscribers/export?key={key}" class="export-btn">Download CSV</a> <a href="/admin" class="logout">Logout</a></div>
      </div>
      <table>
        <tr><th>Email</th><th>Source</th><th>Category</th><th>Subscribed</th><th>Status</th></tr>
        {row_html}
      </table>
    </div></body></html>"""

@app.route("/admin/subscribers/export")
def admin_export_csv():
    key = request.args.get("key", "")
    if not ADMIN_KEY or key != ADMIN_KEY:
        return "Unauthorized", 401
    conn = get_db()
    rows = db_execute(conn, "SELECT email, source, transition_category, subscribed_at, unsubscribed_at FROM subscribers ORDER BY subscribed_at DESC").fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Source", "Category", "Subscribed At", "Unsubscribed At"])
    for r in rows:
        writer.writerow([r[0], r[1] or "", r[2] or "", r[3] or "", r[4] or ""])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=lumeway_subscribers_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

# ── Admin Tools (Expenses, Revenue, Analytics) ──

def check_admin():
    key = request.args.get("key", "") or request.headers.get("X-Admin-Key", "")
    if not ADMIN_KEY or key != ADMIN_KEY:
        return False
    return True

@app.route("/admin/tools")
def admin_tools():
    if not check_admin():
        return redirect("/admin")
    return send_from_directory(".", "admin-tools.html")

@app.route("/api/admin/expenses", methods=["GET"])
def admin_get_expenses():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    month = request.args.get("month")  # YYYY-MM
    if month:
        cur = db_execute(conn, f"SELECT id, date, amount_cents, category, description, payment_method, notes, created_at FROM expenses WHERE date LIKE {param} ORDER BY date DESC", (month + "%",))
    else:
        cur = db_execute(conn, "SELECT id, date, amount_cents, category, description, payment_method, notes, created_at FROM expenses ORDER BY date DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    return jsonify({"expenses": [{"id": r[0], "date": r[1], "amount_cents": r[2], "category": r[3], "description": r[4], "payment_method": r[5], "notes": r[6], "created_at": r[7]} for r in rows]})

@app.route("/api/admin/expenses", methods=["POST"])
def admin_add_expense():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    date = data.get("date", "")
    amount = data.get("amount", 0)
    category = data.get("category", "")
    description = data.get("description", "")
    payment_method = data.get("payment_method", "")
    notes = data.get("notes", "")
    if not date or not amount or not category or not description:
        return jsonify({"error": "Missing required fields"}), 400
    amount_cents = int(round(float(amount) * 100))
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    db_execute(conn, """INSERT INTO expenses (date, amount_cents, category, description, payment_method, notes, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
        """INSERT INTO expenses (date, amount_cents, category, description, payment_method, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (date, amount_cents, category, description, payment_method, notes, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/admin/expenses/<int:expense_id>", methods=["DELETE"])
def admin_delete_expense(expense_id):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM expenses WHERE id = {param}", (expense_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/admin/subscribers", methods=["GET"])
def admin_get_subscribers():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = db_execute(conn, "SELECT email, source, transition_category, subscribed_at, unsubscribed_at FROM subscribers ORDER BY subscribed_at DESC").fetchall()
    conn.close()
    return jsonify({"subscribers": [{"email": r[0], "source": r[1], "category": r[2], "subscribed_at": r[3], "unsubscribed_at": r[4]} for r in rows]})

@app.route("/api/admin/revenue-entries", methods=["GET"])
def admin_get_revenue_entries():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    cur = db_execute(conn, "SELECT id, date, amount_cents, category, description, notes, created_at FROM revenue_entries ORDER BY date DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    return jsonify({"entries": [{"id": r[0], "date": r[1], "amount_cents": r[2], "category": r[3], "description": r[4], "notes": r[5], "created_at": r[6]} for r in rows]})

@app.route("/api/admin/revenue-entries", methods=["POST"])
def admin_add_revenue_entry():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    date = data.get("date", "")
    amount = data.get("amount", 0)
    category = data.get("category", "")
    description = data.get("description", "")
    notes = data.get("notes", "")
    if not date or not amount or not category or not description:
        return jsonify({"error": "Missing required fields"}), 400
    amount_cents = int(round(float(amount) * 100))
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    db_execute(conn, """INSERT INTO revenue_entries (date, amount_cents, category, description, notes, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
        """INSERT INTO revenue_entries (date, amount_cents, category, description, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (date, amount_cents, category, description, notes, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/admin/revenue-entries/<int:entry_id>", methods=["DELETE"])
def admin_delete_revenue_entry(entry_id):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM revenue_entries WHERE id = {param}", (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/admin/pnl", methods=["GET"])
def admin_pnl():
    """YTD profit & loss broken down by category."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    year = datetime.now(timezone.utc).strftime("%Y")
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Expenses by category (YTD)
    cur = db_execute(conn, f"SELECT category, SUM(amount_cents) FROM expenses WHERE date LIKE {param} GROUP BY category ORDER BY SUM(amount_cents) DESC", (year + "%",))
    expense_cats = [{"category": r[0], "amount_cents": r[1]} for r in cur.fetchall()]
    # Manual revenue entries by category (YTD)
    cur = db_execute(conn, f"SELECT category, SUM(amount_cents) FROM revenue_entries WHERE date LIKE {param} GROUP BY category ORDER BY SUM(amount_cents) DESC", (year + "%",))
    manual_rev_cats = [{"category": r[0], "amount_cents": r[1]} for r in cur.fetchall()]
    # Dashboard/Stripe revenue by product (YTD) — only paid purchases
    cur = db_execute(conn, f"SELECT product_name, SUM(amount_cents) FROM purchases WHERE purchased_at LIKE {param} AND amount_cents > 0 GROUP BY product_name ORDER BY SUM(amount_cents) DESC", (year + "%",))
    stripe_rev_cats = [{"category": r[0], "amount_cents": r[1]} for r in cur.fetchall()]
    # Totals
    total_expenses = sum(e["amount_cents"] for e in expense_cats)
    total_manual_rev = sum(r["amount_cents"] for r in manual_rev_cats)
    total_stripe_rev = sum(r["amount_cents"] for r in stripe_rev_cats)
    total_revenue = total_manual_rev + total_stripe_rev
    conn.close()
    return jsonify({
        "year": year,
        "expenses": {"total": total_expenses, "categories": expense_cats},
        "manual_revenue": {"total": total_manual_rev, "categories": manual_rev_cats},
        "stripe_revenue": {"total": total_stripe_rev, "categories": stripe_rev_cats},
        "total_revenue": total_revenue,
        "net_profit": total_revenue - total_expenses
    })

@app.route("/api/admin/revenue", methods=["GET"])
def admin_revenue():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    # All purchases
    cur = db_execute(conn, "SELECT product_id, product_name, amount_cents, purchased_at, email FROM purchases ORDER BY purchased_at DESC")
    purchases = [{"product_id": r[0], "product_name": r[1], "amount_cents": r[2], "purchased_at": r[3], "email": r[4]} for r in cur.fetchall()]
    conn.close()
    return jsonify({"purchases": purchases})

@app.route("/api/admin/analytics", methods=["GET"])
def admin_analytics():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    # User stats
    total_users = db_execute(conn, "SELECT COUNT(*) FROM users").fetchone()[0]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    users_today = db_execute(conn, "SELECT COUNT(*) FROM users WHERE created_at LIKE %s" if USE_POSTGRES else "SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    users_this_month = db_execute(conn, "SELECT COUNT(*) FROM users WHERE created_at LIKE %s" if USE_POSTGRES else "SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (this_month + "%",)).fetchone()[0]
    # Chat stats
    total_chats = db_execute(conn, "SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
    chats_this_month = db_execute(conn, "SELECT COUNT(*) FROM chat_sessions WHERE started_at LIKE %s" if USE_POSTGRES else "SELECT COUNT(*) FROM chat_sessions WHERE started_at LIKE ?", (this_month + "%",)).fetchone()[0]
    # Checklist stats
    total_checklist_users = db_execute(conn, "SELECT COUNT(DISTINCT user_id) FROM checklist_items").fetchone()[0]
    true_val = "TRUE" if USE_POSTGRES else "1"
    total_completed = db_execute(conn, f"SELECT COUNT(*) FROM checklist_items WHERE is_completed = {true_val}").fetchone()[0]
    total_items = db_execute(conn, "SELECT COUNT(*) FROM checklist_items").fetchone()[0]
    # Purchase stats
    total_revenue = db_execute(conn, "SELECT COALESCE(SUM(amount_cents), 0) FROM purchases").fetchone()[0]
    total_purchases = db_execute(conn, "SELECT COUNT(*) FROM purchases").fetchone()[0]
    revenue_this_month = db_execute(conn, "SELECT COALESCE(SUM(amount_cents), 0) FROM purchases WHERE purchased_at LIKE %s" if USE_POSTGRES else "SELECT COALESCE(SUM(amount_cents), 0) FROM purchases WHERE purchased_at LIKE ?", (this_month + "%",)).fetchone()[0]
    # Tier breakdown
    tier_counts = {}
    for tier_name in ["free", "starter", "one_transition", "all_transitions", "pass", "unlimited"]:
        param = "%s" if USE_POSTGRES else "?"
        cnt = db_execute(conn, f"SELECT COUNT(*) FROM users WHERE tier = {param}", (tier_name,)).fetchone()[0]
        tier_counts[tier_name] = cnt
    # Expense stats
    total_expenses = db_execute(conn, "SELECT COALESCE(SUM(amount_cents), 0) FROM expenses").fetchone()[0]
    expenses_this_month = db_execute(conn, "SELECT COALESCE(SUM(amount_cents), 0) FROM expenses WHERE date LIKE %s" if USE_POSTGRES else "SELECT COALESCE(SUM(amount_cents), 0) FROM expenses WHERE date LIKE ?", (this_month + "%",)).fetchone()[0]
    # Signups by month (last 6 months)
    signups_by_month = []
    for i in range(5, -1, -1):
        d = datetime.now(timezone.utc) - timedelta(days=i*30)
        m = d.strftime("%Y-%m")
        param = "%s" if USE_POSTGRES else "?"
        cnt = db_execute(conn, f"SELECT COUNT(*) FROM users WHERE created_at LIKE {param}", (m + "%",)).fetchone()[0]
        signups_by_month.append({"month": m, "count": cnt})
    # Revenue by month (last 6 months)
    revenue_by_month = []
    for i in range(5, -1, -1):
        d = datetime.now(timezone.utc) - timedelta(days=i*30)
        m = d.strftime("%Y-%m")
        param = "%s" if USE_POSTGRES else "?"
        amt = db_execute(conn, f"SELECT COALESCE(SUM(amount_cents), 0) FROM purchases WHERE purchased_at LIKE {param}", (m + "%",)).fetchone()[0]
        revenue_by_month.append({"month": m, "amount_cents": amt})
    conn.close()
    return jsonify({
        "users": {"total": total_users, "today": users_today, "this_month": users_this_month},
        "chats": {"total": total_chats, "this_month": chats_this_month},
        "checklist": {"users": total_checklist_users, "completed": total_completed, "total": total_items},
        "revenue": {"total": total_revenue, "this_month": revenue_this_month, "purchases": total_purchases},
        "expenses": {"total": total_expenses, "this_month": expenses_this_month},
        "tiers": tier_counts,
        "signups_by_month": signups_by_month,
        "revenue_by_month": revenue_by_month
    })

@app.route("/api/admin/grant-tier", methods=["POST"])
def admin_grant_tier():
    """Admin tool: manually grant a tier to a user (for fixing failed purchases)."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    email = data.get("email", "").strip()
    tier = data.get("tier", "")
    transition = data.get("transition", "")
    create_record = data.get("create_record", False)
    valid_tiers = ("free", "starter", "pass", "unlimited", "one_transition", "all_transitions")
    if not email or tier not in valid_tiers:
        return jsonify({"error": "Invalid email or tier"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    # Look up user
    cur = db_execute(conn, f"SELECT id FROM users WHERE email = {param}", (email,))
    user_row = cur.fetchone()
    if not user_row:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    uid = user_row[0]
    if tier == "all_transitions" or tier == "unlimited":
        # Grant full access to all categories
        for cat in VALID_CATEGORIES:
            add_user_category(uid, cat, "full")
        update_user_tier_from_access(uid)
    elif tier == "one_transition" or tier == "pass":
        # Grant full access to one category
        cat = transition if transition in VALID_CATEGORIES else "job-loss"
        add_user_category(uid, cat, "full")
        update_user_tier_from_access(uid)
    elif tier == "starter":
        # Grant starter access to one category
        cat = transition if transition in VALID_CATEGORIES else "job-loss"
        add_user_category(uid, cat, "starter")
        update_user_tier_from_access(uid)
    else:
        db_execute(conn, f"UPDATE users SET tier = 'free', tier_transition = NULL, tier_expires_at = NULL, stripe_customer_id = NULL, active_transitions = '[]' WHERE email = {param}", (email,))
    conn.commit()
    conn.close()
    # Optionally create a purchase record (use fresh connection)
    record_msg = ""
    if create_record and tier in ("pass", "unlimited", "one_transition", "all_transitions"):
        now = datetime.now(timezone.utc).isoformat()
        token = secrets.token_urlsafe(32)
        if tier in ("pass", "one_transition"):
            pass_id = "pass-" + (transition or "estate")
            product = PASS_PRODUCTS.get(pass_id, {})
            product_name = product.get("name", f"{transition.title()} Full Plan")
            amount_cents = product.get("price", 3900)
        elif tier in ("unlimited", "all_transitions"):
            pass_id = "all-transitions"
            product_name = "All Transitions"
            amount_cents = 12500
        else:
            pass_id = "unknown"
            product_name = "Unknown"
            amount_cents = 0
        try:
            conn2 = get_db()
            db_execute(conn2, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
                """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (email, pass_id, product_name, amount_cents, "manual-grant-" + now, None, now, token, True if USE_POSTGRES else 1))
            # Also grant template bundle downloads
            bundles_to_grant = []
            if tier in ("pass", "one_transition") and transition and transition in BUNDLE_FILES:
                bundles_to_grant = [transition]
            elif tier in ("unlimited", "all_transitions"):
                bundles_to_grant = [k for k in BUNDLE_FILES.keys() if k != "master"]
            for bid in bundles_to_grant:
                bp = PRODUCTS.get(bid, {})
                bt = secrets.token_urlsafe(32)
                db_execute(conn2, """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES else
                    """INSERT INTO purchases (email, product_id, product_name, amount_cents, stripe_session_id, stripe_payment_intent, purchased_at, download_token, fulfilled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (email, bid, bp.get("name", f"{bid.title()} Bundle"), 0, "manual-bundle-" + bid + "-" + now, None, now, bt, True if USE_POSTGRES else 1))
            conn2.commit()
            conn2.close()
            record_msg = ", purchase record created"
            print(f"Purchase record created for {email}: {product_name}")
        except Exception as e:
            record_msg = f", purchase record FAILED: {e}"
            print(f"Error creating purchase record: {e}")
    return jsonify({"ok": True, "message": f"User {email} set to tier={tier}{record_msg}"})

@app.route("/api/admin/create-gift-code", methods=["POST"])
def admin_create_gift_code():
    """Admin tool: create a gift code for testing."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    gift_type = data.get("gift_type", "all_transitions")
    transition_category = data.get("transition_category", "")
    code = data.get("code", "").strip().upper() or generate_gift_code()
    if gift_type == "all_transitions":
        label = "All Access — All Transitions"
    elif transition_category and transition_category in CATEGORY_LABELS:
        label = f"Bundled Plan — {CATEGORY_LABELS[transition_category]}"
    else:
        label = "Bundled Plan — One Transition"
    amount = 12500 if gift_type == "all_transitions" else 3900
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    try:
        db_execute(conn, f"""INSERT INTO gift_codes (code, purchaser_email, purchaser_name, recipient_name, gift_type, gift_label, amount_cents, stripe_session_id, transition_category, created_at)
            VALUES ({param},{param},{param},{param},{param},{param},{param},{param},{param},{param})""",
            (code, "admin@lumeway.co", "Admin", "", gift_type, label, amount, "admin-test", transition_category, now))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500
    conn.close()
    return jsonify({"ok": True, "code": code, "gift_type": gift_type, "transition_category": transition_category, "label": label})

@app.route("/api/admin/delete-purchase", methods=["POST"])
def admin_delete_purchase():
    """Admin tool: delete a purchase record by stripe_session_id."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    session_id = data.get("session_id", "").strip()
    if not session_id:
        return jsonify({"error": "session_id required"}), 400
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"DELETE FROM purchases WHERE stripe_session_id = {param}", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/admin/retry-purchase", methods=["POST"])
def admin_retry_purchase():
    """Admin tool: re-process a Stripe checkout session to create missing purchase records."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    session_id = data.get("session_id", "").strip()
    if not session_id:
        return jsonify({"error": "session_id required"}), 400
    try:
        session_data = stripe.checkout.Session.retrieve(session_id)
        if session_data.payment_status != "paid":
            return jsonify({"error": "Session not paid"}), 400
        metadata = session_data.metadata if isinstance(session_data.metadata, dict) else dict(session_data.metadata or {})
        purchase_type = metadata.get("purchase_type", "")
        if purchase_type in ("pass", "unlimited"):
            handle_tier_upgrade(session_data, metadata)
        else:
            fulfill_purchase(session_data)
        return jsonify({"ok": True, "message": "Purchase re-processed"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export", methods=["POST"])
def export_checklist():
    try:
        import json as _json
        data = request.json
        history = data.get("history", [])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system="""You are extracting structured data from a Lumeway conversation. Return ONLY valid JSON — no markdown, no explanation.

Extract the user's situation and all tasks discussed. Use this exact structure:
{
  "situation": "One sentence describing the user's transition (e.g. 'Job loss in Illinois, two children, happened this week')",
  "tasks": [
    {
      "number": 1,
      "title": "Task title",
      "why": "One sentence why this matters",
      "steps": ["Step 1", "Step 2", "Step 3"],
      "timeNeeded": "30 minutes",
      "deadline": "File within 2 weeks"
    }
  ]
}

If a field is unknown, use null. Always return valid JSON.""",
            messages=[{"role": "user", "content": "Extract tasks from this conversation:\n\n" + _json.dumps(history)}]
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return jsonify(_json.loads(text))
    except Exception as e:
        print(f"Export error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/template-idea", methods=["POST"])
def save_template_idea():
    try:
        data = request.json
        idea = data.get("idea", "").strip()
        session_id = data.get("session_id")
        if not idea:
            return jsonify({"error": "No idea provided"}), 400
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        param = "%s" if USE_POSTGRES else "?"
        db_execute(conn, f"INSERT INTO template_ideas (session_id, idea, created_at) VALUES ({param},{param},{param})", (session_id, idea, now))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        print(f"Template idea error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/research", methods=["POST"])
def research_api():
    try:
        data = request.json
        topic = data.get("topic", "")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system="You are a market research agent for Lumeway, an AI life-transition guide that helps people navigate bureaucratic and logistical tasks during major life transitions. Find realistic examples of posts where people are overwhelmed by PAPERWORK, DEADLINES, TASKS, and BUREAUCRACY — not grief, loneliness, or emotional struggles. Good examples: 'I have no idea what forms to file after my husband died', 'What do I do first after getting laid off?', 'SSDI denied me, what are my next steps?', 'I have 30 days to figure out COBRA, health insurance, 401k rollover — where do I start?'. Bad examples: posts about loneliness, depression, emotional healing, or relationship advice. Return ONLY a JSON array with exactly 4 results. Each result must have: topic (transition category), title (realistic post title showing logistical overwhelm), community (subreddit like r/widowers, r/personalfinance, r/layoffs), url (empty string), summary (2-3 sentences about the specific tasks or deadlines they are confused by), painPoints (array of 3 specific logistical pain points — forms, deadlines, agencies, accounts), opportunityScore (number 1-10 based on how much Lumeway could help), engagementHint (why this post gets engagement). Return ONLY the JSON array, no other text.",
            messages=[{"role": "user", "content": "Find realistic examples of online conversations where people struggle with: " + topic}]
        )
        full_text = "".join([block.text for block in response.content if hasattr(block, "text")])
        return jsonify({"result": full_text})
    except Exception as e:
        print(f"Research API error: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
@app.route("/api/draft-reply", methods=["POST"])
def draft_reply_api():
    try:
        data = request.json
        community = data.get("community", "")
        title = data.get("title", "")
        summary = data.get("summary", "")
        pain_points = data.get("painPoints", [])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system="You are helping the founder of Lumeway (lumeway.co) draft replies to people overwhelmed by logistical tasks during life transitions. Rules: One sentence of empathy, then immediately tell them the single most important thing to do first and why. Be specific — name the exact form, agency, or deadline. Two short paragraphs max. Always mention Lumeway at the end with one specific sentence about what it would do for their exact situation — for example 'Lumeway can walk you through each of these steps in order and draft the letter to your creditors if you need it' or 'Lumeway was built for exactly this — it will tell you what to file first and flag the deadlines you can't miss. You can try it free at lumeway.co.' Never generic. Under 100 words. Plain text only.",
            messages=[{"role": "user", "content": "Draft a helpful reply to this post:\nCommunity: " + community + "\nTitle: " + title + "\nSummary: " + summary + "\nPain points: " + ", ".join(pain_points)}]
        )
        reply = response.content[0].text
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Draft reply error: {str(e)}")
        return jsonify({"error": str(e)}), 500
BOUNDARY_KEYWORDS = {
    "legal": [
        "custody agreement", "severance agreement", "qdro", "file in my state",
        "legal document", "power of attorney", "what should i put in",
        "help me fill out", "draft this for me", "clause in my",
        "is my lawyer right", "do you agree with my lawyer",
    ],
    "financial": [
        "roll over my 401k", "how much child support", "how much alimony",
        "tax implications", "should i accept the settlement",
        "investment", "cash it out", "how much will i get",
    ],
    "medical": [
        "should i take", "diagnose", "medication", "dosage",
        "what treatment", "therapy technique",
        "detox protocol", "which rehab", "what medication for addiction",
    ],
    "form_completion": [
        "help me fill out", "complete this form", "fill in this",
        "write this document", "help me write",
    ],
    "crisis": [
        "kill myself", "want to die", "end it all", "suicide",
        "self-harm", "hurt myself", "no reason to live",
    ],
}


def detect_boundary_category(message):
    lower = message.lower()
    for category, keywords in BOUNDARY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return category
    return None


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "")
        history = data.get("history", [])
        session_id = data.get("session_id")
        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        if not session_id:
            session_id = conversation_log.log_session_start()
            # Also create a chat_sessions row for dashboard
            now = datetime.now(timezone.utc).isoformat()
            user = get_current_user()
            user_id = user["id"] if user else None
            try:
                conn = get_db()
                param = "%s" if USE_POSTGRES else "?"
                db_execute(conn, f"INSERT INTO chat_sessions (id, user_id, started_at) VALUES ({param}, {param}, {param})", (session_id, user_id, now))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error creating chat_session: {e}")

        messages = history + [{"role": "user", "content": user_message}]

        boundary_cat = detect_boundary_category(user_message)

        # Build system prompt — add user context if logged in
        chat_system_prompt = SYSTEM_PROMPT
        user = get_current_user()
        if user:
            try:
                transition_labels = {
                    "job-loss": "job loss", "estate": "loss of a loved one", "divorce": "divorce or separation",
                    "disability": "disability", "relocation": "relocation", "retirement": "retirement", "addiction": "addiction recovery"
                }
                tier = user.get("tier", "free")
                us_state = user.get("us_state", "")
                transition_type = user.get("transition_type", "")
                display_name = user.get("display_name", "")
                active_transitions = user.get("active_transitions") or []
                if isinstance(active_transitions, str):
                    try:
                        import json as _json
                        active_transitions = _json.loads(active_transitions)
                    except Exception:
                        active_transitions = []
                # Normalize: items might be dicts like {"cat": "job-loss"} or strings
                active_cats = [t["cat"] if isinstance(t, dict) else t for t in active_transitions]
                active_labels = [transition_labels.get(c, c) for c in active_cats]

                # Check onboarding source
                onboarding_source = None
                try:
                    conn_ctx = get_db()
                    param_ctx = "%s" if USE_POSTGRES else "?"
                    cur_ctx = db_execute(conn_ctx, f"SELECT onboarding_source FROM users WHERE id = {param_ctx}", (user["id"],))
                    ctx_row = cur_ctx.fetchone()
                    if ctx_row:
                        onboarding_source = ctx_row[0]
                    conn_ctx.close()
                except Exception:
                    pass

                # Build context block
                context_parts = ["\n\nUSER CONTEXT (do not repeat this verbatim, just use it to personalize your responses):"]

                if display_name:
                    context_parts.append(f"- Name: {display_name}")

                if us_state:
                    context_parts.append(f"- State: {us_state}. Use this for state-specific legal deadlines, filing requirements, and resources. Do NOT ask what state they're in — you already know.")

                # Also check transition_type as fallback
                if not active_labels and transition_type and transition_type in transition_labels:
                    active_cats = [transition_type]
                    active_labels = [transition_labels[transition_type]]

                if tier == "all_transitions":
                    context_parts.append("- All Access: They have access to all transition types (job loss, estate/loss of a loved one, divorce, disability, relocation, retirement). Ask which transition they're navigating if it's not clear from context. Then offer help with specific areas relevant to that transition — insurance, finances, legal paperwork, housing, benefits, etc.")
                elif active_labels:
                    context_parts.append(f"- Active transitions: {', '.join(active_labels)}")
                    context_parts.append(f"- They have a paid bundle for {', '.join(active_labels)}. Offer to help with specific areas relevant to their transition — insurance, finances, legal paperwork, housing, benefits, etc.")

                if tier == "free" and not active_labels:
                    context_parts.append("- Free tier. Be helpful but don't oversell — they may upgrade on their own.")
                elif tier == "all_transitions":
                    context_parts.append("- All Access tier — they have access to everything.")
                elif active_labels and tier not in ("free", "all_transitions"):
                    context_parts.append(f"- Bundled Plan tier for: {', '.join(active_labels)}.")

                if onboarding_source == "gift":
                    context_parts.append("- This user received Lumeway as a gift. They may be brand new. Be extra warm and welcoming. If this seems like their first message, acknowledge the gift and help them get started with their bundle. Keep it conversational and low-pressure — they may be going through a hard time.")

                if len(context_parts) > 1:
                    chat_system_prompt += "\n".join(context_parts)
                    print(f"[chat-context] user={user.get('email')}, tier={tier}, transitions={active_cats}, state={us_state}, source={onboarding_source}")
            except Exception as e:
                print(f"[chat-context] Error building context: {e}")
                import traceback
                traceback.print_exc()

        def generate():
            full_reply = ""
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=chat_system_prompt,
                messages=messages
            ) as stream:
                for text in stream.text_stream:
                    full_reply += text
                    newline = chr(10)
                    yield f"data: {text.replace(newline, chr(92) + 'n')}\n\n"

            if boundary_cat:
                summary = full_reply[:300] if len(full_reply) > 300 else full_reply
                conversation_log.log_boundary_redirection(
                    session_id, user_message, boundary_cat, summary
                )

            if boundary_cat == "crisis":
                conversation_log.update_session(session_id, crisis_resources_provided=1)

            reply_lower = full_reply.lower()
            if "just so you know" in reply_lower and "transition navigator" in reply_lower:
                conversation_log.update_session(session_id, disclaimer_displayed=1)

            # Persist messages to chat_messages table
            try:
                now = datetime.now(timezone.utc).isoformat()
                conn = get_db()
                param = "%s" if USE_POSTGRES else "?"
                db_execute(conn, f"INSERT INTO chat_messages (session_id, role, content, created_at) VALUES ({param},{param},{param},{param})", (session_id, "user", user_message, now))
                db_execute(conn, f"INSERT INTO chat_messages (session_id, role, content, created_at) VALUES ({param},{param},{param},{param})", (session_id, "assistant", full_reply, now))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error saving chat messages: {e}")

            updated_history = messages + [{"role": "assistant", "content": full_reply}]
            yield f"data: [DONE]{json.dumps({'history': updated_history, 'session_id': session_id})}\n\n"

        return Response(generate(), mimetype="text/event-stream")
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/<session_id>/end", methods=["POST"])
def end_session(session_id):
    try:
        data = request.json or {}
        transition_category = data.get("transition_category")
        user_state = data.get("user_state")
        templates_mentioned = data.get("templates_mentioned")

        if transition_category:
            conversation_log.update_session(session_id, transition_category=transition_category)
        if user_state:
            conversation_log.update_session(session_id, user_state=user_state)
        if templates_mentioned:
            conversation_log.update_session(session_id, templates_mentioned=templates_mentioned)

        conversation_log.log_session_end(session_id)
        session = conversation_log.get_session(session_id)
        return jsonify({"status": "ok", "session": session})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/<session_id>", methods=["GET"])
def get_session(session_id):
    try:
        session = conversation_log.get_session(session_id)
        if not session:
            return jsonify({"error": "Session not found"}), 404
        events = conversation_log.get_boundary_events(session_id)
        return jsonify({"session": session, "boundary_events": events})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions/flagged", methods=["GET"])
def flagged_sessions():
    try:
        sessions = conversation_log.get_flagged_sessions()
        return jsonify({"sessions": sessions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
# ── User feedback ──

@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """Accept feedback from any user (logged in or not)."""
    data = request.get_json()
    area = (data.get("area") or "").strip()
    message = (data.get("message") or "").strip()
    rating = data.get("rating")
    page_url = (data.get("page_url") or "").strip()
    email = (data.get("email") or "").strip()

    if not area or not message:
        return jsonify({"error": "Area and message are required"}), 400
    if area not in ("site", "templates", "dashboard", "chat", "guides", "other"):
        return jsonify({"error": "Invalid area"}), 400
    if rating is not None:
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                rating = None
        except (ValueError, TypeError):
            rating = None

    user = get_current_user()
    user_id = user["id"] if user else None
    if user and not email:
        email = user.get("email", "")

    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    now = datetime.now(timezone.utc).isoformat()
    db_execute(conn, f"""INSERT INTO user_feedback (user_id, email, area, rating, message, page_url, created_at)
        VALUES ({param},{param},{param},{param},{param},{param},{param})""",
        (user_id, email, area, rating, message, page_url, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/feedback", methods=["GET"])
def admin_get_feedback():
    """Admin: view all feedback."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = db_execute(conn, "SELECT * FROM user_feedback ORDER BY created_at DESC").fetchall()
    conn.close()
    feedback = []
    for r in rows:
        feedback.append({
            "id": r["id"], "user_id": r["user_id"], "email": r["email"],
            "area": r["area"], "rating": r["rating"], "message": r["message"],
            "page_url": r["page_url"], "created_at": r["created_at"]
        })
    return jsonify({"feedback": feedback})


# ── Cron endpoint: process email queue ──
CRON_SECRET = os.environ.get("CRON_SECRET", "lumeway-cron-2026")

@app.route("/api/cron/send-emails", methods=["POST"])
def cron_send_emails():
    """Process due emails from the queue. Called by Railway cron or manual trigger."""
    # Simple secret check to prevent public abuse
    secret = request.headers.get("X-Cron-Secret") or request.args.get("secret")
    if secret != CRON_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"

    try:
        cur = db_execute(conn, f"SELECT id, to_email, subject, html_body FROM email_queue WHERE sent_at IS NULL AND send_after <= {param} ORDER BY send_after LIMIT 10", (now,))
        due_emails = cur.fetchall()
    except Exception as e:
        print(f"Error fetching email queue: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500

    sent_count = 0
    error_count = 0
    for row in due_emails:
        email_id, to_email, subject, html_body = row[0], row[1], row[2], row[3]
        success = send_email_via_resend(to_email, subject, html_body)
        if success:
            db_execute(conn, f"UPDATE email_queue SET sent_at = {param} WHERE id = {param}", (now, email_id))
            sent_count += 1
        else:
            db_execute(conn, f"UPDATE email_queue SET error = {param} WHERE id = {param}", (f"Failed at {now}", email_id))
            error_count += 1

    conn.commit()
    conn.close()
    print(f"Cron: sent {sent_count} emails, {error_count} errors, {len(due_emails)} processed")
    return jsonify({"sent": sent_count, "errors": error_count, "processed": len(due_emails)})


@app.route("/api/cron/reengagement", methods=["POST"])
def cron_reengagement():
    """Check for inactive users and queue a gentle re-engagement email. Run daily."""
    secret = request.headers.get("X-Cron-Secret") or request.args.get("secret")
    if secret != CRON_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    now = datetime.now(timezone.utc)
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"

    # Find users who: have a purchase/tier, last logged in 7-30 days ago, haven't already gotten this email
    try:
        cur = db_execute(conn, f"""SELECT u.id, u.email, u.display_name, u.transition_type
            FROM users u
            WHERE u.last_login_at IS NOT NULL
            AND u.last_login_at < {param}
            AND u.last_login_at > {param}
            AND u.tier != 'free'
            AND u.email NOT IN (
                SELECT to_email FROM email_queue WHERE sequence_name = 'reengagement' AND created_at > {param}
            )""", (cutoff_7d, cutoff_30d, cutoff_30d))
        inactive_users = cur.fetchall()
    except Exception as e:
        print(f"Error checking inactive users: {e}")
        conn.close()
        return jsonify({"error": str(e)}), 500

    queued = 0
    dashboard_url = "https://lumeway.co/dashboard"
    for row in inactive_users:
        user_id, email, name, transition = row[0], row[1], row[2], row[3]
        greeting = f"Hi {name}," if name else "Hi there,"
        html_body = email_wrap(f"""
<p style="{_e_hi}">{greeting}</p>
<p style="{_e_p}">It has been a little while since you logged into Lumeway. That is completely okay — life gets overwhelming, especially during a transition.</p>
<p style="{_e_p}">Your dashboard is still here, exactly where you left it. If you have been putting something off, picking one small task can help build momentum again.</p>
{_e_btn(dashboard_url, 'Pick up where you left off')}
<p style="{_e_muted}">If something is not working or you need help, just reply to this email.</p>""")

        send_after = (now + timedelta(hours=1)).isoformat()
        try:
            db_execute(conn, f"""INSERT INTO email_queue
                (to_email, subject, html_body, sequence_name, sequence_step, send_after, created_at)
                VALUES ({param},{param},{param},{param},{param},{param},{param})""",
                (email, "Your dashboard is waiting for you", html_body, "reengagement", 1, send_after, now.isoformat()))
            queued += 1
        except Exception as e:
            print(f"Error queuing reengagement for {email}: {e}")

    conn.commit()
    conn.close()
    print(f"Reengagement: queued {queued} emails for {len(inactive_users)} inactive users")
    return jsonify({"queued": queued, "checked": len(inactive_users)})


@app.route("/api/admin/email-queue", methods=["GET"])
def admin_email_queue():
    """View scheduled and sent emails."""
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    cur = db_execute(conn, "SELECT id, to_email, subject, sequence_name, sequence_step, send_after, sent_at, error, created_at FROM email_queue ORDER BY created_at DESC LIMIT 100")
    rows = cur.fetchall()
    conn.close()
    emails = []
    for r in rows:
        emails.append({
            "id": r[0], "to_email": r[1], "subject": r[2],
            "sequence_name": r[3], "sequence_step": r[4],
            "send_after": r[5], "sent_at": r[6], "error": r[7], "created_at": r[8]
        })
    return jsonify({"emails": emails})


if __name__ == "__main__":
    print("\n✓ Lumeway is running!")
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
