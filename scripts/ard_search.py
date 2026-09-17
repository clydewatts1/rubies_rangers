"""
---
type: Tool
title: "Agentic Resource Discovery (ARD) Search CLI"
description: "Fast keyword, tag, and query search across federated ARD manifests for instant zero-crawl component discovery."
tags: [discovery, registry, python, cli, tooling]
status: Active
sources: []
generated:
  at: "2026-09-16T22:18:00Z"
  by: "agent:antigravity"
---
"""

import os
import sys
import json
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_TIERS = ["docs", "analytics", "automation", "clients", "ui", "tests", "scripts"]


def find_repo_root() -> Path:
    current = Path(__file__).resolve().parent.parent
    if (current / "ard.yaml").exists() or (current / "ard.json").exists() or (current / "docs").exists():
        return current
    cwd = Path.cwd()
    if (cwd / "ard.yaml").exists() or (cwd / "ard.json").exists() or (cwd / "docs").exists():
        return cwd
    return current


def load_manifest(manifest_path: Path) -> list:
    if not manifest_path.exists():
        return []
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("resources", [])
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to load {manifest_path}: {e}\n")
        return []


def score_resource(res: dict, query_terms: list, full_query: str) -> float:
    score = 0.0

    title = (res.get("displayName") or "").lower()
    url = (res.get("url") or "").lower()
    desc = (res.get("description") or "").lower()
    concept = (res.get("conceptType") or "").lower()
    tags = [str(t).lower() for t in res.get("tags", [])]
    queries = [q.lower() for q in res.get("representativeQueries", [])]
    sources = [str(s).lower() for s in res.get("sources", [])]

    # Exact phrase matches
    if full_query in title:
        score += 60.0
    if full_query in url:
        score += 50.0
    if any(full_query == t for t in tags):
        score += 40.0
    if any(full_query in q for q in queries):
        score += 30.0
    if full_query in desc:
        score += 25.0

    # Term matches
    for term in query_terms:
        if term == title or term == Path(url).stem.lower():
            score += 40.0
        elif term in title:
            score += 20.0

        if term in url:
            score += 15.0

        if any(term == t for t in tags):
            score += 20.0
        elif any(term in t for t in tags):
            score += 10.0

        if any(term in q for q in queries):
            score += 10.0

        if term in desc:
            score += 8.0

        if term in concept:
            score += 15.0

        if any(term in s for s in sources):
            score += 12.0

    return score


def search_ard(
    repo_root: Path,
    query: str,
    tier: str = None,
    concept_type: str = None,
    tag: str = None,
    limit: int = 10
) -> list:
    tiers_to_search = [tier] if tier and tier != "all" else DEFAULT_TIERS

    all_resources = []
    # Check tier manifests first
    for t in tiers_to_search:
        mpath = repo_root / t / "ard.json"
        resources = load_manifest(mpath)
        for r in resources:
            r["_tier"] = t
            all_resources.append(r)

    # Fallback to master ard.json if tier manifests don't exist
    if not all_resources:
        master_path = repo_root / "ard.json"
        all_resources = load_manifest(master_path)

    full_query = query.strip().lower()
    query_terms = [t for t in full_query.replace("-", " ").replace("_", " ").split() if len(t) > 1]
    if not query_terms:
        query_terms = [full_query]

    scored = []
    for res in all_resources:
        if concept_type:
            c_type = (res.get("conceptType") or "").lower()
            if concept_type.lower() not in c_type:
                continue

        if tag:
            t_req = tag.lower()
            tags = [str(t).lower() for t in res.get("tags", [])]
            if not any(t_req in t for t in tags):
                continue

        score = score_resource(res, query_terms, full_query)
        if score > 0:
            scored.append((score, res))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def format_terminal(results: list) -> str:
    if not results:
        return "No matching resources found in ARD manifests."

    lines = []
    for res in results:
        concept = res.get("conceptType") or "Resource"
        url = res.get("url") or res.get("identifier") or ""
        title = res.get("displayName") or ""
        desc = res.get("description") or ""
        sources = res.get("sources") or []
        tags = res.get("tags") or []

        lines.append(f"[{concept}] {url}")
        lines.append(f"  Title: {title}")

        if sources:
            design_src = ", ".join(str(s) for s in sources)
            lines.append(f"  Lineage: {design_src}")

        if desc:
            lines.append(f"  Description: {desc}")

        if tags:
            tag_str = ", ".join(str(t) for t in tags)
            lines.append(f"  Tags: [{tag_str}]")

        lines.append("")

    return "\n".join(lines).rstrip()


def main():
    parser = argparse.ArgumentParser(
        description="Search federated ARD manifests for instant zero-crawl component discovery."
    )
    parser.add_argument("query", nargs="*", help="Keywords, tags, or question to search")
    parser.add_argument("--tier", "-t", choices=DEFAULT_TIERS + ["all"], default="all", help="Limit search to a manifest tier")
    parser.add_argument("--type", dest="concept_type", help="Filter by concept type (e.g. Issue, Brainstorm, Design, Plan, Playbook)")
    parser.add_argument("--tag", help="Filter by tag (e.g. optimization, cpn, monte-carlo, weather)")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max results to display (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--repo-root", help="Path to repository root")

    args = parser.parse_args()

    query_str = " ".join(args.query).strip()
    if not query_str and not args.concept_type and not args.tag:
        parser.print_help()
        sys.exit(1)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()
    results = search_ard(
        repo_root,
        query_str,
        tier=args.tier,
        concept_type=args.concept_type,
        tag=args.tag,
        limit=args.limit
    )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_terminal(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
