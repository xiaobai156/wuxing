"""Mechanically extract the pure parser dependency closure from the frozen baseline."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "wuxing_crawler.py"
KERNEL_PATH = ROOT / "wuxing" / "parsers" / "kernel.py"
REGISTRY_DATA_PATH = ROOT / "wuxing" / "registry_data.py"
OCR_SCRIPT_PATH = ROOT / "wuxing" / "sources" / "ocr_script.py"

PARSER_ROOTS = {"parse_candidates_for_site", "site_authoritative_documents"}
REGISTRY_ASSIGNMENTS = {
    "BROWSER_TAB_CLICK_PATTERNS",
    "BROWSER_FIRST_URLS",
    "BROWSER_VISIBLE_TEXT_ONLY_URLS",
    "BROWSER_SKIP_CLICK_URLS",
    "BROWSER_NON_BLOCKING_LOAD_URLS",
    "ARTICLE_API_AUTHORITATIVE_ONLY_URLS",
    "BROWSER_EXACT_CLICK_HREFS",
    "CLICK_THROUGH_DETAIL_URLS",
}


def defined_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (node.name,)
    if isinstance(node, ast.Assign):
        return tuple(target.id for target in node.targets if isinstance(target, ast.Name))
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return (node.target.id,)
    return ()


def source_segment(source: str, node: ast.AST) -> str:
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
        raise RuntimeError(f"节点缺少源码位置：{type(node).__name__}")
    decorator_lines = [item.lineno for item in getattr(node, "decorator_list", ())]
    start_line = min([node.lineno, *decorator_lines])
    lines = source.splitlines()
    return "\n".join(lines[start_line - 1 : node.end_lineno]).rstrip()


def parser_closure(tree: ast.Module) -> set[str]:
    definitions: dict[str, ast.AST] = {}
    for node in tree.body:
        for name in defined_names(node):
            definitions[name] = node
    selected = set(PARSER_ROOTS)
    pending = list(PARSER_ROOTS)
    while pending:
        node = definitions.get(pending.pop())
        if node is None:
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Name) or not isinstance(child.ctx, ast.Load):
                continue
            if child.id in definitions and child.id not in selected:
                selected.add(child.id)
                pending.append(child.id)
    return selected


def write_parser_kernel(source: str, tree: ast.Module) -> None:
    selected = parser_closure(tree)
    segments = []
    for node in tree.body:
        if any(name in selected for name in defined_names(node)):
            segments.append(source_segment(source, node))
    header = '''from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Iterable
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None
'''
    KERNEL_PATH.write_text(header + "\n\n" + "\n\n\n".join(segments) + "\n", encoding="utf-8")


def write_registry_data(source: str, tree: ast.Module) -> None:
    segments = []
    for node in tree.body:
        if REGISTRY_ASSIGNMENTS.intersection(defined_names(node)):
            segments.append(source_segment(source, node))
    header = "from __future__ import annotations\n\nimport re\n"
    REGISTRY_DATA_PATH.write_text(header + "\n\n" + "\n\n\n".join(segments) + "\n", encoding="utf-8")


def write_ocr_script(source: str, tree: ast.Module) -> None:
    match = next(
        node for node in tree.body
        if "IMAGE_OCR_JS" in defined_names(node)
    )
    OCR_SCRIPT_PATH.write_text(
        "from __future__ import annotations\n\n" + source_segment(source, match) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    write_parser_kernel(source, tree)
    write_registry_data(source, tree)
    write_ocr_script(source, tree)


if __name__ == "__main__":
    main()
