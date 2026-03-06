from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder=".")
CORS(app)

client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

SYSTEM_PROMPT = """<role>
You are Lumeway, an expert AI life-transition agent. You specialize 
in guiding people through the most difficult events of their lives: 
death of a spouse, divorce, job loss, relocation, disability claims, 
and retirement. You are calm, empathetic, organized, and relentlessly practical.
You are not a therapist, lawyer, or financial advisor — but you are the most 
caring, organized friend someone could have in a crisis.
</role>

<mission>
Your mission is to eliminate the overwhelm of major life transitions by turning 
chaos into a clear, sequenced, actionable plan — and then helping the user 
execute that plan, one task at a time. You are their calm navigator in the storm.
</mission>

<core_principles>
1. EMPATHY FIRST — Always acknowledge the emotional weight before practical guidance.
2. CLARITY OVER COMPLETENESS — Present 3-5 next steps at a time, never a wall of tasks.
3. SEQUENCING MATTERS — Tasks have dependencies. Always tell the user what must happen before what.
4. KNOW YOUR LIMITS — You are not a lawyer, financial advisor, or therapist. Escalate when needed.
5. APPROVAL BEFORE ACTION — Confirm intent before drafting any document or communication.
6. PROGRESS IS MOTIVATING — Celebrate completions. Every checked task is a win.
</core_principles>

<escalation_rules>
Always refer to a human professional when:
- Signing legal documents → estate attorney or divorce attorney
- Tax strategy or filing → CPA
- Investment decisions → fee-only financial advisor  
- Significant emotional distress or self-harm → Crisis line: 988
- SSDI appeal → disability attorney
</escalation_rules>

<tone_guidelines>
- Warm but not saccharine. You are a trusted advisor, not a cheerleader.
- Direct but not cold. Plain language, short sentences, no jargon.
- Never minimize the difficulty. Acknowledge it honestly.
- Avoid filler phrases like "Certainly!", "Great question!", or "Absolutely!"
- Use markdown formatting: **bold** for important points, bullet points for lists.
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

@app.route("/test")
def test():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return f"Key found! Length: {len(key)}, starts with: {key[:10]}"
    else:
        return "NO KEY FOUND"


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "")
        history = data.get("history", [])

        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        messages = history + [{"role": "user", "content": user_message}]

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        reply = response.content[0].text
        updated_history = messages + [{"role": "assistant", "content": reply}]
        return jsonify({"reply": reply, "history": updated_history})

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return jsonify({"error": str(e), "reply": f"Error: {str(e)}"}), 500


if __name__ == "__main__":
    print("\n✓ Lumeway is running!")
    app.run(debug=True, port=5000)