---
name: code-frontmatter-generator
description: Generates, embeds, and audits OKF YAML frontmatter within Python module docstrings. Connects source code modules to their origin Stage 3 Design specifications and registers them in the ARD manifest.
---

# code-frontmatter-generator

## Purpose
This skill ensures that Python source code files adhere to the **Code-as-Knowledge** OKF specification. By placing a structured YAML frontmatter block inside the module's top-level docstring, source code becomes self-describing, searchable via `ard_search`, and traceable back to its originating Design document in `docs/design/`.

## Python Docstring Frontmatter Format

In Python modules, frontmatter is placed at the very top of the file within triple quotes:

```python
"""
---
type: Implementation | Component | Service | Solver | Tool | Test
title: "<Human-Readable Module Title>"
description: "<Concise 1-2 sentence description of module responsibility>"
tags: [<domain_tags>, <tech_tags>]
status: Active | Draft | Deprecated | Legacy
sources: ["docs/design/des_<ID>_<slug>.md"]
generated:
  at: "<ISO-8601-UTC-Timestamp>"
  by: "agent:<name>"
---
"""
from __future__ import annotations
...
```

## Validation Script
You can audit source code files across the repository using:
```bash
python .agents/skills/code-frontmatter-generator/scripts/validate_code_okf.py --root .
```

## When to Activate
- Authoring a new Python module in `analytics/`, `automation/`, `clients/`, `ui/`, or `scripts/`.
- Retrofitting existing Python modules with OKF lineage.
- Running a codebase audit for design-to-code traceability.
