raw_html = """
                <div class="squad-player-card" style="border: 1px solid #3b82f6; background: #1e293b;">
                    <div style="display: flex;">
                        <span>Roefs</span>
                    </div>
                    <div>(Sunderland)</div>
                </div>
"""

clean = "\n".join(line.strip() for line in raw_html.splitlines() if line.strip())
print(repr(clean))
print(clean)
