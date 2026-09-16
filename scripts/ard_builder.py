"""
---
type: Tool
title: "Agentic Resource Discovery (ARD) Builder"
description: "Automatically builds federated ARD manifests by scanning OKF frontmatter in docs, analytics, automation, clients, ui, and tests."
tags: [registry, discovery, python, tooling]
status: Active
sources: []
generated:
  at: "2026-09-16T22:15:00Z"
  by: "agent:antigravity"
---
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from collections import defaultdict
import yaml

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def extract_frontmatter(file_path: Path):
    """Extracts OKF YAML frontmatter from Python docstrings or Markdown headers."""
    suffix = file_path.suffix.lower()
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return None, str(e)

    raw_yaml = None
    if suffix == ".py":
        match = re.search(r'^[ \t]*"""[ \t]*\r?\n---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n[ \t]*"""', content, re.DOTALL)
        if match:
            raw_yaml = match.group(1)
    elif suffix in (".md", ".markdown"):
        if content.lstrip("\ufeff").startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                raw_yaml = parts[1]

    if not raw_yaml:
        return None, "No OKF frontmatter"
    raw_yaml = raw_yaml.replace("\t", "  ")
    try:
        data = yaml.safe_load(raw_yaml)
        if isinstance(data, dict):
            return data, None
    except Exception as e:
        return None, f"YAML parse error: {e}"
    return None, "Invalid frontmatter"


def generate_queries(meta: dict, doc_type: str) -> list[str]:
    queries = []
    title = meta.get("title", "")
    queries.append(f"Where is the {title} {doc_type.lower()}?")
    if "tags" in meta and isinstance(meta["tags"], list) and meta["tags"]:
        queries.append(f"Show me {', '.join(str(t) for t in meta['tags'][:2])} {doc_type.lower()}s.")
    return queries


def build_manifest_for_dir(target_dir: Path, repo_root: Path, domain: str) -> dict | None:
    if not target_dir.exists():
        return None

    resources = []
    ignore_dirs = {".git", ".venv", "venv", "__pycache__", "archive", "node_modules", ".hypothesis", ".pytest_cache", "logs"}

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = sorted([d for d in dirs if d not in ignore_dirs])
        for f in sorted(files):
            if not f.endswith((".md", ".py", ".yaml")):
                continue

            file_path = Path(root) / f
            meta, err = extract_frontmatter(file_path)
            if not meta:
                continue

            rel_path = file_path.relative_to(repo_root).as_posix()
            doc_type = meta.get("type", "Document")
            slug = file_path.stem.replace("_", "-")
            urn = f"urn:clydewatts1:rubies_rangers:{domain}:{slug}"

            res = {
                "identifier": urn,
                "displayName": meta.get("title", f),
                "type": "text/markdown" if f.endswith(".md") else "text/x-python",
                "conceptType": doc_type,
                "tags": meta.get("tags", []),
                "sources": meta.get("sources", []),
                "url": rel_path,
                "description": meta.get("description", ""),
                "representativeQueries": generate_queries(meta, doc_type),
            }
            resources.append(res)

    return {"resources": resources}


def generate_and_write_okf_indexes(resources: list[dict], target_dir: Path, repo_root: Path, dry_run: bool = False):
    prefix = target_dir.name + "/"
    files_by_dir = defaultdict(list)
    dirs_by_dir = defaultdict(set)

    for res in resources:
        rel_path = res["url"]
        if rel_path.startswith(prefix):
            local_path = rel_path[len(prefix):]
        else:
            local_path = rel_path

        parts = local_path.split("/")
        if len(parts) > 1:
            dir_path = "/".join(parts[:-1])
            file_name = parts[-1]

            current = "."
            for part in parts[:-1]:
                dirs_by_dir[current].add(part)
                if current == ".":
                    current = part
                else:
                    current = current + "/" + part
        else:
            dir_path = "."
            file_name = local_path

        files_by_dir[dir_path].append({
            "title": res["displayName"],
            "url": file_name,
            "description": res.get("description", ""),
        })

    all_dirs = sorted(set(files_by_dir.keys()).union(set(dirs_by_dir.keys())))
    if not all_dirs:
        all_dirs = ["."]

    for d in all_dirs:
        lines = []
        heading = target_dir.name.capitalize() if d == "." else os.path.basename(d).capitalize()
        lines.append(f"# {heading} Index")
        lines.append("")

        if d in dirs_by_dir and dirs_by_dir[d]:
            lines.append("## Subdirectories")
            lines.append("")
            for subdir in sorted(dirs_by_dir[d]):
                lines.append(f"* [{subdir.capitalize()}]({subdir}/) - Directory")
            lines.append("")

        if d in files_by_dir and files_by_dir[d]:
            lines.append("## Documents")
            lines.append("")
            for item in sorted(files_by_dir[d], key=lambda x: x["title"]):
                desc = f" - {item['description']}" if item["description"] else ""
                lines.append(f"* [{item['title']}]({item['url']}){desc}")
            lines.append("")

        md_content = "\n".join(lines)
        actual_dir = target_dir if d == "." else target_dir / d
        index_file = actual_dir / "index.md"

        should_write = True
        if index_file.exists():
            try:
                existing_content = index_file.read_text(encoding="utf-8")
                if existing_content.replace("\r\n", "\n").strip() == md_content.replace("\r\n", "\n").strip():
                    should_write = False
            except Exception:
                should_write = True

        if dry_run:
            if should_write:
                print(f"--- Would write to {index_file.relative_to(repo_root)} ---")
                print(md_content)
        else:
            if should_write:
                actual_dir.mkdir(parents=True, exist_ok=True)
                with open(index_file, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print(f"Updated {index_file.relative_to(repo_root)} with OKF index.")


def main():
    parser = argparse.ArgumentParser(description="Build ARD JSON manifests for Rubies Rangers")
    parser.add_argument("--repo-root", default=".", help="Root of repository")
    parser.add_argument("--dry-run", action="store_true", help="Print manifests without writing")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    targets = ["docs", "analytics", "automation", "clients", "ui", "tests"]

    all_resources = []

    for t in targets:
        tdir = repo_root / t
        manifest = build_manifest_for_dir(tdir, repo_root, domain=t)
        if manifest and manifest.get("resources"):
            all_resources.extend(manifest["resources"])
            out_file = tdir / "ard.json"
            new_content = json.dumps(manifest, indent=2)

            should_write = True
            if out_file.exists():
                try:
                    existing_content = out_file.read_text(encoding="utf-8")
                    if existing_content.strip() == new_content.strip():
                        should_write = False
                except Exception:
                    should_write = True

            if args.dry_run:
                if should_write:
                    print(f"--- Would write to {out_file.relative_to(repo_root)} ---")
                else:
                    print(f"Unchanged: {out_file.relative_to(repo_root)} ({len(manifest['resources'])} resources)")
            else:
                if should_write:
                    with open(out_file, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"Updated {out_file.relative_to(repo_root)} with {len(manifest['resources'])} resources.")
                else:
                    print(f"Unchanged: {out_file.relative_to(repo_root)} ({len(manifest['resources'])} resources)")

            if t == "docs":
                generate_and_write_okf_indexes(manifest["resources"], tdir, repo_root, args.dry_run)

    # Master repository manifest at root
    master_manifest = {
        "version": "1.0",
        "namespace": "urn:air:clydewatts1:rubies_rangers",
        "resources": all_resources
    }
    master_out = repo_root / "ard.json"
    master_json = json.dumps(master_manifest, indent=2)

    if args.dry_run:
        print(f"--- Master manifest would have {len(all_resources)} total resources ---")
    else:
        with open(master_out, "w", encoding="utf-8") as f:
            f.write(master_json)
        print(f"Updated master {master_out.relative_to(repo_root)} with {len(all_resources)} total resources.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
