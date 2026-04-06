from flask import Flask, request, jsonify, send_from_directory, send_file, Response, render_template_string, redirect, session as flask_session
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
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
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
    """Get or create file encryption key. In production, use a KMS."""
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".file_encryption_key")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
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
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(hours=24)
CORS(app)


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
    conn.commit()
    conn.close()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "re_17DAfkrF_3mB4pCdStfmYHiNQoeKrxaWe")

def send_purchase_email(to_email, product_id, product_name, download_token):
    """Send purchase confirmation with download link via Resend."""
    if not RESEND_API_KEY:
        print(f"RESEND_API_KEY not set, skipping email to {to_email}")
        return False
    download_url = f"https://lumeway.co/download/{download_token}"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:system-ui,-apple-system,sans-serif;color:#1B2A38;max-width:560px;margin:0 auto;padding:32px 24px;">
<div style="text-align:center;margin-bottom:32px;">
  <span style="font-family:Georgia,serif;font-size:24px;color:#1B3A5C;font-weight:500;">Lumeway</span>
</div>
<p style="font-size:16px;line-height:1.6;">Hi there,</p>
<p style="font-size:16px;line-height:1.6;">Thank you for your purchase! Your <strong>{product_name}</strong> is ready to download.</p>
<div style="text-align:center;margin:32px 0;">
  <a href="{download_url}" style="display:inline-block;padding:14px 32px;background:#1B3A5C;color:white;text-decoration:none;border-radius:100px;font-size:15px;font-weight:500;">Download Your Templates</a>
</div>
<p style="font-size:14px;color:#6E7D8A;line-height:1.6;">This link is unique to your purchase and does not expire.</p>
<p style="font-size:14px;color:#6E7D8A;line-height:1.6;">If you have any questions, just reply to this email.</p>
<hr style="border:none;border-top:1px solid #E4DDD3;margin:32px 0;" />
<p style="font-size:13px;color:#6E7D8A;">Warmly,<br>The Lumeway Team<br><a href="https://lumeway.co" style="color:#1B3A5C;">lumeway.co</a></p>
<p style="font-size:11px;color:#999;margin-top:24px;">Lumeway provides organizational tools, not legal or financial advice. Always consult a qualified professional for decisions specific to your situation.</p>
</body></html>"""
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

init_subscribers_db()
os.makedirs("uploads", exist_ok=True)

client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

conversation_log.init_db()

# ── Auth helpers ──

def get_current_user():
    """Return user dict if logged in, else None."""
    user_id = flask_session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    cur = db_execute(conn, f"SELECT id, email, display_name, transition_type, us_state, created_at, last_login_at FROM users WHERE id = {param}", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        cols = ["id", "email", "display_name", "transition_type", "us_state", "created_at", "last_login_at"]
        return dict(zip(cols, row))
    return None

def send_auth_code(to_email, code):
    """Send login code via Resend."""
    if not RESEND_API_KEY:
        print(f"RESEND_API_KEY not set, skipping auth code to {to_email}")
        return False
    html = f"""<!DOCTYPE html>
<html><body style="font-family:system-ui,-apple-system,sans-serif;color:#1B2A38;max-width:560px;margin:0 auto;padding:32px 24px;">
<div style="text-align:center;margin-bottom:32px;">
  <span style="font-family:Georgia,serif;font-size:24px;color:#1B3A5C;font-weight:500;">Lumeway</span>
</div>
<p style="font-size:16px;line-height:1.6;">Your login code is:</p>
<div style="text-align:center;margin:24px 0;">
  <span style="font-size:36px;font-weight:600;letter-spacing:8px;color:#1B3A5C;">{code}</span>
