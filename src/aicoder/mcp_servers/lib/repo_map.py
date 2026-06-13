"""Repo Map (Skeleton) builder — the "X-ray" step of Interactive Lazy-Loading RAG.

Produces a compact map of a Java codebase: directory of files, each with its
type declarations and method/constructor signatures — NO method bodies. The
Planner reads this skeleton first (TC-CORE-03), then asks for specific symbols
via get_symbol (zoom-in, TC-CORE-04).

PageRank-style ranking (Aider-style) is a later refinement; M1 emits a
deterministic, path-sorted map.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_java
from tree_sitter import Language, Parser

_LANG = Language(tree_sitter_java.language())

_TYPE_DECLS = {
    "class_declaration",
    "interface_declaration",
    "record_declaration",
    "enum_declaration",
    "annotation_type_declaration",
}


@dataclass
class Member:
    kind: str  # "method" | "constructor"
    signature: str


@dataclass
class TypeSkeleton:
    kind: str  # "class" | "interface" | "record" | "enum" | ...
    name: str
    members: list[Member] = field(default_factory=list)


@dataclass
class FileSkeleton:
    path: str  # relative to repo_root, forward slashes
    package: str
    types: list[TypeSkeleton]


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _new_parser() -> Parser:
    return Parser(_LANG)


def _method_signature(node, src: bytes) -> str:
    name = node.child_by_field_name("name")
    ret = node.child_by_field_name("type")
    params = node.child_by_field_name("parameters")
    ret_txt = f"{_text(ret, src)} " if ret is not None else ""
    params_txt = _text(params, src) if params is not None else "()"
    return f"{ret_txt}{_text(name, src) if name else '?'}{params_txt}".strip()


def _ctor_signature(node, src: bytes) -> str:
    name = node.child_by_field_name("name")
    params = node.child_by_field_name("parameters")
    params_txt = _text(params, src) if params is not None else "()"
    return f"{_text(name, src) if name else '?'}{params_txt}"


def _type_skeleton(node, src: bytes) -> TypeSkeleton:
    name_node = node.child_by_field_name("name")
    kind = node.type.replace("_declaration", "")
    ts = TypeSkeleton(kind=kind, name=_text(name_node, src) if name_node else "?")
    body = node.child_by_field_name("body")
    if body is not None:
        for m in body.named_children:
            if m.type == "method_declaration":
                ts.members.append(Member("method", _method_signature(m, src)))
            elif m.type == "constructor_declaration":
                ts.members.append(Member("constructor", _ctor_signature(m, src)))
    return ts


def extract_file_skeleton(path: Path, repo_root: Path) -> FileSkeleton:
    src = Path(path).read_bytes()
    root = _new_parser().parse(src).root_node

    package = ""
    types: list[TypeSkeleton] = []

    # walk the whole tree, picking up every type declaration (incl. nested)
    stack = [root]
    while stack:
        node = stack.pop()
        for ch in node.named_children:
            if ch.type == "package_declaration":
                package = _text(ch, src).removeprefix("package").strip().rstrip(";").strip()
            if ch.type in _TYPE_DECLS:
                types.append(_type_skeleton(ch, src))
            stack.append(ch)

    rel = str(Path(path).relative_to(repo_root)).replace("\\", "/")
    return FileSkeleton(path=rel, package=package, types=types)


def _java_files(base: Path) -> list[Path]:
    return [
        f
        for f in sorted(base.rglob("*.java"))
        if "target" not in f.parts and not f.name.startswith("._")
    ]


def build_repo_map(
    repo_root: str | Path, subpath: str | None = None, max_files: int = 400
) -> str:
    repo_root = Path(repo_root)
    base = repo_root / subpath if subpath else repo_root
    files = _java_files(base)
    truncated = len(files) > max_files
    files = files[:max_files]

    lines = [f"# Repo Map: {base.name} ({len(files)} java files)"]
    for f in files:
        try:
            skel = extract_file_skeleton(f, repo_root)
        except Exception as exc:  # never let one bad file sink the map
            rel = str(f.relative_to(repo_root)).replace("\\", "/")
            lines.append(f"\n{rel}  <parse error: {exc}>")
            continue
        header = f"\n{skel.path}" + (f"  [{skel.package}]" if skel.package else "")
        lines.append(header)
        for t in skel.types:
            lines.append(f"  {t.kind} {t.name}")
            for m in t.members:
                lines.append(f"    {m.signature}")
    if truncated:
        lines.append(f"\n... (truncated to {max_files} files)")
    return "\n".join(lines)


def get_symbol(repo_root: str | Path, path: str, name: str) -> str | None:
    """Zoom-in: return the source of a type or method named `name` in `path`."""
    repo_root = Path(repo_root)
    target = repo_root / path
    src = target.read_bytes()
    root = _new_parser().parse(src).root_node

    stack = [root]
    while stack:
        node = stack.pop()
        for ch in node.named_children:
            if ch.type in _TYPE_DECLS or ch.type in (
                "method_declaration",
                "constructor_declaration",
            ):
                name_node = ch.child_by_field_name("name")
                if name_node is not None and _text(name_node, src) == name:
                    return _text(ch, src)
            stack.append(ch)
    return None
