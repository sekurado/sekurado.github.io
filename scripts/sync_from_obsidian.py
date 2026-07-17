#!/usr/bin/env python3
"""
Sync blog posts and projects from an Obsidian vault into this Jekyll site.

Expected vault layout::

    MyVault/
      _attachments/                         # all vault attachments
      blog/
        name.github.io/
          posts/*.md
          projects/*.md

Point ``--blog-folder`` at ``MyVault/blog/name.github.io``.
Only notes with ``publish: true`` are synced.

Attachments are resolved from the vault ``_attachments`` folder (walked up
from the blog folder) and copied into ``assets/img/``, with Obsidian embed/link
syntax rewritten for Jekyll.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
ATTACHMENTS_FOLDER_NAME = "_attachments"
POSTS_DIR = "posts"
PROJECTS_DIR = "projects"

# ![[file]] or ![[file|alt]]
EMBED_RE = re.compile(r"!\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
# [[target]] or [[target|label]] or [[target#heading]]
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")
# Markdown links/images that still point at _attachments/
ATTACHMENT_PATH_RE = re.compile(
    r"(!?\[[^\]]*\]\()_attachments/([^)\s]+)(?:\s+\"[^\"]*\")?\)"
)


@dataclass
class Note:
    path: Path
    kind: str  # "post" | "project"
    meta: dict[str, Any]
    body: str
    slug: str


@dataclass
class SyncConfig:
    blog_folder: Path
    site_folder: Path
    attachments_folder: Path
    dry_run: bool


def prompt_path(label: str, default: Path | None = None) -> Path:
    hint = f" [{default}]" if default else ""
    while True:
        raw = input(f"{label}{hint}: ").strip()
        if not raw and default is not None:
            return default
        if not raw:
            print("  Path is required.")
            continue
        path = Path(raw).expanduser().resolve()
        if path.exists():
            return path
        print(f"  Path does not exist: {path}")


def default_attachments_folder(blog_folder: Path) -> Path:
    """Walk up from the blog folder until _attachments is found (vault root)."""
    current = blog_folder.resolve()
    while True:
        candidate = current / ATTACHMENTS_FOLDER_NAME
        if candidate.is_dir():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return blog_folder.parent / ATTACHMENTS_FOLDER_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Obsidian blog notes and attachments into the Jekyll site."
    )
    parser.add_argument(
        "--blog-folder",
        type=Path,
        help=(
            "Obsidian blog folder with posts/ and projects/ "
            "(e.g. MyVault/50 - Blog/sekurado.github.io)"
        ),
    )
    parser.add_argument(
        "--site-folder",
        type=Path,
        help="Local checkout of the Jekyll site (sekurado.github.io)",
    )
    parser.add_argument(
        "--attachments-folder",
        type=Path,
        help=f"Obsidian attachments folder (default: <vault>/{ATTACHMENTS_FOLDER_NAME})",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    return parser.parse_args()


def load_yaml_list(path: Path, field: str) -> set[str]:
    if not path.is_file():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return {item["slug"] for item in data if isinstance(item, dict) and field in item}


def split_front_matter(text: str) -> tuple[dict[str, Any] | None, str]:
    if not text.startswith("---"):
        return None, text
    try:
        _, raw_fm, body = text.split("---", 2)
    except ValueError:
        return None, text
    meta = yaml.safe_load(raw_fm) or {}
    if not isinstance(meta, dict):
        return None, body.strip()
    return meta, body.strip()


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-") or "untitled"


def parse_date(value: Any, source: Path) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Invalid date {value!r} in {source}")


def collect_notes(blog_folder: Path) -> list[Note]:
    notes: list[Note] = []

    posts_dir = blog_folder / POSTS_DIR
    projects_dir = blog_folder / PROJECTS_DIR

    if posts_dir.is_dir():
        for path in sorted(posts_dir.glob("*.md")):
            meta, body = split_front_matter(path.read_text(encoding="utf-8"))
            if not meta or not meta.get("publish"):
                continue
            slug = str(meta.get("slug") or path.stem)
            notes.append(Note(path, "post", meta, body, slug))

    if projects_dir.is_dir():
        for path in sorted(projects_dir.glob("*.md")):
            meta, body = split_front_matter(path.read_text(encoding="utf-8"))
            if not meta or not meta.get("publish"):
                continue
            slug = str(meta.get("slug") or path.stem)
            notes.append(Note(path, "project", meta, body, slug))

    return notes


def build_link_map(notes: list[Note]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for note in notes:
        post_date: date | None = None
        if note.kind == "post":
            post_date = parse_date(note.meta["date"], note.path)
            url = f"/{post_date:%Y/%m/%d}/{note.slug}/"
        else:
            url = f"/project/{note.slug}/"

        keys = {
            note.slug.lower(),
            note.path.stem.lower(),
            slugify(str(note.meta.get("title", note.slug))).lower(),
        }
        for key in keys:
            mapping[key] = url
    return mapping


def resolve_attachment(attachments_folder: Path, reference: str) -> Path | None:
    reference = reference.strip().replace("\\", "/")
    direct = attachments_folder / reference
    if direct.is_file():
        return direct

    basename = Path(reference).name
    matches = list(attachments_folder.rglob(basename))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        exact = [m for m in matches if m.relative_to(attachments_folder).as_posix() == reference]
        if len(exact) == 1:
            return exact[0]
    return None


def attachment_web_path(attachments_folder: Path, file_path: Path) -> str:
    rel = file_path.relative_to(attachments_folder).as_posix()
    return f"/assets/img/{rel}"


def copy_attachment(
    attachments_folder: Path,
    site_folder: Path,
    file_path: Path,
    copied: dict[Path, str],
    dry_run: bool,
) -> str:
    if file_path in copied:
        return copied[file_path]

    rel = file_path.relative_to(attachments_folder)
    dest = site_folder / "assets" / "img" / rel
    web_path = f"/assets/img/{rel.as_posix()}"
    copied[file_path] = web_path

    if dry_run:
        print(f"  [dry-run] copy attachment {file_path} -> {dest}")
        return web_path

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, dest)
    return web_path


def transform_embed(
    match: re.Match[str],
    attachments_folder: Path,
    site_folder: Path,
    copied: dict[Path, str],
    dry_run: bool,
) -> str:
    reference = match.group(1).strip()
    alt = (match.group(2) or Path(reference).stem).strip()

    file_path = resolve_attachment(attachments_folder, reference)
    if not file_path:
        print(f"  warning: attachment not found for embed ![[{reference}]]", file=sys.stderr)
        return match.group(0)

    web_path = copy_attachment(
        attachments_folder, site_folder, file_path, copied, dry_run
    )
    if file_path.suffix.lower() in IMAGE_EXTENSIONS:
        return f"![{alt}]({web_path})"
    label = alt or file_path.name
    return f"[{label}]({web_path})"


def transform_wikilink(
    match: re.Match[str],
    link_map: dict[str, str],
    attachments_folder: Path,
    site_folder: Path,
    copied: dict[Path, str],
    dry_run: bool,
) -> str:
    target = match.group(1).strip()
    heading = match.group(2)
    label = match.group(3) or target

    file_path = resolve_attachment(attachments_folder, target)
    if file_path:
        web_path = copy_attachment(
            attachments_folder, site_folder, file_path, copied, dry_run
        )
        anchor = f"#{slugify(heading)}" if heading else ""
        return f"[{label}]({web_path}{anchor})"

    url = link_map.get(target.lower()) or link_map.get(slugify(target).lower())
    if url:
        anchor = f"#{slugify(heading)}" if heading else ""
        return f"[{label}]({url}{anchor})"

    print(f"  warning: unresolved wikilink [[{target}]]", file=sys.stderr)
    return label


def transform_content(
    body: str,
    link_map: dict[str, str],
    attachments_folder: Path,
    site_folder: Path,
    copied: dict[Path, str],
    dry_run: bool,
) -> str:
    def replace_embed(match: re.Match[str]) -> str:
        return transform_embed(
            match, attachments_folder, site_folder, copied, dry_run
        )

    def replace_wikilink(match: re.Match[str]) -> str:
        return transform_wikilink(
            match, link_map, attachments_folder, site_folder, copied, dry_run
        )

    text = EMBED_RE.sub(replace_embed, body)
    text = WIKILINK_RE.sub(replace_wikilink, text)

    def replace_attachment_path(match: re.Match[str]) -> str:
        prefix = match.group(1)
        reference = match.group(2)
        file_path = resolve_attachment(attachments_folder, reference)
        if not file_path:
            print(
                f"  warning: attachment not found for path _attachments/{reference}",
                file=sys.stderr,
            )
            return match.group(0)
        web_path = copy_attachment(
            attachments_folder, site_folder, file_path, copied, dry_run
        )
        return f"{prefix}{web_path})"

    text = ATTACHMENT_PATH_RE.sub(replace_attachment_path, text)
    return text


def build_post_front_matter(meta: dict[str, Any], post_date: date) -> dict[str, Any]:
    return {
        "title": meta["title"],
        "date": post_date.isoformat(),
        "tags": meta.get("tags") or [],
    }


def build_project_front_matter(meta: dict[str, Any]) -> dict[str, Any]:
    front_matter: dict[str, Any] = {
        "title": meta["title"],
        "category": meta["category"],
        "status": meta["status"],
        "description": meta.get("description", ""),
        "tags": meta.get("tags") or [],
    }
    if meta.get("repo"):
        front_matter["repo"] = meta["repo"]
    if meta.get("date"):
        front_matter["date"] = parse_date(meta["date"], Path("project")).isoformat()
    return front_matter


def dump_front_matter(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()


def validate_note(
    note: Note,
    categories: set[str],
    statuses: set[str],
) -> None:
    if not note.meta.get("title"):
        raise ValueError(f"Missing title in {note.path}")

    if note.kind == "post":
        parse_date(note.meta.get("date"), note.path)
        return

    if note.meta.get("category") not in categories:
        raise ValueError(
            f"Invalid category {note.meta.get('category')!r} in {note.path}. "
            f"Expected one of: {', '.join(sorted(categories))}"
        )
    if note.meta.get("status") not in statuses:
        raise ValueError(
            f"Invalid status {note.meta.get('status')!r} in {note.path}. "
            f"Expected one of: {', '.join(sorted(statuses))}"
        )


def write_note(
    dest: Path,
    front_matter: dict[str, Any],
    body: str,
    dry_run: bool,
) -> None:
    content = f"---\n{dump_front_matter(front_matter)}\n---\n\n{body}\n"
    if dry_run:
        print(f"  [dry-run] write {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def resolve_config(args: argparse.Namespace) -> SyncConfig:
    print("Obsidian → Jekyll sync\n")

    blog_default: Path | None = None
    if args.blog_folder:
        blog_folder = args.blog_folder.expanduser().resolve()
    else:
        blog_folder = prompt_path(
            "Path to Obsidian blog folder "
            "(e.g. …/blog/name.github.io)",
            blog_default,
        )

    if not (blog_folder / POSTS_DIR).is_dir() and not (blog_folder / PROJECTS_DIR).is_dir():
        print(
            f"warning: expected {POSTS_DIR}/ and/or {PROJECTS_DIR}/ under {blog_folder}",
            file=sys.stderr,
        )

    if args.site_folder:
        site_folder = args.site_folder.expanduser().resolve()
    else:
        default_site = Path(__file__).resolve().parent.parent
        site_folder = prompt_path("Path to Jekyll site folder", default_site)

    attachments_default = default_attachments_folder(blog_folder)
    if args.attachments_folder:
        attachments_folder = args.attachments_folder.expanduser().resolve()
    elif attachments_default.is_dir():
        attachments_folder = attachments_default
        print(f"Using attachments folder: {attachments_folder}")
    else:
        attachments_folder = prompt_path(
            "Path to Obsidian attachments folder",
            attachments_default,
        )

    if not attachments_folder.is_dir():
        print(f"warning: attachments folder not found: {attachments_folder}", file=sys.stderr)

    return SyncConfig(
        blog_folder=blog_folder,
        site_folder=site_folder,
        attachments_folder=attachments_folder,
        dry_run=args.dry_run,
    )


def sync(config: SyncConfig) -> int:
    notes = collect_notes(config.blog_folder)
    if not notes:
        print("No published notes found (publish: true). Nothing to do.")
        return 0

    categories = load_yaml_list(config.site_folder / "_data/categories.yml", "slug")
    statuses = load_yaml_list(config.site_folder / "_data/project_statuses.yml", "slug")
    link_map = build_link_map(notes)
    copied: dict[Path, str] = {}

    posts_written = 0
    projects_written = 0

    for note in notes:
        validate_note(note, categories, statuses)
        transformed_body = transform_content(
            note.body,
            link_map,
            config.attachments_folder,
            config.site_folder,
            copied,
            config.dry_run,
        )

        if note.kind == "post":
            post_date = parse_date(note.meta["date"], note.path)
            dest = (
                config.site_folder
                / "_posts"
                / f"{post_date.isoformat()}-{note.slug}.md"
            )
            front_matter = build_post_front_matter(note.meta, post_date)
            write_note(dest, front_matter, transformed_body, config.dry_run)
            posts_written += 1
            print(f"post: {note.path.name} -> {dest.relative_to(config.site_folder)}")
        else:
            dest = config.site_folder / "_projects" / f"{note.slug}.md"
            front_matter = build_project_front_matter(note.meta)
            write_note(dest, front_matter, transformed_body, config.dry_run)
            projects_written += 1
            print(f"project: {note.path.name} -> {dest.relative_to(config.site_folder)}")

    print(
        f"\nDone. {posts_written} post(s), {projects_written} project(s), "
        f"{len(copied)} attachment(s)"
        + (" (dry run)" if config.dry_run else "")
    )
    return 0


def main() -> int:
    try:
        args = parse_args()
        config = resolve_config(args)
        return sync(config)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