</div>
<p style="font-size:14px;color:#6E7D8A;line-height:1.6;">This code expires in 10 minutes. If you didn't request this, you can ignore this email.</p>
<hr style="border:none;border-top:1px solid #E4DDD3;margin:32px 0;" />
<p style="font-size:13px;color:#6E7D8A;">Lumeway<br><a href="https://lumeway.co" style="color:#1B3A5C;">lumeway.co</a></p>
</body></html>"""
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
Job Loss, Estate & Survivor, Divorce, Disability, Relocation, Retirement

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

QUICK-REPLY BUTTONS:
When your message ends with a question that has a small set of clear answer
options (2-6 choices), append a special tag on the LAST line of your response:

[QUICK_REPLIES: Option A | Option B | Option C]

Rules:
- Use this whenever you ask a yes/no question, or present a short list of
  choices the user can pick from.
- Keep each option SHORT (1-6 words). These become clickable buttons.
- Maximum 6 options. If there are more possibilities, omit the tag and let
  the user type freely.
- Always include an "Other" or "Something else" option when the choices
  might not cover every situation.
- Do NOT use this tag when asking open-ended questions (e.g., "What state
  are you in?" or "Tell me more about your situation").
- The tag must be on its own line at the very end of your message.

Examples:
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
    "loss-of-spouse": ["Estate", "Death", "Loss of Spouse", "Grief"],
    "divorce": ["Divorce", "Separation"],
    "job-loss": ["Job Loss", "Job Loss Worksheet", "Unemployment", "COBRA"],
    "relocation": ["Relocation", "Moving"],
    "disability": ["Disability", "Benefits"],
    "retirement": ["Retirement"],
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
    return inject_related_posts("estate.html", TRANSITION_CATEGORIES["loss-of-spouse"])

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
    "master": {"name": "Life Transition Bundle", "price": 3600, "desc": "All 6 category bundles — 90 documents",
        "headline": "Every Transition. Every Template. One Download.",
        "emoji": "📦", "count": "90",
        "long_desc": "Everything Lumeway offers in one package. All six category bundles covering job loss, estate settlement, divorce, disability, relocation, and retirement — 90 documents plus bonus wellness worksheets.",
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
}

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
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "templates#" + product_id,
            metadata={"product_id": product_id},
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    # Send email in background thread so it doesn't block the response
    threading.Thread(target=send_purchase_email, args=(email, product_id, product["name"], token), daemon=True).start()
    print(f"Email send initiated for {email}")

@app.route("/purchase-success")
def purchase_success():
    session_id = request.args.get("session_id")
    print(f"Purchase success page hit, session_id={session_id}")
    if session_id:
        try:
            session_data = stripe.checkout.Session.retrieve(session_id)
            print(f"Session retrieved: payment_status={session_data.payment_status}, metadata={session_data.metadata}")
            if session_data.payment_status == "paid":
                product_id = session_data.metadata.get("product_id", "") if isinstance(session_data.metadata, dict) else getattr(session_data.metadata, "product_id", "")
                product = PRODUCTS.get(product_id, {})
                # Check if already fulfilled (webhook may have handled it)
                conn = get_db()
                cur = db_execute(conn, "SELECT download_token FROM purchases WHERE stripe_session_id = %s" if USE_POSTGRES else "SELECT download_token FROM purchases WHERE stripe_session_id = ?", (session_id,))
                row = cur.fetchone()
                conn.close()
                if not row:
                    print(f"No existing purchase found, fulfilling now...")
                    fulfill_purchase(session_data)
                else:
                    print(f"Purchase already exists in DB, token={row[0]}")
                    # Resend email in case it failed before
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
    item_type = data.get("type")  # "bundle" or "individual"
    if not product_id or not name or price is None or item_type not in ("bundle", "individual"):
        return jsonify({"error": "Missing or invalid fields"}), 400
    cart = flask_session.get("cart", [])
    # Prevent duplicates
    for item in cart:
        if item["product_id"] == product_id:
            return jsonify({"items": cart, "message": "Already in cart"})
    cart.append({"product_id": product_id, "name": name, "price": price, "type": item_type})
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
    line_items = []
    for item in cart:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {"name": item["name"]},
                "unit_amount": int(item["price"] * 100),
            },
            "quantity": 1,
        })
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=request.host_url + "purchase-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "cart",
            metadata={"product_ids": ",".join(item["product_id"] for item in cart)},
        )
        flask_session["cart"] = []
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        ("https://lumeway.co/loss-of-spouse", "weekly", "0.9"),
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
        cat_match = re.search(r'class="[^"]*category-tag[^"]*"[^>]*>(.*?)</span>', raw, re.DOTALL)
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
      'Estate': ('/loss-of-spouse', 'Death & Estate Guide'),
      'Death': ('/loss-of-spouse', 'Death & Estate Guide'),
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
    db_execute(conn, f"INSERT INTO auth_codes (email, code, created_at, expires_at) VALUES ({param}, {param}, {param}, {param})", (email, code, now, expires))
    conn.commit()
    conn.close()

    if not send_auth_code(email, code):
        return jsonify({"error": "Failed to send code. Please try again."}), 500

    return jsonify({"ok": True, "message": "Code sent! Check your email."})

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

    # Claim anonymous chat session if provided
    if claim_session_id:
        db_execute(conn, f"UPDATE chat_sessions SET user_id = {param} WHERE id = {param} AND user_id IS NULL", (user_id, claim_session_id))

    conn.commit()
    conn.close()

    # Set session cookie
    flask_session["user_id"] = user_id
    flask_session.permanent = True

    audit_log(user_id, "login", "user", str(user_id), email)

    return jsonify({"ok": True, "is_new": is_new, "user_id": user_id})

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    flask_session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/me")
def auth_me():
    user = get_current_user()
    if not user:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "user": user})

# ── Dashboard routes ──


@app.route("/api/account/settings", methods=["POST"])
def update_account_settings():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json or {}
    display_name = data.get("display_name", "").strip()[:100]
    us_state = data.get("us_state", "").strip()[:5]
    conn = get_db()
    param = "%s" if USE_POSTGRES else "?"
    db_execute(conn, f"UPDATE users SET display_name = {param}, us_state = {param} WHERE id = {param}",
               (display_name or None, us_state or None, user["id"]))
    conn.commit()
    conn.close()
    audit_log(user["id"], "settings_update", "user", str(user["id"]), f"name={display_name}, state={us_state}")
    return jsonify({"ok": True})

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

    conn.close()
    return jsonify({
        "user": user,
        "sessions": sessions,
        "checklist": {"total": total_items, "completed": completed_items},
        "purchases": purchases,
        "goals": goals,
        "deadlines": deadlines,
        "documents_needed": documents_needed,
        "notes": notes
    })

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

DEFAULT_CHECKLISTS = {
    "estate": {
        "First 24 Hours": [
            "Obtain the death certificate (request 10+ certified copies)",
            "Notify immediate family and close friends",
            "Contact the funeral home or cremation service",
            "Secure the deceased's home and property",
            "Locate the will and any estate planning documents",
        ],
        "First Week": [
            "Notify the deceased's employer and request final paycheck",
            "Contact Social Security Administration (1-800-772-1213)",
            "Notify banks and financial institutions",
            "Contact life insurance companies to file claims",
            "Notify the post office to forward mail",
            "Contact utility companies about accounts",
        ],
        "First Month": [
            "Meet with an estate attorney if needed",
            "File for probate if required",
            "Apply for survivor benefits (Social Security, VA, pension)",
            "Transfer vehicle titles",
            "Update property deeds if applicable",
            "Notify credit agencies (Equifax, Experian, TransUnion)",
            "Cancel subscriptions and memberships",
        ],
        "Ongoing": [
            "File the deceased's final tax return",
            "Distribute assets according to the will",
            "Close remaining accounts",
            "Keep records of all estate transactions",
        ],
    },
    "divorce": {
        "First 24 Hours": [
            "Secure copies of all important financial documents",
            "Open individual bank account if you don't have one",
            "Document all shared assets and debts",
            "Change passwords on personal accounts",
            "Consult with a family law attorney",
        ],
        "First Week": [
            "Gather tax returns from the last 3 years",
            "List all joint accounts (bank, credit cards, investments)",
            "Review and understand your household budget",
            "Research local family law attorneys (consultations are often free)",
            "Understand your state's divorce filing requirements",
        ],
        "First Month": [
            "File for divorce or respond to petition if served",
            "Request temporary orders if needed (custody, support, exclusive use)",
            "Begin the asset and property inventory",
            "Understand how retirement accounts will be divided (QDRO)",
            "Set up mail forwarding if moving out",
            "Update beneficiaries on insurance policies",
        ],
        "Ongoing": [
            "Attend all court dates and mediation sessions",
            "Keep detailed records of all expenses",
            "Update your estate plan (will, power of attorney)",
            "Establish credit in your own name",
            "Update your name on documents if applicable",
        ],
    },
    "job-loss": {
        "First 24 Hours": [
            "Review your severance agreement (don't sign immediately)",
            "File for unemployment benefits",
            "Understand your COBRA health insurance options",
            "Secure copies of important work documents and contacts",
            "Review your last paycheck for accuracy",
        ],
        "First Week": [
            "Create a detailed budget based on reduced income",
            "Review your 401(k) options (leave it, roll over, or cash out)",
            "Update your resume and LinkedIn profile",
            "Apply for any applicable state or local assistance programs",
            "Contact creditors if you anticipate payment difficulties",
        ],
        "First Month": [
            "Decide on COBRA vs. marketplace health insurance",
            "Begin active job searching",
            "Consider whether to roll over your 401(k) to an IRA",
            "Cut non-essential expenses",
            "File for any applicable tax credits or deductions",
        ],
        "Ongoing": [
            "Maintain a record of all job applications",
            "Network actively — attend events, reach out to contacts",
            "Consider skills training or certifications",
            "Monitor your unemployment benefits and renew if needed",
        ],
    },
    "relocation": {
        "First 24 Hours": [
            "Research your new state's requirements (license, registration, voting)",
            "Create a moving timeline and checklist",
            "Get quotes from moving companies or plan a DIY move",
            "Notify your landlord or list your home for sale",
            "Research schools in the new area if applicable",
        ],
        "First Week": [
            "Set up mail forwarding through USPS",
            "Transfer or set up utilities at new address",
            "Notify your employer and update payroll address",
            "Transfer medical records and find new healthcare providers",
            "Update address with banks and financial institutions",
        ],
        "First Month": [
            "Get a new driver's license in your new state",
            "Register your vehicle in the new state",
            "Register to vote at your new address",
            "Update your address with the IRS",
            "Find new local services (doctor, dentist, vet, etc.)",
        ],
        "Ongoing": [
            "Update all remaining subscriptions and accounts",
            "File taxes correctly for the year you moved (may need to file in both states)",
            "Explore your new community — join local groups",
        ],
    },
    "disability": {
        "First 24 Hours": [
            "Request FMLA leave from your employer if applicable",
            "Gather all medical records and documentation",
            "Understand the difference between SSDI and SSI",
            "Contact your employer about short-term disability benefits",
            "Begin documenting your condition and limitations daily",
        ],
        "First Week": [
            "Apply for Social Security disability benefits (online or by phone)",
            "Review your employer's disability insurance policy",
            "Contact your health insurance to understand coverage",
            "Gather work history for the past 15 years",
            "Identify all sources of income and benefits available to you",
        ],
        "First Month": [
            "Follow up on your SSDI/SSI application status",
            "Apply for any state disability programs",
            "Create a budget based on reduced income",
            "Look into Medicaid eligibility if applicable",
            "Keep all medical appointments and document everything",
        ],
        "Ongoing": [
            "Continue medical treatment and keep records",
            "Prepare for a potential denial and appeal process",
            "Consider working with a disability attorney if denied",
            "Monitor your benefits and report any changes",
        ],
    },
    "retirement": {
        "First 24 Hours": [
            "Create a retirement income plan (Social Security + pension + savings)",
            "Understand your Medicare enrollment timeline",
            "Review all retirement account balances (401k, IRA, pension)",
            "Decide when to start Social Security benefits",
            "Review your employer's retirement benefits package",
        ],
        "First Week": [
            "Enroll in Medicare if you're 65+ (Parts A, B, D)",
            "Compare Medicare Supplement vs. Medicare Advantage plans",
            "Begin consolidating retirement accounts if needed",
            "Create a detailed retirement budget",
            "Review your estate plan and update beneficiaries",
        ],
        "First Month": [
            "Apply for Social Security benefits (3 months before desired start)",
            "Decide on pension payout options (lump sum vs. annuity)",
            "Set up Required Minimum Distributions if 73+",
            "Plan for healthcare costs in retirement",
            "Consider long-term care insurance",
        ],
        "Ongoing": [
            "Monitor your withdrawal rate and adjust as needed",
            "Take Required Minimum Distributions on time",
            "Review Medicare coverage during annual enrollment",
            "Update your estate plan annually",
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
- Weekly and monthly goals

Use this exact structure:
{
  "transition_type": "estate|divorce|job-loss|relocation|disability|retirement",
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
  ],
  "goals": [
    {"title": "Set up emergency budget", "timeframe": "weekly"},
    {"title": "Complete benefits applications", "timeframe": "monthly"}
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

        # Save goals
        for goal in plan.get("goals", []):
            target = None
            if goal.get("timeframe") == "weekly":
                target = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
            elif goal.get("timeframe") == "monthly":
                target = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
            db_execute(conn, f"INSERT INTO user_goals (user_id, title, timeframe, target_date, created_at) VALUES ({param},{param},{param},{param},{param})",
                (user["id"], goal.get("title", ""), goal.get("timeframe", "weekly"), target, now))

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

        def generate():
            full_reply = ""
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
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
        
if __name__ == "__main__":
    print("\n✓ Lumeway is running!")
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
