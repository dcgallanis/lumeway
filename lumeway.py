##############################################################
# LIFESHIFT — Your AI Life Transition Agent
# Beginner-friendly version with lots of comments explaining
# what every single line does.
##############################################################

# These lines import tools we need
# "anthropic" is the library that talks to Claude
# "os" lets us read files and environment variables
# "dotenv" reads our secret API key from the .env file
import anthropic
import os
from dotenv import load_dotenv

# This line reads your .env file and loads your API key
load_dotenv()

# This creates your Claude "client" — think of it as opening
# a phone line to Claude. It automatically finds your API key
# from the .env file you set up.
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# This is your Lumeway system prompt.
# Think of this as the "instructions" you give Claude
# BEFORE the user starts talking. It tells Claude who it is
# and how to behave. This is sent with EVERY message.
SYSTEM_PROMPT = """<role>
You are Lumeway, an expert AI life-transition agent. You specialize 
in guiding people through the most difficult events of their lives: 
death of a spouse, divorce, job loss, relocation, disability claims, 
and retirement. You are calm, empathetic, organized, and practical.
</role>

<core_principles>
1. EMPATHY FIRST — Always acknowledge the emotional weight before practical guidance.
2. CLARITY OVER COMPLETENESS — Present 3-5 next steps at a time, never a wall of tasks.
3. SEQUENCING MATTERS — Tell the user what must happen before what.
4. KNOW YOUR LIMITS — You are not a lawyer or financial advisor. Escalate when needed.
5. APPROVAL BEFORE ACTION — Confirm intent before drafting any document.
</core_principles>

<task_output_format>
When presenting tasks, always use this structure:
TASK [NUMBER]: [TASK NAME]
→ Why it matters: [one sentence]
→ What to do: [2-4 clear steps]
→ Time needed: [estimate]
→ Deadline: [if one exists]
</task_output_format>"""


# This is the main function that sends a message to Claude
# and gets a response back.
#
# "user_message" = what the user just typed
# "conversation_history" = all the messages so far (starts empty)
#
# WHY DO WE NEED HISTORY?
# Claude has NO memory between calls. Every time you send a message,
# you have to send ALL the previous messages too — otherwise Claude
# forgets everything that was said before. Think of it like emailing
# someone: you have to forward the whole chain each time.

def chat(user_message, conversation_history=[]):
    
    # Add the new user message to the history list
    # Each message is a dictionary with a "role" and "content"
    # role = "user" (the person) or "assistant" (Claude)
    messages = conversation_history + [
        {"role": "user", "content": user_message}
    ]
    
    # Send everything to Claude and wait for a response
    # This is the actual API call — this is where your API key gets used
    response = client.messages.create(
        model="claude-sonnet-4-6",   # Which version of Claude to use
        max_tokens=1024,              # Maximum length of Claude's response
        system=SYSTEM_PROMPT,         # The instructions (sent every time)
        messages=messages             # The full conversation so far
    )
    
    # Pull out just the text from Claude's response
    # (The response object contains other metadata we don't need right now)
    claude_reply = response.content[0].text
    
    # Add Claude's reply to the history so future messages remember it
    updated_history = messages + [
        {"role": "assistant", "content": claude_reply}
    ]
    
    # Return both Claude's reply AND the updated history
    return claude_reply, updated_history


##############################################################
# MAIN PROGRAM
# This is where the actual conversation loop runs.
# It keeps asking for input until you type "quit".
##############################################################

def main():
    print("\n" + "="*50)
    print("  Welcome to Lumeway")
    print("  Your AI Life Transition Agent")
    print("  Type 'quit' to exit")
    print("="*50 + "\n")
    
    # Start with an empty conversation history
    history = []
    
    # Keep looping until the user types "quit"
    while True:
        
        # Ask the user to type something
        user_input = input("You: ").strip()
        
        # If they typed "quit", end the program
        if user_input.lower() == "quit":
            print("\nLumeway: Take care. Come back anytime.\n")
            break
        
        # If they didn't type anything, ask again
        if not user_input:
            continue
        
        # Show a "thinking" indicator
        print("\nLumeway: ", end="", flush=True)
        
        # Send their message to Claude (along with full history)
        reply, history = chat(user_input, history)
        
        # Print Claude's response
        print(reply)
        print()  # blank line for readability


# This line means "run the main() function when this file is run directly"
if __name__ == "__main__":
    main()
