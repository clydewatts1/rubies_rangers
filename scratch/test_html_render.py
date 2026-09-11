import textwrap

raw = """
                <div class="squad-player-card">
                    <div style="display: flex;">
                        <span>Roefs</span>
                    </div>
                </div>
"""

print("RAW:")
for l in raw.splitlines():
    print(repr(l))

print("\nDEDENTED:")
dedented = textwrap.dedent(raw).strip()
for l in dedented.splitlines():
    print(repr(l))
