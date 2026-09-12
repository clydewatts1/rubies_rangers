import re
from pathlib import Path

p = Path(r"C:\Users\cw171001\Projects\PNC_KAN_GREASAN\docs\design\scatter_gather_detailed_design.md")
content = p.read_text(encoding="utf-8")
content = re.sub(r'sources:\s*\[[^\]]+\]', 'sources: ["legacy"]', content)
p.write_text(content, encoding="utf-8")
print("SUCCESS: Updated sources to ['legacy']")
