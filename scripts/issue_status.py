"""
---
type: Tool
title: "Issue Lifecycle Status & CPN Marking Inspector"
description: "Zero-code metadata inspector that queries ARD manifests and OKF frontmatter to determine the exact lifecycle stage, CPN marking, and next eligible transitions for issues."
tags: [discovery, registry, python, cli, tooling, cpn]
status: Active
sources: []
generated:
  at: "2026-09-17T06:08:00Z"
  by: "agent:antigravity"
---
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

STAGE_NAMES = {
    1: "Stage 1 (Issue)",
    2: "Stage 2 (Brainstorm)",
    3: "Stage 3 (Design)",
    4: "Stage 4 (Plan)",
    5: "Stage 5 (Tasks)",
    6: "Stage 6 (Playbook)",
}

CPN_PLACES = {
    1: "P_ISSUE_READY",
    2: "P_BRAINSTORM_POOL",
    3: "P_DESIGN_READY",
    4: "P_PLAN_READY",
    5: "P_TASK_QUEUE",
    6: "P_COMMITTED_PLAYBOOK",
}

NEXT_TRANSITIONS = {
    1: "T_BRAINSTORM (via /brainstorm-facilitator or /ideate) or T_DESIGN (Track B Fast-Track)",
    2: "T_DESIGN (via /design-facilitator)",
    3: "T_SPEC_TO_PLAN (via /spec-to-plan or /design-to-task)",
    4: "T_PLAN_TO_TASK (via /plan-to-task)",
    5: "T_CODE / T_VERIFY (via pytest verification harness)",
    6: "COMPLETED (In Operations & Maintenance)",
}


def find_repo_root() -> Path:
    current = Path(__file__).resolve().parent.parent
    if (current / "ard.json").exists() or (current / "docs").exists():
        return current
    cwd = Path.cwd()
    if (cwd / "ard.json").exists() or (cwd / "docs").exists():
        return cwd
    return current


def extract_frontmatter(file_path: Path) -> Optional[Dict[str, Any]]:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None
    if content.lstrip("\ufeff").startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1].replace("\t", "  ")
            try:
                data = yaml.safe_load(raw_yaml)
                if isinstance(data, dict):
                    return data
            except Exception:
                return None
    return None


def extract_issue_id(text: str) -> Optional[str]:
    """Extracts a 3-digit issue ID (e.g. 001, 015) from string."""
    match = re.search(r'(?:iss_|\[#|#)(\d{3})', text)
    if match:
        return match.group(1)
    match_loose = re.search(r'\b(\d{3})\b', text)
    if match_loose:
        return match_loose.group(1)
    return None


def clean_title(title: str) -> str:
    """Removes [#001] prefixes from title."""
    return re.sub(r'^\[#\d+\]\s*', '', title).strip()


class IssueLifecycleTracker:
    def __init__(self, root: Path):
        self.root = root
        self.manifest_path = root / "ard.json"
        self.resources: List[Dict[str, Any]] = []
        self._load_resources()

    def _load_resources(self):
        """Loads from ard.json if available; falls back to parsing docs/ frontmatter."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.resources = data.get("resources", [])
            except Exception as e:
                sys.stderr.write(f"Warning: Could not read {self.manifest_path}: {e}\n")

        if not self.resources:
            # Fallback: scan docs directly
            docs_dir = self.root / "docs"
            if docs_dir.exists():
                for md_file in docs_dir.rglob("*.md"):
                    fm = extract_frontmatter(md_file)
                    if fm:
                        rel_path = md_file.relative_to(self.root).as_posix()
                        self.resources.append({
                            "displayName": fm.get("title", md_file.stem),
                            "conceptType": fm.get("type", "Document"),
                            "url": rel_path,
                            "sources": fm.get("sources", []),
                            "tags": fm.get("tags", []),
                            "status": fm.get("status", "Active"),
                            "description": fm.get("description", "")
                        })

    def get_all_issue_states(self) -> Dict[str, Dict[str, Any]]:
        """Constructs lifecycle map for every issue found in repository."""
        issues: Dict[str, Dict[str, Any]] = {}

        # 1. Identify all primary Issue resources
        for res in self.resources:
            url = res.get("url", "")
            concept = (res.get("conceptType") or "").lower()
            name = res.get("displayName") or ""
            
            # Match docs/issues/iss_*.md
            if "docs/issues/iss_" in url or concept == "issue":
                issue_id = extract_issue_id(url) or extract_issue_id(name)
                if issue_id:
                    if issue_id not in issues:
                        issues[issue_id] = {
                            "id": issue_id,
                            "title": clean_title(name),
                            "status": res.get("status", "Active"),
                            "description": res.get("description", ""),
                            "stages": {1: None, 2: None, 3: None, 4: None, 5: None, 6: None},
                            "sources": {}
                        }
                    issues[issue_id]["stages"][1] = url
                    issues[issue_id]["sources"][1] = res.get("sources", [])

        # 2. Correlate downstream artifacts (Brainstorm, Design, Plan, Tasks, Playbook)
        for res in self.resources:
            url = res.get("url", "")
            concept = (res.get("conceptType") or "").lower()
            name = res.get("displayName") or ""
            sources = res.get("sources", [])
            tags = [t.lower() for t in res.get("tags", [])]

            # Determine stage candidate
            stage_idx = None
            if "docs/brainstorm/" in url or concept == "brainstorm" or "brainstorm" in tags:
                stage_idx = 2
            elif "docs/design/" in url or concept == "design" or "design" in tags:
                stage_idx = 3
            elif "docs/plans/" in url or concept == "plan" or "plan" in tags:
                stage_idx = 4
            elif "docs/tasks/" in url or concept in ("task", "taskharness") or "task" in tags:
                stage_idx = 5
            elif "docs/playbooks/" in url or concept == "playbook" or "playbook" in tags:
                stage_idx = 6

            if not stage_idx:
                continue

            # Identify target issue ID for this artifact
            matched_id = extract_issue_id(url) or extract_issue_id(name)
            if not matched_id and sources:
                for src in sources:
                    src_id = extract_issue_id(str(src))
                    if src_id:
                        matched_id = src_id
                        break

            if matched_id and matched_id in issues:
                issues[matched_id]["stages"][stage_idx] = url
                issues[matched_id]["sources"][stage_idx] = sources
                # If artifact has a more updated status or title, note it
                if stage_idx > 1 and res.get("status"):
                    issues[matched_id]["status"] = res.get("status")

        # 3. Compute current active stage and CPN marking
        for issue_id, info in issues.items():
            completed_stages = [s for s, path in info["stages"].items() if path is not None]
            current_stage = max(completed_stages) if completed_stages else 1
            info["current_stage"] = current_stage
            info["stage_name"] = STAGE_NAMES[current_stage]
            info["cpn_place"] = CPN_PLACES[current_stage]
            info["next_transition"] = NEXT_TRANSITIONS[current_stage]

        return dict(sorted(issues.items()))

    def get_issue_detail(self, query_id: str) -> Optional[Dict[str, Any]]:
        norm_id = query_id.strip().lstrip("#")
        if norm_id.startswith("iss_"):
            norm_id = norm_id[4:]
        if norm_id.isdigit():
            norm_id = f"{int(norm_id):03d}"

        all_states = self.get_all_issue_states()
        return all_states.get(norm_id)

    def get_cpn_marking(self) -> Dict[str, int]:
        marking = {place: 0 for place in CPN_PLACES.values()}
        for issue in self.get_all_issue_states().values():
            place = issue["cpn_place"]
            marking[place] = marking.get(place, 0) + 1
        return marking


def print_table(issues: Dict[str, Dict[str, Any]]):
    print("=" * 105)
    print(" RUBIES RANGERS | ISSUE LIFECYCLE & CPN MARKING TELEMETRY")
    print("=" * 105)
    print(f" {'ID':<5} | {'Stage':<8} | {'CPN Place':<21} | {'Status':<10} | {'Title'}")
    print("-" * 6 + "+-" + "-" * 8 + "+-" + "-" * 21 + "+-" + "-" * 10 + "+-" + "-" * 51)

    for issue_id, data in issues.items():
        stage_code = f"S{data['current_stage']}"
        print(f" #{issue_id:<4} | {stage_code:<8} | {data['cpn_place']:<21} | {data['status']:<10} | {data['title'][:50]}")

    print("=" * 105)
    
    # Summary marking row
    marking_counts = {place: 0 for place in CPN_PLACES.values()}
    for data in issues.values():
        marking_counts[data["cpn_place"]] += 1
    
    summary_parts = [f"{k}: {v}" for k, v in marking_counts.items() if v > 0]
    print(f" CPN Marking Vector M: {{ {', '.join(summary_parts)} }} | Total Issues: {len(issues)}")
    print("=" * 105)


def print_detail(issue: Dict[str, Any]):
    print("=" * 90)
    print(f" ISSUE TELEMETRY: #{issue['id']} - {issue['title']}")
    print("=" * 90)
    print(f"  Current Stage    : {issue['stage_name']}")
    print(f"  CPN Place        : {issue['cpn_place']}")
    print(f"  Status           : {issue['status']}")
    print(f"  Next Transition  : {issue['next_transition']}")
    print("-" * 90)
    print("  Lineage Trace (OKF Lifecycle Artifacts):")
    for s in range(1, 7):
        path = issue["stages"].get(s)
        marker = "[x]" if path else "[ ]"
        s_name = STAGE_NAMES[s]
        display_path = path if path else "None (Pending)"
        print(f"    {marker} {s_name:<20}: {display_path}")
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(
        description="Inspect issue lifecycle states and CPN markings using ARD and OKF metadata."
    )
    parser.add_argument("--id", "-i", type=str, help="Specific Issue ID to inspect (e.g. 001, 15, #004)")
    parser.add_argument("--all", "-a", action="store_true", help="Display all issues in a formatted telemetry table")
    parser.add_argument("--stage", "-s", type=int, choices=[1, 2, 3, 4, 5, 6], help="Filter issues currently at a specific stage (1-6)")
    parser.add_argument("--marking", "-m", action="store_true", help="Output only the CPN Token Marking Vector")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON format for agent parsing")

    args = parser.parse_args()

    root = find_repo_root()
    tracker = IssueLifecycleTracker(root)

    if args.marking:
        marking = tracker.get_cpn_marking()
        if args.json:
            print(json.dumps(marking, indent=2))
        else:
            print("=" * 60)
            print(" CPN GLOBAL TOKEN MARKING VECTOR M")
            print("=" * 60)
            for place, count in marking.items():
                print(f"  {place:<22}: {count} token{'s' if count != 1 else ''}")
            print("-" * 60)
            print(f"  Total Active Issues   : {sum(marking.values())}")
            print("=" * 60)
        return

    if args.id:
        detail = tracker.get_issue_detail(args.id)
        if not detail:
            sys.stderr.write(f"Error: Issue #{args.id} not found in ARD/OKF metadata.\n")
            sys.exit(1)
        if args.json:
            print(json.dumps(detail, indent=2))
        else:
            print_detail(detail)
        return

    all_issues = tracker.get_all_issue_states()
    if args.stage:
        all_issues = {k: v for k, v in all_issues.items() if v["current_stage"] == args.stage}

    if args.json:
        print(json.dumps(all_issues, indent=2))
    else:
        print_table(all_issues)


if __name__ == "__main__":
    main()
