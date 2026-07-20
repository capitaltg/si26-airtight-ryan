#!/usr/bin/env python3
"""Regenerate the project-structure tree in AGENTS.md from the git index.

Runs as a pre-commit hook. It rebuilds the block between the
`<!-- STRUCTURE:START -->` and `<!-- STRUCTURE:END -->` markers from the files
git currently tracks (staged state), while preserving any `# comment` a human
wrote next to a path in the existing tree. Comments are matched by full
repo-relative path, so renaming a file drops its old comment and adding a file
gives an uncommented line you can annotate by hand.

No third-party deps. Exits 0 and does nothing if the repo, AGENTS.md, or the
markers are missing, so it never blocks a commit on its own plumbing.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

START = "<!-- STRUCTURE:START -->"
END = "<!-- STRUCTURE:END -->"
COMMENT_COL = 33  # column where `# comment` starts, matching the existing tree

# Path prefixes never worth listing even if git happens to track something under
# them. git ls-files already drops gitignored paths, so this is a thin backstop.
SKIP_PREFIXES = ("node_modules/", ".git/")


def repo_root() -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return Path(out.stdout.strip())


def tracked_files(root: Path) -> list[str]:
    # tracked + untracked-but-not-ignored, so the tree mirrors what is actually
    # in the working dir minus gitignored junk (node_modules, .env, __pycache__).
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    files = {line for line in out.stdout.splitlines() if line}
    return [f for f in sorted(files) if not f.startswith(SKIP_PREFIXES)]


# --- parse existing tree: full path -> comment ------------------------------

_LINE = re.compile(r"^((?:(?:│  )|(?:   ))*)([├└])─ (.*)$")


def parse_comments(block_lines: list[str]) -> dict[str, str]:
    """Map repo-relative path -> comment from the current tree block."""
    comments: dict[str, str] = {}
    names_by_level: dict[int, str] = {}
    for raw in block_lines:
        m = _LINE.match(raw)
        if not m:
            continue
        level = len(m.group(1)) // 3 + 1  # top children are level 1
        rest = m.group(3)
        # split trailing "   # comment"
        name_part, comment = rest, None
        hash_at = rest.find("#")
        if hash_at != -1:
            name_part = rest[:hash_at].rstrip()
            comment = rest[hash_at + 1 :].strip()
        name = name_part.strip().rstrip("/")
        names_by_level[level] = name
        for deeper in [k for k in names_by_level if k > level]:
            del names_by_level[deeper]
        path = "/".join(names_by_level[k] for k in range(1, level + 1))
        if comment:
            comments[path] = comment
    return comments


# --- build nested tree from the flat path list ------------------------------


def build_tree(files: list[str]) -> dict:
    tree: dict = {}
    for f in files:
        parts = f.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        # leaf: mark file with None unless a dir already claimed the name
        node.setdefault(parts[-1], None)
    return tree


def render(node: dict, prefix: str, path_parts: list[str], comments: dict[str, str]) -> list[str]:
    lines: list[str] = []
    # directories (value is a dict) first, then files, each alphabetical
    entries = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0].lower()))
    for i, (name, child) in enumerate(entries):
        last = i == len(entries) - 1
        connector = "└─ " if last else "├─ "
        display = name + ("/" if isinstance(child, dict) else "")
        text = prefix + connector + display
        cur_path = "/".join(path_parts + [name])
        comment = comments.get(cur_path)
        if comment:
            pad = " " * max(1, COMMENT_COL - len(text))
            text = f"{text}{pad}# {comment}"
        lines.append(text)
        if isinstance(child, dict):
            ext = "   " if last else "│  "
            lines.extend(render(child, prefix + ext, path_parts + [name], comments))
    return lines


def main() -> int:
    root = repo_root()
    if root is None:
        return 0
    claude = root / "AGENTS.md"
    if not claude.exists():
        return 0
    content = claude.read_text()
    if START not in content or END not in content:
        return 0

    pre, rest = content.split(START, 1)
    _old_block, post = rest.split(END, 1)

    old_lines = _old_block.splitlines()
    comments = parse_comments(old_lines)

    files = tracked_files(root)
    tree = build_tree(files)
    body = [f"{root.name}/"] + render(tree, "", [], comments)

    new_block = "\n```\n" + "\n".join(body) + "\n```\n"
    new_content = pre + START + new_block + END + post

    if new_content != content:
        claude.write_text(new_content)
        print("update_structure: refreshed AGENTS.md tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
