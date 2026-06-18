"""Pure-Python regression guard over a rendered Structurizr DSL set (no docker, no infra).

`design_structurizr.render_structurizr` is meant to be valid by construction; this catches
the bug classes that have shipped elsewhere when an unvalidated DSL was accepted — so if the
generator is correct, `validate_structurizr` always returns []. It is the cheap in-process
counterpart to the real `structurizr/cli` parse that runs in CI (see render_ci_workflow).

  S1  an inline block — `{` is not the LAST token on its line (the CLI requires the block
      body on following lines): `deploymentNode "x" { containerInstance a }`.
  S2  a declaration with no space around `=` (`foo= component …`) — the tokenizer then reads
      `foo=` as one identifier and the parse breaks.
  S3  a file under an `!adrs` directory whose name is not `NNNN-*.md` (a README in that dir
      throws NumberFormatException at import).
  S4  an `![alt](embed:KEY)` in a `!docs` markdown whose KEY names no defined view.
  S5  a relationship endpoint (`a -> b`) that is never declared as an element.
  S6  two views sharing the same key.
  S7  an `!include` / `!docs` / `!adrs` target that resolves to nothing in the rendered set.

Mirrors `design_lint.py`: a pure function returning an ordered, de-duplicated list of
findings. Surfaced at the approval gate; blocks under `design.review_strict`.
"""

from __future__ import annotations

import re

# A line that opens a block: ends with `{` (rule 1). Used to spot the inline-block bug.
_OPEN_BRACE = re.compile(r"\{")
# A declared element id: `id = person|softwareSystem|container|component …`.
_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(?:person|softwareSystem|container|component|deploymentNode|infrastructureNode)\b")
# A relationship line: `a -> b "..."` (ids may be dotted, e.g. element.property — we keep the head).
_REL = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*->\s*([A-Za-z_][\w.]*)")
# A view declaration: `<type> <scope> "KEY" ["name"] {`.
_VIEW = re.compile(r'^\s*(?:systemContext|container|component|dynamic|deployment|filtered|image)\s+\S+\s+"([^"]+)"')
# `![alt](embed:KEY)`.
_EMBED = re.compile(r"embed:([A-Za-z0-9_\-]+)")
# `!include X`, `!docs X`, `!adrs X`.
_INCLUDE = re.compile(r"^\s*!(include|docs|adrs)\s+(\S+)")


def _strip_quotes(line: str) -> str:
    """Blank out double-quoted spans so an `=` or `{` inside a string is not mis-flagged."""
    return re.sub(r'"[^"]*"', '""', line)


def _is_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#") or s.startswith("//")


def _dsl_files(files: dict[str, str]) -> dict[str, str]:
    return {p: c for p, c in files.items() if p.endswith(".dsl")}


def validate_structurizr(files: dict[str, str]) -> list[str]:
    """Return an ordered, de-duplicated list of structural findings over the rendered AaC
    set ({path: content}). Empty == the generated DSL is structurally sound."""
    issues: list[str] = []
    dsl = _dsl_files(files)

    declared: set[str] = set()
    view_keys: list[str] = []
    include_targets: list[tuple[str, str, str]] = []  # (path, directive, target)

    for path, content in dsl.items():
        for lineno, raw in enumerate(content.splitlines(), 1):
            if _is_comment(raw):
                continue
            clean = _strip_quotes(raw)

            # S1 — inline block: a `{` that is not the last non-space char of the line.
            if _OPEN_BRACE.search(clean):
                if clean.rstrip()[-1:] != "{":
                    issues.append(f"S1 {path}:{lineno} inline block — `{{` must be the last "
                                  f"token on its line, body on following lines: {raw.strip()}")

            # S2 — `=` without a space on both sides (skip ==, <=, >=, !=).
            for mo in re.finditer(r"(.)=(.)", clean):
                before, after = mo.group(1), mo.group(2)
                if before in "=<>!" or after == "=":
                    continue
                if before != " " or after != " ":
                    issues.append(f"S2 {path}:{lineno} `=` needs a space on both sides "
                                  f"(`foo = component`, not `foo= component`): {raw.strip()}")
                    break

            mo = _DECL.match(raw)
            if mo:
                declared.add(mo.group(1))
            mo = _VIEW.match(raw)
            if mo:
                view_keys.append(mo.group(1))
            mo = _INCLUDE.match(raw)
            if mo:
                include_targets.append((path, mo.group(1), mo.group(2)))

    # built-in element identifiers that need no declaration.
    builtin = {"system"}
    view_key_set = set(view_keys)

    # S5 — every relationship endpoint must be a declared element.
    for path, content in dsl.items():
        for lineno, raw in enumerate(content.splitlines(), 1):
            if _is_comment(raw):
                continue
            mo = _REL.match(raw)
            if not mo:
                continue
            for ep in (mo.group(1), mo.group(2)):
                head = ep.split(".")[0]
                if head not in declared and head not in builtin:
                    issues.append(f"S5 {path}:{lineno} relationship endpoint `{ep}` is not a "
                                  f"declared element: {raw.strip()}")

    # S6 — duplicate view keys.
    for key in sorted({k for k in view_keys if view_keys.count(k) > 1}):
        issues.append(f"S6 view key `{key}` is declared more than once — keys must be unique.")

    # S4 — embed targets must resolve to a defined view key.
    for path, content in files.items():
        if not path.endswith(".md"):
            continue
        for key in _EMBED.findall(content):
            if key not in view_key_set:
                issues.append(f"S4 {path} embeds `embed:{key}` but no view defines that key "
                              f"(defined: {sorted(view_key_set) or '[]'}).")

    # S3 — files under an `!adrs` dir must be numbered `NNNN-*.md`.
    adr_dirs = {f"{path.rsplit('/', 1)[0]}/{target.strip('/')}"
                for path, directive, target in include_targets if directive == "adrs"}
    for adr_dir in adr_dirs:
        prefix = adr_dir + "/"
        for path in files:
            if path.startswith(prefix):
                base = path[len(prefix):]
                if "/" in base:
                    continue
                if not re.match(r"^\d{4}-.*\.md$", base):
                    issues.append(f"S3 {path} is under an `!adrs` directory but is not named "
                                  f"`NNNN-*.md` — a README/non-numbered file breaks `!adrs`.")

    # S7 — include / docs / adrs targets must resolve to something in the set.
    for path, directive, target in include_targets:
        base = path.rsplit("/", 1)[0]
        resolved = f"{base}/{target.strip('/')}"
        if directive == "include":
            if resolved not in files:
                issues.append(f"S7 {path} `!include {target}` resolves to no file in the set.")
        else:  # docs / adrs -> a directory with >= 1 file
            if not any(p.startswith(resolved + "/") for p in files):
                issues.append(f"S7 {path} `!{directive} {target}` resolves to an empty/missing "
                              f"directory.")

    # de-dupe, preserve first-seen order.
    seen: set[str] = set()
    out: list[str] = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
