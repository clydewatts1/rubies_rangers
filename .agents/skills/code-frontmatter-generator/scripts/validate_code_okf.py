"""
---
type: Tool
title: "Code OKF Validator"
description: "CLI utility for validating that source code and markdown documents adhere to the OKF frontmatter specification and are registered in ARD manifests."
tags: [registry, discovery, python, tooling]
status: Active
sources: []
generated:
  at: "2026-09-16T22:20:00Z"
  by: "agent:antigravity"
---
"""

import os
import sys
import re
import yaml
import json
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

APPROVED_TAGS = {
    # Process Tags
    "issue", "brainstorm", "design", "plan", "task", "playbook", "process",
    "architecture", "derived", "audit", "idea", "bug", "feature", "refactor",
    # Domain Tags
    "optimization", "monte-carlo", "milp", "knapsack", "cpn", "saga",
    "transfers", "hits", "chips", "balance-sheet", "challenge", "rolling-lock",
    "fdr", "weather", "odds", "tactics", "setpieces", "venue", "moneyball",
    "scout", "telemetry", "strategy", "portfolio", "automation",
    # Technology Tags
    "python", "pandas", "numpy", "streamlit", "pytest", "asyncio", "yaml",
    "json", "fastapi", "pulp", "scipy",
    # Component Tags
    "engine", "client", "service", "ui", "component", "solver", "adapter",
    "runner", "daemon", "validator", "journal", "tooling", "registry", "discovery", "cli"
}

VALID_CODE_TYPES = {"Implementation", "Component", "Test", "Script", "Tool", "Model", "Service"}
VALID_DOC_TYPES = {"Issue", "Brainstorm", "Design", "Plan", "TaskHarness", "Playbook", "Architecture", "Tool", "Document"}
VALID_STATUSES = {"Draft", "Active", "Deprecated", "Legacy", "Open", "Closed", "Merged"}


def extract_frontmatter_from_python(content: str):
    """Extracts YAML frontmatter from module docstring."""
    docstring_match = re.search(r'^[ \t]*"""[ \t]*\r?\n---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n[ \t]*"""', content, re.DOTALL)
    if docstring_match:
        return docstring_match.group(1)
    return None


def extract_frontmatter_from_markdown(content: str):
    """Extracts YAML frontmatter from Markdown file."""
    if content.lstrip("\ufeff").startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[1]
    return None


def extract_frontmatter(file_path: Path):
    suffix = file_path.suffix.lower()
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return None, f"Could not read file: {e}"

    raw_yaml = None
    if suffix == ".py":
        raw_yaml = extract_frontmatter_from_python(content)
    elif suffix in (".md", ".markdown"):
        raw_yaml = extract_frontmatter_from_markdown(content)

    if not raw_yaml:
        return None, "No OKF frontmatter block found"

    raw_yaml = raw_yaml.replace("\t", "  ")
    try:
        data = yaml.safe_load(raw_yaml)
        if not isinstance(data, dict):
            return None, "Frontmatter does not parse as a YAML dictionary"
        return data, None
    except Exception as e:
        return None, f"Invalid YAML frontmatter: {e}"


def load_ard_registered_urls(repo_root: Path) -> set:
    registered = set()
    for root, _, files in os.walk(repo_root):
        if "ard.json" in files:
            ard_file = Path(root) / "ard.json"
            try:
                with open(ard_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                    for r in manifest.get("resources", []):
                        url = r.get("url")
                        if url:
                            registered.add(url.replace("\\", "/").lstrip("/"))
            except Exception:
                pass
    return registered


def validate_file(file_path: Path, repo_root: Path, ard_urls: set) -> dict:
    rel_path = file_path.relative_to(repo_root).as_posix()
    issues = []
    warnings = []

    meta, err = extract_frontmatter(file_path)
    if err:
        return {
            "file": rel_path,
            "status": "FAIL",
            "provenance": "-",
            "ard": "YES" if rel_path in ard_urls else "NO",
            "issues": [err]
        }

    doc_type = meta.get("type")
    if file_path.suffix == ".md":
        if not doc_type or doc_type not in VALID_DOC_TYPES:
            issues.append(f"Invalid docs type '{doc_type}' (expected one of {sorted(VALID_DOC_TYPES)})")
    else:
        if not doc_type or doc_type not in VALID_CODE_TYPES:
            issues.append(f"Invalid code type '{doc_type}' (expected one of {sorted(VALID_CODE_TYPES)})")

    if not meta.get("title"):
        issues.append("Missing 'title'")
    if not meta.get("description"):
        issues.append("Missing 'description'")

    tags = meta.get("tags", [])
    if not isinstance(tags, list) or not tags:
        issues.append("Missing or empty 'tags' list")
    else:
        invalid_tags = [t for t in tags if t.lower() not in APPROVED_TAGS]
        if invalid_tags:
            issues.append(f"Unapproved tags: {invalid_tags}")

    status = meta.get("status")
    if not status:
        issues.append("Missing 'status'")
    elif status not in VALID_STATUSES:
        issues.append(f"Invalid status '{status}' (expected one of {sorted(VALID_STATUSES)})")

    sources = meta.get("sources", [])
    prov_display = "None"
    if not isinstance(sources, list):
        issues.append("sources must be a list")
    elif not sources:
        if doc_type not in ("Issue", "Brainstorm", "Tool") and status != "Legacy":
            warnings.append("No 'sources' design linkage defined")
    else:
        prov_display = ", ".join(sources)
        for s in sources:
            if s == "legacy" or s == "[]":
                continue
            source_path = repo_root / s
            if not source_path.exists():
                issues.append(f"Linked source does not exist: {s}")

    return {
        "file": rel_path,
        "status": "PASS" if not issues else "FAIL",
        "provenance": prov_display,
        "ard": "YES" if rel_path in ard_urls else "NO",
        "issues": issues,
        "warnings": warnings
    }


def main():
    parser = argparse.ArgumentParser(description="Validate OKF frontmatter on source code and markdown docs")
    parser.add_argument("--root", default=".", help="Root of repository")
    parser.add_argument("--dir", help="Specific directory to scan")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    target_dir = repo_root / args.dir if args.dir else repo_root

    ard_urls = load_ard_registered_urls(repo_root)

    results = []
    ignore_dirs = {".git", ".venv", "venv", "__pycache__", "archive", "node_modules", ".hypothesis", ".pytest_cache", "logs"}

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = sorted([d for d in dirs if d not in ignore_dirs])
        for f in sorted(files):
            if f.endswith((".py", ".md")):
                f_path = Path(root) / f
                # Skip __init__.py, temp files, index.md, and root walkthrough/plan
                if f in ("__init__.py", "tempCodeRunnerFile.py", "walkthrough.md", "implementation_plan.md", "index.md"):
                    continue
                res = validate_file(f_path, repo_root, ard_urls)
                results.append(res)

    passes = sum(1 for r in results if r["status"] == "PASS")
    fails = sum(1 for r in results if r["status"] == "FAIL")

    print("=" * 80)
    print(f" OKF VALIDATION REPORT | Total Files: {len(results)} | Passed: {passes} | Failed: {fails}")
    print("=" * 80)

    for r in results:
        if r["status"] == "FAIL" or (r.get("warnings") and args.strict):
            print(f"[{r['status']}] {r['file']}")
            for iss in r["issues"]:
                print(f"  ❌ {iss}")
            for w in r.get("warnings", []):
                print(f"  ⚠️  {w}")

    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
