import glob
import json
import os

paths = glob.glob(r"C:\Users\cw171001\.gemini\antigravity-ide\brain\*\.system_generated\logs\transcript.jsonl")
for p in paths:
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                if any(k in line.lower() for k in ["rubies", "league", "entry", "manager", "fpl id"]):
                    try:
                        d = json.loads(line)
                        if d.get("type") == "USER_INPUT":
                            print(f"[{os.path.basename(os.path.dirname(os.path.dirname(p)))}] USER: {d.get('content')[:200]}")
                    except Exception:
                        pass
    except Exception:
        pass
