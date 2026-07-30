import os
import json
import re
import glob
import time
from datetime import datetime
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://obsidian-ollama:11434")
VAULT_PATH = os.getenv("VAULT_PATH", "/vault")
MODEL = os.getenv("MODEL", "phi4")
INTERVAL_MIN = int(os.getenv("INTERVAL_MIN", "60"))

PROMPT_TEMPLATE = """You are a creative writing assistant that helps restructure and enhance daily journal notes. Your goal is to make the notes more readable, insightful, and creatively engaging while preserving all original content.

Process this raw daily note into three sections:

## 1. Structured Summary
Restructure the raw content into clear bullet points organized by topic (work, personal, health, ideas, etc.). Preserve every detail.

## 2. Mood & Patterns
Identify the emotional tone and any recurring themes. Be honest but constructive.

## 3. Creative Reflection
Write a brief (2-3 sentences) creative or poetic reflection on the day. Match the user's energy — if they had a rough day, be supportive. If they were productive, be hype. Keep it natural, not flowery.

## 4. Extracted Todos
Pull out any tasks, deadlines, or follow-ups mentioned. Format as a clean checklist.

Rules:
- NEVER remove original content — only reorganize and enhance
- The user can review and delete sections they don't want
- Keep the creative reflection concise (max 100 words)
- Use markdown formatting

Raw daily note:
---
{content}
---

Enhanced daily note:"""


def get_daily_notes():
    daily_dir = os.path.join(VAULT_PATH, "Daily")
    if not os.path.exists(daily_dir):
        return []
    
    notes = []
    for filepath in glob.glob(os.path.join(daily_dir, "*.md")):
        with open(filepath, "r") as f:
            content = f.read()
        
        if "<!-- ai-enhanced -->" in content:
            continue
        
        stripped = re.sub(r'#.*|^\s*$', '', content, flags=re.MULTILINE).strip()
        if len(stripped) < 20:
            continue
        
        notes.append({"path": filepath, "content": content})
    
    return notes


def enhance_note(content):
    prompt = PROMPT_TEMPLATE.format(content=content)
    
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.7}},
            timeout=300
        )
        resp.raise_for_status()
        return resp.json()["response"]
    except Exception as e:
        return f"\n\n---\n*AI enhancement failed: {e}*\n"


def save_enhanced(filepath, original, enhanced):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    output = f"""{original}

---

*Enhanced by AI on {timestamp}*

{enhanced}

<!-- ai-enhanced -->
"""
    
    with open(filepath, "w") as f:
        f.write(output)
    
    return filepath


def run_once():
    notes = get_daily_notes()
    processed = []
    
    for note in notes:
        print(f"Enhancing: {note['path']}")
        enhanced = enhance_note(note["content"])
        save_enhanced(note["path"], note["content"], enhanced)
        processed.append(os.path.basename(note["path"]))
    
    return processed


if __name__ == "__main__":
    while True:
        results = run_once()
        if results:
            print(json.dumps({"enhanced": results, "time": datetime.now().isoformat()}))
        else:
            print(f"[{datetime.now().isoformat()}] No notes to enhance. Sleeping {INTERVAL_MIN}m...")
        
        time.sleep(INTERVAL_MIN * 60)
