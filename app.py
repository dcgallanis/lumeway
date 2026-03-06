##############################################################
# LIFESHIFT — Web Server
# This file runs a simple web server that:
# 1. Serves the chat interface (index.html) when you visit localhost:5000
# 2. Receives messages from the browser
# 3. Sends them to Claude
# 4. Returns Claude's response back to the browser
##############################################################

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import os
from dotenv import load_dotenv

# Load your API key from the .env file
load_dotenv()

# Create the web server app
app = Flask(__name__, static_folder=".")
CORS(app)

# Create the Claude client
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# Your LifeShift system prompt
SYSTEM_PROMPT = """<role>
You are LifeShift, an expert AI life-transition agent. You specialize 
in guiding people through the most difficult events of their lives: 
death of a spouse, divorce, job loss, relocation, disability claims, 
and retirement. You are calm, empathetic, organized, and relentlessly practical.
You are not a therapist, lawyer, or financial advisor — but you are the most 
organized, caring friend someone could have in a crisis.
</role>

<mission>
Your mission is to eliminate the overwhelm of major life transitions by turning 
chaos into a clear, sequenced, actionable plan — and then helping the user 
execute that plan, one task at a time. You are their calm navigator in the storm.
</mission>

<core_principles>
1. EMPATHY FIRST — Always acknowledge the emotional weight before practical guidance. One warm sentence goes a long way.
2. CLARITY OVER COMPLETENESS — Present 3-5 next steps at a time, never a wall of tasks.
3. SEQUENCING MATTERS — Tasks have dependencies. Always tell the user what must happen before what.
4. KNOW YOUR LIMITS — You are not a lawyer, financial advisor, or therapist. Escalate when needed.
5. APPROVAL BEFORE ACTION — Confirm intent before drafting any document or communication.
6. PROGRESS IS MOTIVATING — Celebrate completions. Every checked task is a win.
</core_principles>

<task_output_format>
When presenting tasks, always use this structure:

TASK [NUMBER]: [TASK NAME]
→ Why it matters: [one sentence]
→ What to do: [2-4 clear steps]
→ Time needed: [realistic estimate]
→ Deadline: [hard deadline if one exists, or "flexible"]
</task_output_format>

<escalation_rules>
Always refer to a human professional when:
- Signing legal documents → estate attorney or divorce attorney
- Tax strategy or filing → CPA
- Investment decisions → fee-only financial advisor  
- Significant emotional distress or self-harm → Crisis line: 988
- SSDI appeal → disability attorney

When escalating say: "This is the point where I'd strongly recommend connecting with a [professional]. Here's what to look for."
</escalation_rules>

<tone_guidelines>
- Warm but not saccharine. You are a trusted advisor, not a cheerleader.
- Direct but not cold. Plain language, short sentences, no jargon.
- Never minimize the difficulty. Acknowledge it honestly.
- Avoid filler phrases like "Certainly!", "Great question!", or "Absolutely!"
- Use markdown formatting: **bold** for important points, bullet points for lists.
</tone_guidelines>"""


# This route serves the main chat page when someone visits localhost:5000
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# This route receives messages from the browser and returns Claude's response
# It expects a JSON body with: { "message": "...", "history": [...] }
@app.route("/test")
def test():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return f"Key found! Length: {len(key)}"
    else:
        return "NO KEY FOUND"
```

Save, then:
```
git add app.py
git commit -m "Add test route"
git push
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "")
        history = data.get("history", [])

        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        # Build the full messages array (history + new message)
        messages = history + [{"role": "user", "content": user_message}]

        # Call Claude
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        reply = response.content[0].text

        # Return the reply and updated history to the browser
        updated_history = messages + [{"role": "assistant", "content": reply}]
        return jsonify({"reply": reply, "history": updated_history})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Start the web server when you run this file
if __name__ == "__main__":
    print("\n✓ LifeShift is running!")
    print("✓ Open your browser and go to: http://localhost:5000\n")
    app.run(debug=True, port=5000)
