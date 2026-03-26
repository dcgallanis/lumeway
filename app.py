from flask import Flask, request, jsonify, send_from_directory, Response, render_template_string
from flask_cors import CORS
import anthropic
import csv
import glob as globmod
import io
import json
import markdown
import os
import re
import sqlite3
from datetime import datetime, timezone
from dotenv import load_dotenv
import conversation_log

load_dotenv()

app = Flask(__name__, static_folder=".")
CORS(app)

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
    else:
        db_execute(conn, """CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            source TEXT DEFAULT 'popup',
            transition_category TEXT,
            subscribed_at TEXT NOT NULL,
            unsubscribed_at TEXT
        )""")
    conn.commit()
    conn.close()

init_subscribers_db()

client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

conversation_log.init_db()

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
- After presenting the roadmap, say: "Lumeway has templates and
  checklists for several of these steps. Would you like me to show
  you which ones might be helpful?"
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

1. WHEN TO MENTION TEMPLATES: After presenting a roadmap step, you may say:
   "Lumeway has a [template name] that can help you stay organized during
   this step."

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
- Potential guardrail weaknesses that need strengthening"""


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

@app.route("/loss-of-spouse")
def loss_of_spouse():
    return inject_related_posts("loss-of-spouse.html", TRANSITION_CATEGORIES["loss-of-spouse"])

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

@app.route("/templates")
def templates():
    return send_from_directory(".", "templates.html")

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
    # Extract category from blog-category div
    cat_match = re.search(r'class="blog-category"[^>]*>(.*?)</div>', raw, re.DOTALL)
    if cat_match:
        meta["category"] = re.sub(r"<[^>]+>", "", cat_match.group(1)).strip()
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
    html = html.replace('<div class="blog-grid">', '<div class="blog-grid">' + cards_html)
    html = html.replace('<span class="blog-card-soon">Coming soon</span>', '')
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
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{--cream:#F7F4EF;--warm-white:#FDFCFA;--text:#1B2A38;--muted:#6E7D8A;--navy:#1B3A5C;--gold:#B8977E;--border:#E4DDD3}
    body{font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--text);-webkit-font-smoothing:antialiased;line-height:1.7;font-size:17px;font-weight:300}
    nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:20px 48px;display:flex;align-items:center;justify-content:space-between;background:rgba(247,244,239,0.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
    .nav-logo{display:flex;align-items:center;gap:10px;text-decoration:none}
    .nav-logo-icon{width:32px;height:32px;background:var(--navy);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--cream);font-family:'Cormorant Garamond',serif;font-size:18px;font-weight:500}
    .nav-logo-text{font-family:'Cormorant Garamond',serif;font-size:20px;font-weight:500;color:var(--text)}
    .nav-left{display:flex;align-items:center;gap:28px}
    .nav-right{display:flex;gap:12px;align-items:center}
    .btn-ghost{padding:8px 20px;border:1px solid var(--border);border-radius:100px;background:transparent;color:var(--text);font-family:'DM Sans',sans-serif;font-size:14px;text-decoration:none;transition:all 0.2s}
    .btn-ghost:hover{background:var(--navy);color:var(--cream)}
    .btn-primary{padding:8px 20px;border:none;border-radius:100px;background:var(--navy);color:var(--cream);font-family:'DM Sans',sans-serif;font-size:14px;text-decoration:none;transition:all 0.2s}
    article{max-width:720px;margin:0 auto;padding:120px 24px 64px}
    .post-meta{margin-bottom:32px}
    .post-tag{display:inline-block;font-size:11px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:var(--gold);background:var(--warm-white);border:1px solid var(--border);padding:3px 10px;border-radius:100px;margin-bottom:16px}
    .post-title{font-family:'Cormorant Garamond',serif;font-size:clamp(32px,5vw,48px);font-weight:300;line-height:1.15;letter-spacing:-0.02em;margin-bottom:12px}
    .post-date{font-size:13px;color:var(--muted)}
    .post-divider{width:60px;height:2px;background:var(--gold);margin-bottom:40px}
    .post-body{font-size:16px;line-height:1.85;font-weight:300;color:var(--text)}
    .post-body h2{font-family:'Cormorant Garamond',serif;font-size:28px;font-weight:400;margin:48px 0 20px;color:var(--navy);line-height:1.3}
    .post-body h3{font-size:18px;font-weight:500;margin:28px 0 12px;color:var(--text)}
    .post-body p{margin-bottom:18px}
    .post-body ul,.post-body ol{margin:0 0 20px 24px}
    .post-body li{margin-bottom:8px;line-height:1.7}
    .post-body strong{font-weight:500}
    .post-body a{color:var(--navy);text-decoration:underline;text-decoration-color:var(--border);text-underline-offset:3px}
    .post-body a:hover{text-decoration-color:var(--navy)}
    .post-body .template-callout{background:var(--warm-white);border-left:3px solid var(--gold);padding:20px 24px;margin:28px 0;border-radius:0 8px 8px 0}
    .post-body .template-callout p{font-size:15px;color:var(--muted);margin-bottom:0}
    .post-body .cta-box{background:var(--warm-white);border:1px solid var(--border);border-radius:12px;padding:32px;margin:40px 0;text-align:center}
    .post-body .cta-box h3{font-family:'Cormorant Garamond',serif;font-size:24px;font-weight:400;color:var(--navy);margin-bottom:12px}
    .post-body .cta-box p{font-size:15px;color:var(--muted);margin-bottom:20px}
    .post-body .cta-button{display:inline-block;font-family:'DM Sans',sans-serif;font-size:13px;font-weight:500;text-transform:uppercase;letter-spacing:1.5px;color:var(--cream);background:var(--navy);padding:14px 32px;border-radius:28px;text-decoration:none;transition:background 0.2s}
    .post-body .cta-button:hover{background:var(--gold);color:white}
    .post-body .disclaimer{font-size:13px;font-style:italic;color:var(--muted);border-top:1px solid var(--border);padding-top:32px;margin-top:48px;line-height:1.6}
    .post-back{display:inline-block;margin-top:48px;font-size:14px;color:var(--muted);text-decoration:none}
    .post-back:hover{color:var(--navy)}
    footer{padding:28px 48px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-top:64px}
    .footer-logo{font-family:'Cormorant Garamond',serif;font-size:18px;font-weight:500;color:var(--navy)}
    .footer-note{font-size:12px;color:var(--muted);font-weight:300}
    .footer-note a{color:var(--muted)}
    @media(max-width:580px){nav{padding:16px 20px}article{padding:100px 20px 48px}}
  </style>
</head>
<body>
  <nav>
    <div class="nav-left">
      <a href="/" class="nav-logo">
        <div class="nav-logo-icon">L</div>
        <span class="nav-logo-text">Lumeway</span>
      </a>
    </div>
    <div class="nav-right">
      <a href="/chat" target="_blank" class="btn-ghost">Try it free</a>
      <a href="/#waitlist" class="btn-primary">Join waitlist</a>
    </div>
  </nav>
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
      <p style="font-family:'Cormorant Garamond',serif;font-size:22px;color:var(--navy);margin-bottom:8px">Need a full step-by-step plan?</p>
      <p style="font-size:14px;color:var(--muted);margin-bottom:16px">Our {{ category_links[cat][1] }} walks you through timelines, deadlines, and resources.</p>
      <a href="{{ category_links[cat][0] }}" style="display:inline-block;padding:12px 28px;background:var(--navy);color:var(--cream);border-radius:100px;font-size:14px;text-decoration:none">View the guide</a>
    </div>
    {% endif %}
    <a href="/blog" class="post-back">&larr; Back to all posts</a>
  </article>
  <footer>
    <span class="footer-logo">Lumeway</span>
    <span class="footer-note">&copy; 2026 Lumeway. All rights reserved. | <a href="/privacy">Privacy</a> &middot; <a href="/terms">Terms</a> | <a href="https://www.pinterest.com/lumeway" rel="noopener" target="_blank">Pinterest</a> &middot; <a href="https://www.etsy.com/shop/LumewayTemplates" rel="noopener" target="_blank">Etsy</a></span>
  </footer>
</body>
</html>"""

@app.route("/static/data/state-rules.json")
def state_rules():
    return send_from_directory("data", "state-rules.json")

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
                    yield f"data: {text.replace(chr(10), '\\n')}\n\n"

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
