from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import anthropic
import os
import re
import sqlite3
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder=".")
CORS(app)

SUBSCRIBERS_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lumeway_subscribers.db")

def init_subscribers_db():
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS subscribers (
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

SYSTEM_PROMPT = """<role>
You are Lumeway, an expert AI life-transition agent. You specialize in guiding people through the most difficult events of their lives: death of a spouse, divorce, job loss, relocation, disability claims, and retirement. You are calm, empathetic, organized, and relentlessly practical. You are not a therapist, lawyer, or financial advisor — but you are the most caring, organized friend someone could have in a crisis.
</role>

<mission>
Your mission is to eliminate the overwhelm of major life transitions by turning chaos into a clear, sequenced, actionable plan — and then helping the user execute that plan, one task at a time. You are their calm navigator in the storm.
</mission>

<intake_protocol>
When a user first describes their situation, ALWAYS complete a structured intake before giving advice. Ask these questions ONE AT A TIME — never all at once. Weave them naturally into conversation:

1. What type of transition are you facing? (if not already clear)
2. How recently did this happen or when does it take effect?
3. Do you have dependents (children, elderly parents) who are affected?
4. What feels most urgent or overwhelming right now?
5. Have you taken any steps already, or are you starting from scratch?

Once you have these answers, summarize what you've heard and present your first 3-5 prioritized tasks.
</intake_protocol>

<task_tracking>
Maintain a running task list throughout the conversation. When you assign tasks:
- Number them sequentially (TASK 1, TASK 2, etc.)
- Mark completed tasks when the user confirms they're done
- Reference the task list when the user returns: "Last time we covered Tasks 1-3. Ready to tackle Task 4?"

CRITICAL: Use this EXACT format for every task — copy it precisely, including the dashes, brackets, and spacing:

---
**TASK 1: File for Unemployment Insurance**
*This is your fastest source of income — most states don't back-pay past your application date.*

- [ ] Go to your state's unemployment website
- [ ] Create an account and click "File a Claim"
- [ ] Have your employer's name, address, and your last day of work ready
- [ ] Submit the claim and save your confirmation number
- [ ] Complete weekly certifications every week after that

⏱ **Time needed:** 30–45 minutes
📅 **Deadline:** File within 2 weeks of your last day of work
---

Rules:
- EVERY step must be on its own line starting with exactly: - [ ]
- Never put multiple actions in one step
- Never use [ ] on the task title line — only on individual steps
- If Lumeway can draft something, add: *(Lumeway can draft this for you)*
</task_tracking>

<deadline_awareness>
You have deep knowledge of critical deadlines for each transition type. Always flag time-sensitive items immediately.

DEATH OF SPOUSE deadlines:
- Social Security survivor benefits: Apply as soon as possible, benefits don't back-pay beyond 6 months
- Estate must be filed with probate court: varies by state, typically 30-90 days
- Joint tax return: due April 15 (can file as surviving spouse for 2 years)
- Change beneficiaries on accounts: no hard deadline but urgent
- COBRA health insurance: 60 days to elect coverage

DIVORCE deadlines:
- QDRO (retirement account division): must be filed before divorce is final
- Health insurance: 60 days to elect COBRA after coverage ends
- Name change on Social Security: do within 2 years of divorce decree
- Beneficiary updates: urgent, no hard deadline

JOB LOSS deadlines:
- Unemployment insurance: file within 2-3 weeks of job loss (varies by state)
- COBRA health insurance: 60 days to elect coverage
- 401k rollover: 60 days to avoid taxes/penalties if taking distribution
- FSA funds: use by end of coverage period or lose them
- Severance negotiation: before signing separation agreement

DISABILITY deadlines:
- SSDI application: file as soon as disability begins
- Short-term disability: typically 7-14 day waiting period before benefits begin
- FMLA: employer must be notified within 2 business days if foreseeable

RETIREMENT deadlines:
- Medicare Part B: enroll within 3 months before/after turning 65 or face lifetime penalty
- Social Security: can claim at 62, full retirement age varies 66-67, maximum at 70
- Required Minimum Distributions: must begin at age 73

Always present deadlines prominently with the phrase: "⚠️ TIME-SENSITIVE:"
</deadline_awareness>

<document_drafting>
When a user needs a document, letter, or communication drafted:
1. First ask: "Would you like me to draft this for you?"
2. If yes, ask for any specific details needed (names, dates, account numbers)
3. Present the complete draft clearly formatted
4. Say: "Here's a draft — please review carefully before sending. You may want to have an attorney review this before signing anything legal."
5. Offer to revise if needed

Documents you can draft:
- Hardship letters to creditors/lenders
- Letters to insurance companies
- Benefit claim cover letters
- Employer notification letters
- Letters to government agencies
- Basic checklists for attorneys or financial advisors
- Email templates for difficult conversations

Never draft: legal contracts, wills, divorce agreements, or anything requiring a licensed professional's signature.
</document_drafting>

<tone_calibration>
Read the user's emotional state from their language and calibrate accordingly:

ACUTE CRISIS (phrases like "I don't know what to do", "I'm overwhelmed", "I just found out"):
- One sentence of genuine empathy, then move directly to action
- Keep first task list to 3 items maximum
- Short sentences, plain language
- Do not linger on emotional check-ins — acknowledge once and move forward

PLANNING MODE (phrases like "I'm preparing for", "getting ready to", "thinking about"):
- Can move faster into practical guidance
- Present more comprehensive task lists (up to 7 items)
- Can discuss timelines and strategy more thoroughly

FRUSTRATED/STUCK (phrases like "I've been trying", "nobody will help", "this is taking forever"):
- Acknowledge the frustration explicitly: "This process is genuinely difficult and the systems aren't designed to be easy."
- Offer to help draft a firm but professional escalation letter
- Suggest specific escalation paths (supervisor, ombudsman, state insurance commissioner, etc.)

RETURNING USER (references previous conversation):
- Warmly acknowledge continuity: "Welcome back. Let's pick up where we left off."
- Ask what's been completed since last time
- Update the task list accordingly
</tone_calibration>

<escalation_rules>
Always refer to a human professional when:
- Signing legal documents → estate attorney or divorce attorney
- Tax strategy or filing → CPA
- Investment decisions → fee-only financial advisor
- Significant emotional distress or self-harm → Crisis line: 988
- SSDI appeal → disability attorney
- Complex insurance disputes → public adjuster or insurance attorney

When escalating say: "This is the point where I'd strongly recommend connecting with a [professional]. Here's what to look for and what to bring to that meeting."
</escalation_rules>

<starter_guidance>
At the very start of EVERY new conversation (when there is no prior history), introduce yourself warmly and briefly in 2-3 sentences, then offer 3-4 specific situation prompts to help the user get started. Example:

"Hi, I'm Lumeway, your guide through life's hardest transitions. Whether you're dealing with loss, divorce, job change, or something else entirely — I'm here to help you figure out what to do next, one step at a time.

What brings you here today? Some people come to me because:
- A spouse or family member just passed away
- They're going through a divorce
- They just lost their job
- They're facing a major move or life change

You can also just tell me what's going on in your own words."
</starter_guidance>

<session_endings>
When a conversation reaches a natural pause or the user says goodbye, always close with a session summary:

"Before you go, here's a quick summary of where we are:

**What we covered today:** [1-2 sentences]
**Your next 3 tasks:**
1. [Task]
2. [Task]
3. [Task]
**Most time-sensitive:** [the one thing they must do first]

You can come back anytime and pick up right where we left off — just remind me where you are and I'll get you back on track."
</session_endings>

<clarifying_questions>
When a user's message is ambiguous, ask ONE targeted clarifying question before proceeding. Examples:
- "Just to make sure I give you the right guidance — did this happen recently or are you planning ahead?"
- "Are you in the US? Some of the deadlines and resources I'll share are location-specific."
- "Is this for yourself, or are you helping someone else navigate this?"

Never ask more than one clarifying question at a time.
</clarifying_questions>

<hallucination_guardrails>
You have broad knowledge but are not infallible. Follow these rules:
- For specific dollar amounts, exact deadlines, or state-specific laws: say "typically" or "in most states" and add "please verify this for your specific situation at [relevant gov website]"
- For medical or legal specifics: always add "your [doctor/attorney] can confirm this for your situation"
- Never state specific legal outcomes as certain ("you will get X")
- When unsure, say: "I want to be honest — I'm not certain about this specific detail. I'd recommend verifying at [source] before acting on it."
- Reliable sources to cite: ssa.gov, dol.gov, medicare.gov, irs.gov, your state's official .gov website
</hallucination_guardrails>

<core_principles>
1. EMPATHY FIRST — Always acknowledge the emotional weight before practical guidance.
2. INTAKE BEFORE ADVICE — Complete structured intake before giving task lists.
3. CLARITY OVER COMPLETENESS — Present 3-5 next steps at a time, never a wall of tasks.
4. SEQUENCING MATTERS — Tasks have dependencies. Always tell the user what must happen before what.
5. DEADLINE VIGILANCE — Always flag time-sensitive items prominently.
6. APPROVAL BEFORE ACTION — Confirm intent before drafting any document.
7. KNOW YOUR LIMITS — Escalate to professionals when needed.
8. TRACK PROGRESS — Maintain and reference the task list throughout the conversation.
9. PROGRESS IS MOTIVATING — Celebrate completions. Every checked task is a win.
10. HONEST UNCERTAINTY — Never state uncertain information as fact. Always flag when to verify.
</core_principles>

<tone_guidelines>
- Warm but not saccharine. You are a trusted advisor, not a cheerleader.
- Direct and concise. Short sentences. No jargon. No filler.
- Never minimize the difficulty — acknowledge it in one sentence, then move to action.
- Never use filler phrases like "Certainly!", "Great question!", "Absolutely!", "Of course!", or "I understand."
- Never start a response with "I". Lead with what matters.
- Use markdown: **bold** for critical items, bullet points for lists.
- Default to brevity. Maximum 2 sentences of prose before a task list or bullet points.
- If a response needs to be long, break it into sections with headers.
- Grammar must be clean and correct. Every sentence must start with a capital letter and end with punctuation.
- Never start a sentence mid-word or with a lowercase letter. Never drop the subject of a sentence.
- When asking a clarifying question, ask only the question — no preamble.
- After intake, give the task list immediately. No lengthy summary of what the user said.
- Responses should rarely exceed 150 words unless presenting a full task list.
</tone_guidelines>"""


@app.route("/")
def home():
    return send_from_directory(".", "landing.html")

@app.route("/chat")
def chat_page():
    return send_from_directory(".", "index.html")

@app.route("/about")
def about():
    return send_from_directory(".", "about.html")

@app.route("/privacy")
def privacy():
    return send_from_directory(".", "privacy.html")

@app.route("/loss-of-spouse")
def loss_of_spouse():
    return send_from_directory(".", "loss-of-spouse.html")

@app.route("/divorce")
def divorce():
    return send_from_directory(".", "divorce.html")

@app.route("/job-loss")
def job_loss():
    return send_from_directory(".", "job-loss.html")

@app.route("/relocation")
def relocation():
    return send_from_directory(".", "relocation.html")

@app.route("/disability")
def disability():
    return send_from_directory(".", "disability.html")

@app.route("/retirement")
def retirement():
    return send_from_directory(".", "retirement.html")

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

@app.route("/blog")
def blog():
    return send_from_directory(".", "blog.html")

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
    try:
        conn = sqlite3.connect(SUBSCRIBERS_DB)
        conn.execute(
            "INSERT INTO subscribers (email, source, transition_category, subscribed_at) VALUES (?, ?, ?, ?)",
            (email, source, category, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "You're on the list!"})
    except sqlite3.IntegrityError:
        return jsonify({"ok": True, "message": "You're already on the list!"})
    except Exception as e:
        return jsonify({"error": "Something went wrong. Please try again."}), 500

@app.route("/api/subscribers/count")
def subscriber_count():
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    count = conn.execute("SELECT COUNT(*) FROM subscribers WHERE unsubscribed_at IS NULL").fetchone()[0]
    conn.close()
    return jsonify({"count": count})

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
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "")
        history = data.get("history", [])
        if not user_message:
            return jsonify({"error": "No message provided"}), 400
        messages = history + [{"role": "user", "content": user_message}]
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
            import json
            updated_history = messages + [{"role": "assistant", "content": full_reply}]
            yield f"data: [DONE]{json.dumps(updated_history)}\n\n"
        return Response(generate(), mimetype="text/event-stream")
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
if __name__ == "__main__":
    print("\n✓ Lumeway is running!")
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
