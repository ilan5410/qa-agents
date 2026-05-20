from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

from document_map_parser import DocxMapParser


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
NS = {"w": W_NS, "r": R_NS, "pr": PKG_REL_NS}


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _xml_bytes(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def _read_xml(zf: zipfile.ZipFile, name: str) -> etree._Element:
    return etree.fromstring(zf.read(name))


def _read_optional_xml(zf: zipfile.ZipFile, name: str) -> etree._Element | None:
    if name not in zf.namelist():
        return None
    return _read_xml(zf, name)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _visible_tag_name(node: etree._Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _sdt_is_hidden(sdt: etree._Element) -> bool:
    pr = sdt.find("w:sdtPr", namespaces=NS)
    if pr is None:
        return False
    appearance = pr.find(f"{{{W15_NS}}}appearance")
    if appearance is not None and appearance.get(f"{{{W15_NS}}}val") == "hidden":
        return True
    alias = pr.find("w:alias", namespaces=NS)
    alias_val = alias.get(w("val")) if alias is not None else None
    if alias_val and "layout table" in alias_val.lower():
        return True
    tag = pr.find("w:tag", namespaces=NS)
    tag_val = tag.get(w("val")) if tag is not None else None
    if tag_val and "layout table" in tag_val.lower():
        return True
    return False


def _top_child(node: etree._Element, container: etree._Element) -> etree._Element:
    current = node
    parent = current.getparent()
    while parent is not None and parent is not container:
        current = parent
        parent = current.getparent()
    return current


@dataclass(frozen=True)
class Piece:
    text: str
    node: etree._Element
    top_child: etree._Element
    start: int
    end: int
    kind: str


def _collect_visible_pieces(container: etree._Element) -> tuple[list[Piece], bool]:
    pieces: list[Piece] = []
    has_field_codes = False
    cursor = 0

    def walk(node: etree._Element, top_child: etree._Element, in_deleted: bool = False, in_instr: bool = False) -> None:
        nonlocal cursor, has_field_codes
        tag = _visible_tag_name(node)
        if tag in {"del", "moveFrom"}:
            in_deleted = True
        if tag == "instrText":
            in_instr = True
            has_field_codes = True
        if tag in {"commentRangeStart", "commentRangeEnd", "bookmarkStart", "bookmarkEnd", "fldChar"}:
            if tag == "fldChar":
                has_field_codes = True
        elif tag == "footnoteReference":
            marker = node.get(w("id"))
            text = f"[fn:{marker}]" if marker is not None else "[fn:]"
            pieces.append(Piece(text=text, node=node, top_child=top_child, start=cursor, end=cursor + len(text), kind="footnote_reference"))
            cursor += len(text)
            return
        elif tag == "endnoteReference":
            marker = node.get(w("id"))
            text = f"[en:{marker}]" if marker is not None else "[en:]"
            pieces.append(Piece(text=text, node=node, top_child=top_child, start=cursor, end=cursor + len(text), kind="endnote_reference"))
            cursor += len(text)
            return
        elif tag in {"t", "delText"} and node.text and not in_deleted and not in_instr:
            pieces.append(Piece(text=node.text, node=node, top_child=top_child, start=cursor, end=cursor + len(node.text), kind="deleted_text" if tag == "delText" else "text"))
            cursor += len(node.text)
        elif tag == "instrText":
            if node.text:
                cursor += len(node.text)
        elif node.text and tag not in {"pPr", "rPr", "tblPr", "trPr", "tcPr", "sdtPr", "sdtEndPr"} and not in_deleted and not in_instr:
            pieces.append(Piece(text=node.text, node=node, top_child=top_child, start=cursor, end=cursor + len(node.text), kind="text"))
            cursor += len(node.text)
        for child in list(node):
            walk(child, top_child, in_deleted=in_deleted, in_instr=in_instr)
        if node.tail and not in_deleted and not in_instr:
            pieces.append(Piece(text=node.tail, node=node, top_child=top_child, start=cursor, end=cursor + len(node.tail), kind="tail"))
            cursor += len(node.tail)

    for child in list(container):
        walk(child, child)
    return pieces, has_field_codes


def _clone_child_with_span(child: etree._Element, keep_start: int | None, keep_end: int | None) -> etree._Element | None:
    clone = copy.deepcopy(child)
    original_pieces, _ = _collect_visible_pieces(child)
    clone_pieces, _ = _collect_visible_pieces(clone)
    if not original_pieces or len(original_pieces) != len(clone_pieces):
        return clone
    for original, copied in zip(original_pieces, clone_pieces):
        if copied.kind not in {"text", "deleted_text", "tail"}:
            continue
        text = original.text
        if keep_end is not None and keep_start is None:
            # Prefix fragment: keep text strictly before keep_end.
            if original.end <= keep_end:
                new_text = text
            elif original.start >= keep_end:
                new_text = ""
            else:
                new_text = text[: keep_end - original.start]
        elif keep_start is not None and keep_end is None:
            # Suffix fragment: keep text starting at keep_start.
            if original.end <= keep_start:
                new_text = ""
            elif original.start >= keep_start:
                new_text = text
            else:
                new_text = text[keep_start - original.start :]
        elif keep_start is not None and keep_end is not None:
            if original.end <= keep_start or original.start >= keep_end:
                new_text = ""
            else:
                new_text = text[max(0, keep_start - original.start): max(0, min(len(text), keep_end - original.start))]
        else:
            new_text = text
        copied.node.text = new_text
    return clone


def _visible_text_from_container(container: etree._Element) -> str:
    pieces, _ = _collect_visible_pieces(container)
    return "".join(piece.text for piece in pieces)


def _cleanup_empty_runs(container: etree._Element) -> None:
    for child in list(container):
        if _visible_tag_name(child) != "r":
            continue
        has_text = bool(child.xpath(".//w:t/text() | .//w:delText/text() | .//m:t/text()", namespaces={"w": W_NS, "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}))
        has_other = bool(child.xpath("./w:footnoteReference | ./w:endnoteReference | ./w:br | ./w:tab | ./w:commentReference | ./w:fldChar", namespaces=NS))
        if not has_text and not has_other:
            container.remove(child)


def _ensure_track_revisions(settings_root: etree._Element) -> None:
    if settings_root.find("w:trackRevisions", namespaces=NS) is None:
        settings_root.insert(0, etree.Element(w("trackRevisions")))


def _ensure_comments_root(existing: bytes | None) -> etree._Element:
    if existing is not None:
        return etree.fromstring(existing)
    return etree.Element(w("comments"), nsmap={"w": W_NS})


def _ensure_content_types(ct_root: etree._Element) -> None:
    xpath = "//*[local-name()='Override' and @PartName='/word/comments.xml']"
    if ct_root.xpath(xpath):
        return
    override = etree.Element("Override")
    override.set("PartName", "/word/comments.xml")
    override.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml")
    ct_root.append(override)


def _ensure_document_rels(rels_root: etree._Element) -> None:
    rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
    for rel in rels_root.xpath("//pr:Relationship", namespaces=NS):
        if rel.get("Type") == rel_type and rel.get("Target") == "comments.xml":
            return
    ids = []
    for rel in rels_root.xpath("//pr:Relationship", namespaces=NS):
        rid = rel.get("Id", "")
        if rid.startswith("rId") and rid[3:].isdigit():
            ids.append(int(rid[3:]))
    new_id = f"rId{(max(ids) + 1) if ids else 1}"
    rel = etree.SubElement(rels_root, f"{{{PKG_REL_NS}}}Relationship")
    rel.set("Id", new_id)
    rel.set("Type", rel_type)
    rel.set("Target", "comments.xml")


def _next_comment_id(comments_root: etree._Element, doc_root: etree._Element) -> int:
    used: set[int] = set()
    for c in comments_root.xpath("//w:comment", namespaces=NS):
        try:
            used.add(int(c.get(w("id"))))
        except Exception:
            pass
    for node in doc_root.xpath("//w:commentRangeStart | //w:commentRangeEnd | //w:commentReference", namespaces=NS):
        try:
            used.add(int(node.get(w("id"))))
        except Exception:
            pass
    return (max(used) + 1) if used else 0


def _append_comment(comments_root: etree._Element, cid: int, author: str, text: str) -> None:
    c = etree.SubElement(comments_root, w("comment"))
    c.set(w("id"), str(cid))
    c.set(w("author"), author)
    c.set(w("date"), _iso_now())
    p = etree.SubElement(c, w("p"))
    r = etree.SubElement(p, w("r"))
    t = etree.SubElement(r, w("t"))
    t.text = text


def _anchor_comment_to_paragraph(p: etree._Element, cid: int) -> None:
    insert_at = 0
    for i, child in enumerate(list(p)):
        if _visible_tag_name(child) == "pPr":
            insert_at = i + 1
    start = etree.Element(w("commentRangeStart"))
    start.set(w("id"), str(cid))
    end = etree.Element(w("commentRangeEnd"))
    end.set(w("id"), str(cid))
    ref_run = etree.Element(w("r"))
    ref = etree.SubElement(ref_run, w("commentReference"))
    ref.set(w("id"), str(cid))
    p.insert(insert_at, start)
    p.append(end)
    p.append(ref_run)


def _make_change_wrapper(tag: str, cid: int, author: str, text: str) -> etree._Element:
    outer = etree.Element(w(tag))
    outer.set(w("id"), str(cid))
    outer.set(w("author"), author)
    outer.set(w("date"), _iso_now())
    run = etree.SubElement(outer, w("r"))
    leaf_tag = "delText" if tag == "del" else "t"
    leaf = etree.SubElement(run, w(leaf_tag))
    leaf.text = text
    return outer


def _make_text_run(text: str, template_run: etree._Element | None = None) -> etree._Element:
    run = etree.Element(w("r"))
    if template_run is not None:
        rpr = template_run.find("w:rPr", namespaces=NS)
        if rpr is not None:
            run.append(copy.deepcopy(rpr))
    t = etree.SubElement(run, w("t"))
    if text[:1].isspace() or text[-1:].isspace():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return run


def _replace_inside_single_text_node(
    pieces: list[Piece],
    old: str,
    new: str,
    cid: int,
    author: str,
) -> bool:
    for piece in pieces:
        if piece.kind != "text" or old not in piece.text:
            continue
        text_node = piece.node
        parent_run = text_node.getparent()
        if parent_run is None or _visible_tag_name(parent_run) != "r":
            continue
        run_parent = parent_run.getparent()
        if run_parent is None:
            continue
        before, after = piece.text.split(old, 1)
        replacement_nodes: list[etree._Element] = []
        if before:
            replacement_nodes.append(_make_text_run(before, parent_run))
        replacement_nodes.append(_make_change_wrapper("del", cid, author, old))
        replacement_nodes.append(_make_change_wrapper("ins", cid + 1, author, new))
        if after:
            replacement_nodes.append(_make_text_run(after, parent_run))
        insert_at = run_parent.index(parent_run)
        for node in replacement_nodes:
            run_parent.insert(insert_at, node)
            insert_at += 1
        run_parent.remove(parent_run)
        return True
    return False


def _replace_text_span(container: etree._Element, old: str, new: str, cid: int, author: str) -> bool:
    pieces, _ = _collect_visible_pieces(container)
    visible = "".join(piece.text for piece in pieces)
    idx = visible.find(old)
    if idx < 0:
        return False
    end = idx + len(old)

    # Special case: inserting a single space before a footnote marker.
    if old.endswith("]") and old.count("[fn:") == 1 and new == old.replace("[fn:", " [fn:") and visible.count(old) == 1:
        marker_id = old.split("[fn:", 1)[1].split("]", 1)[0]
        marker_piece = next((p for p in pieces if p.kind == "footnote_reference" and p.text == f"[fn:{marker_id}]"), None)
        if marker_piece is not None:
            target_child = marker_piece.top_child
            child_list = list(container)
            child_idx = child_list.index(target_child)
            container.insert(child_idx, _make_change_wrapper("ins", cid, author, " "))
            return True

    if _replace_inside_single_text_node(pieces, old, new, cid, author):
        return True

    affected = [piece for piece in pieces if not (piece.end <= idx or piece.start >= end)]
    if not affected:
        return False

    first_child = affected[0].top_child
    last_child = affected[-1].top_child
    child_list = list(container)
    first_idx = child_list.index(first_child)
    last_idx = child_list.index(last_child)
    child_starts: dict[int, int] = {}
    for piece in pieces:
        child_starts.setdefault(id(piece.top_child), piece.start)

    new_children: list[etree._Element] = []
    for i, child in enumerate(child_list):
        if child is first_child:
            first_base = child_starts.get(id(first_child), 0)
            if first_child is last_child:
                prefix = _clone_child_with_span(child, None, idx - first_base)
                if prefix is not None and _visible_text_from_container(prefix) != "":
                    new_children.append(prefix)
                new_children.append(_make_change_wrapper("del", cid, author, old))
                new_children.append(_make_change_wrapper("ins", cid + 1, author, new))
                suffix = _clone_child_with_span(child, end - first_base, None)
                if suffix is not None and _visible_text_from_container(suffix) != "":
                    new_children.append(suffix)
            else:
                prefix = _clone_child_with_span(child, None, idx - first_base)
                if prefix is not None and _visible_text_from_container(prefix) != "":
                    new_children.append(prefix)
                new_children.append(_make_change_wrapper("del", cid, author, old))
                new_children.append(_make_change_wrapper("ins", cid + 1, author, new))
            continue
        if first_child is not last_child and first_idx < i < last_idx:
            continue
        if child is last_child and child is not first_child:
            last_base = child_starts.get(id(last_child), 0)
            suffix = _clone_child_with_span(child, end - last_base, None)
            if suffix is not None and _visible_text_from_container(suffix) != "":
                new_children.append(suffix)
            continue
        if i < first_idx or i > last_idx:
            new_children.append(child)

    # Preserve paragraph properties and replace the rest of the content.
    ppr = container.find("w:pPr", namespaces=NS)
    preserved = [ppr] if ppr is not None else []
    for child in list(container):
        if child is ppr:
            continue
        container.remove(child)
    for child in reversed(preserved):
        container.insert(0, child)
    insert_at = 1 if ppr is not None else 0
    for child in new_children:
        container.insert(insert_at, child)
        insert_at += 1
    _cleanup_empty_runs(container)
    return True


def _insert_space_before_footnote(container: etree._Element, marker_id: str, cid: int, author: str) -> bool:
    for i, child in enumerate(list(container)):
        if _visible_tag_name(child) == "pPr":
            continue
        if child.xpath(f".//w:footnoteReference[@w:id='{marker_id}']", namespaces=NS):
            container.insert(i, _make_change_wrapper("ins", cid, author, " "))
            return True
    return False


def _paragraphs_from_body(parser: DocxMapParser, body: etree._Element) -> list[tuple[str, etree._Element, str]]:
    entries: list[tuple[str, etree._Element, str]] = []
    para_counter = 0
    heading_path: list[str] = []
    current_section_id = "sec_0000"
    section_counter = 0
    counter = 0

    def recurse(node: etree._Element) -> None:
        nonlocal counter, para_counter, heading_path, current_section_id, section_counter
        for child in list(node):
            tag = _visible_tag_name(child)
            if tag == "sectPr":
                continue
            if tag == "sdt" and _sdt_is_hidden(child):
                continue
            if tag == "sdt":
                recurse(child)
                continue
            if tag == "p":
                counter += 1
                text = _visible_text_from_container(child).strip()
                if not text:
                    continue
                style_id, style_name = _paragraph_style_from_lxml(child)
                style_info = parser.styles.get(style_id or "")
                if parser._is_navigation_artifact(text, style_id, style_name):
                    continue
                level = parser._heading_level(style_id, style_name, style_info, text)
                if level is not None:
                    section_counter += 1
                    current_section_id = f"sec_{section_counter:04d}"
                    heading_path = parser._update_heading_path(heading_path, level, text)
                    continue
                para_counter += 1
                entries.append((f"p_{para_counter:04d}", child, current_section_id))
                continue
            recurse(child)

    def _paragraph_style_from_lxml(p: etree._Element) -> tuple[str | None, str | None]:
        ppr = p.find("w:pPr", namespaces=NS)
        if ppr is None:
            return None, None
        style_node = ppr.find("w:pStyle", namespaces=NS)
        if style_node is None:
            return None, None
        style_id = style_node.get(w("val"))
        style_name = parser.styles.get(style_id).name if style_id and style_id in parser.styles else None
        return style_id, style_name

    recurse(body)
    return entries


def _footnote_paragraphs(footnotes_root: etree._Element | None) -> dict[str, etree._Element]:
    mapping: dict[str, etree._Element] = {}
    if footnotes_root is None:
        return mapping
    for note in footnotes_root.findall(".//w:footnote", namespaces=NS):
        note_id = note.get(w("id"))
        if note_id in {"-1", "0", None}:
            continue
        paras = note.findall(".//w:p", namespaces=NS)
        if paras:
            mapping[note_id] = paras[0]
    return mapping


def _load_issue_log(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_application_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _issue_comment_text(issue: dict) -> str:
    parts = [f"[{issue['issue_id']}]", issue.get("recommended_action", "").strip(), issue.get("rationale", "").strip()]
    return " ".join(part for part in parts if part)


def _target_paragraph_issue_ids(issue: dict, mode: str) -> tuple[list[str], list[str]]:
    body_ids = []
    footnote_ids = []
    loc = issue.get("location", {})
    pid = loc.get("paragraph_id")
    if pid:
        body_ids.append(pid)
    for extra in issue.get("metadata", {}).get("additional_occurrences", []) or []:
        extra_pid = extra.get("paragraph_id")
        if extra_pid:
            body_ids.append(extra_pid)
        extra_loc = extra.get("page_or_location_if_available", "")
        if isinstance(extra_loc, str) and extra_loc.startswith("footnote:"):
            footnote_ids.append(extra_loc.split(":", 1)[1])
    if isinstance(loc.get("page_or_location_if_available"), str) and str(loc["page_or_location_if_available"]).startswith("footnote:"):
        footnote_ids.append(str(loc["page_or_location_if_available"]).split(":", 1)[1])
    return sorted(set(body_ids)), sorted(set(footnote_ids))


def _find_body_matches(body_lookup: dict[str, etree._Element], needle: str) -> list[str]:
    matches: list[str] = []
    for pid, node in body_lookup.items():
        visible = _visible_text_from_container(node)
        if needle and needle in visible:
            matches.append(pid)
    return matches


def _find_any_paragraph_matches(body_root: etree._Element, needle: str) -> list[etree._Element]:
    if not needle:
        return []
    matches: list[etree._Element] = []
    for p in body_root.findall(".//w:p", namespaces=NS):
        if needle in _visible_text_from_container(p):
            matches.append(p)
    return matches


def _apply_replacement_once(
    node: etree._Element,
    old: str,
    new: str,
    next_change_id: int,
    author: str,
) -> tuple[bool, int]:
    if _replace_text_span(node, old, new, next_change_id, author):
        return True, next_change_id + 2
    return False, next_change_id


def _apply_issue_replacements(
    issue_id: str,
    node: etree._Element,
    current_text: str,
    proposed_text: str,
    next_change_id: int,
) -> tuple[bool, int]:
    author = f"ChatGPT [{issue_id}]"
    if issue_id == "proof_0001":
        return _apply_replacement_once(node, "Bouling", "Bowling", next_change_id, author)
    if issue_id == "proof_0016":
        changed_any = False
        changed, next_change_id = _apply_replacement_once(
            node, "help identifying wether", "help identify whether", next_change_id, author
        )
        changed_any = changed_any or changed
        changed, next_change_id = _apply_replacement_once(
            node, "multiple hypothesis", "multiple hypotheses", next_change_id, author
        )
        changed_any = changed_any or changed
        return changed_any, next_change_id
    return _apply_replacement_once(node, current_text, proposed_text, next_change_id, author)


def apply_application(
    source_docx: Path,
    output_docx: Path,
    issue_log: Path,
    application_plan: Path,
    document_map: Path,
    output_log: Path,
    unresolved_path: Path,
) -> dict:
    plan = _load_application_plan(application_plan)
    issues = _load_issue_log(issue_log)["issues"]
    _ = json.loads(document_map.read_text(encoding="utf-8"))
    comment_only_ids = set(plan.get("comment_only_issue_ids", []))

    with tempfile.TemporaryDirectory() as tmpdir:
        work = Path(tmpdir)
        unzip_dir = work / "unzipped"
        unzip_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source_docx, "r") as zin:
            zin.extractall(unzip_dir)

        doc_xml = unzip_dir / "word" / "document.xml"
        doc_root = etree.parse(str(doc_xml)).getroot()
        parser = DocxMapParser(source_docx)
        try:
            body_root = doc_root.find("w:body", namespaces=NS)
            if body_root is None:
                raise RuntimeError("word/document.xml is missing w:body")
            body_paras = _paragraphs_from_body(parser, body_root)
            footnotes_path = unzip_dir / "word" / "footnotes.xml"
            footnotes_root = etree.parse(str(footnotes_path)).getroot() if footnotes_path.exists() else None
            footnote_paras = _footnote_paragraphs(footnotes_root)
        finally:
            parser.close()

        settings_path = unzip_dir / "word" / "settings.xml"
        if settings_path.exists():
            settings_root = etree.parse(str(settings_path)).getroot()
        else:
            settings_root = etree.Element(w("settings"), nsmap={"w": W_NS})
        _ensure_track_revisions(settings_root)
        settings_path.write_bytes(_xml_bytes(settings_root))

        comments_path = unzip_dir / "word" / "comments.xml"
        comments_root = _ensure_comments_root(comments_path.read_bytes() if comments_path.exists() else None)
        with zipfile.ZipFile(source_docx, "r") as zf:
            ct_root = _read_xml(zf, "[Content_Types].xml")
        _ensure_content_types(ct_root)
        (unzip_dir / "[Content_Types].xml").write_bytes(_xml_bytes(ct_root))
        rels_path = unzip_dir / "word" / "_rels" / "document.xml.rels"
        with zipfile.ZipFile(source_docx, "r") as zf:
            rels_root = _read_xml(zf, "word/_rels/document.xml.rels")
        _ensure_document_rels(rels_root)
        rels_path.write_bytes(_xml_bytes(rels_root))

        body_lookup = {pid: node for pid, node, _sid in body_paras}
        footnote_lookup = footnote_paras

        next_change_id = 1
        for node in doc_root.xpath("//w:ins | //w:del", namespaces=NS):
            try:
                next_change_id = max(next_change_id, int(node.get(w("id"))) + 1)
            except Exception:
                continue
        next_comment_id = _next_comment_id(comments_root, doc_root)

        applied: list[str] = []
        comment_only_applied: list[str] = []
        skipped: list[str] = []
        unresolved: list[dict] = []
        warnings: list[str] = []
        failures: list[str] = []

        issues_by_id = {issue["issue_id"]: issue for issue in issues}
        for issue_id in plan.get("accepted_issue_ids", []) + plan.get("comment_only_issue_ids", []):
            issue = issues_by_id.get(issue_id)
            if issue is None:
                skipped.append(issue_id)
                unresolved.append({"issue_id": issue_id, "reason": "Issue not found in issue log", "recommended_next_action": "Regenerate or reconcile the issue log."})
                continue

            body_ids, foot_ids = _target_paragraph_issue_ids(issue, plan.get("requested_mode", ""))
            is_comment_only = issue_id in comment_only_ids or issue.get("edit_safety") == "comment_only"
            current_text = issue.get("current_text", "")
            proposed_text = issue.get("proposed_change", "")

            if not body_ids and current_text:
                body_ids = _find_body_matches(body_lookup, current_text)
            if not body_ids and issue_id == "style_002":
                body_ids = _find_body_matches(body_lookup, "Bartik instrument: construction")

            if is_comment_only:
                anchor_hit = False
                for pid in body_ids:
                    node = body_lookup.get(pid)
                    if node is None:
                        continue
                    _anchor_comment_to_paragraph(node, next_comment_id)
                    _append_comment(comments_root, next_comment_id, author=f"ChatGPT [{issue_id}]", text=_issue_comment_text(issue))
                    next_comment_id += 1
                    comment_only_applied.append(issue_id)
                    anchor_hit = True
                    break
                if not anchor_hit:
                    unresolved.append({"issue_id": issue_id, "reason": "Could not locate body paragraph for comment", "recommended_next_action": "Manually anchor the comment or refresh the document map."})
                continue

            applied_here = False
            applied_locations = 0
            for pid in body_ids:
                node = body_lookup.get(pid)
                if node is None:
                    continue
                if "[fn:" in current_text and proposed_text == current_text.replace("[fn:", " [fn:"):
                    marker_id = current_text.split("[fn:", 1)[1].split("]", 1)[0]
                    if _insert_space_before_footnote(node, marker_id, next_change_id, f"ChatGPT [{issue_id}]"):
                        next_change_id += 1
                        applied_here = True
                        applied_locations += 1
                        break
                changed, next_change_id = _apply_issue_replacements(
                    issue_id, node, current_text, proposed_text, next_change_id
                )
                if changed:
                    applied_here = True
                    applied_locations += 1
            for fid in foot_ids:
                node = footnote_lookup.get(fid)
                if node is None:
                    continue
                changed, next_change_id = _apply_issue_replacements(
                    issue_id, node, current_text, proposed_text, next_change_id
                )
                if changed:
                    applied_here = True
                    applied_locations += 1
            if applied_here:
                applied.append(issue_id)
            if not applied_here:
                if current_text:
                    for node in _find_any_paragraph_matches(body_root, current_text):
                        changed, next_change_id = _apply_issue_replacements(
                            issue_id, node, current_text, proposed_text, next_change_id
                        )
                        if changed:
                            applied.append(issue_id)
                            applied_here = True
                            break
                if applied_here:
                    continue
                unresolved.append({
                    "issue_id": issue_id,
                    "reason": "Tracked-change replacement could not be anchored safely",
                    "recommended_next_action": "Review the affected paragraph and consider a comments-only annotation or manual edit.",
                })

        if comment_only_applied:
            comments_path.write_bytes(_xml_bytes(comments_root))
        elif comments_path.exists():
            comments_path.write_bytes(_xml_bytes(comments_root))
        elif comments_root.xpath("//w:comment", namespaces=NS):
            comments_path.write_bytes(_xml_bytes(comments_root))
        if footnotes_root is not None:
            footnotes_path.write_bytes(_xml_bytes(footnotes_root))
        doc_xml.write_bytes(_xml_bytes(doc_root))

        with zipfile.ZipFile(output_docx, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for root, _dirs, files in os.walk(unzip_dir):
                for file in files:
                    abs_path = Path(root) / file
                    rel_path = abs_path.relative_to(unzip_dir)
                    zout.write(abs_path, rel_path.as_posix())

    log = {
        "source_original_path": str(source_docx.resolve()),
        "working_copy_path": str(output_docx.resolve()),
        "output_docx_path": str(output_docx.resolve()),
        "application_mode": plan.get("requested_mode", "tracked_changes_for_safe_edits_and_comments"),
        "tracked_changes_requested": True,
        "tracked_changes_produced": bool(applied),
        "applied_issue_ids": applied,
        "comment_only_issue_ids": comment_only_applied,
        "skipped_issue_ids": skipped,
        "unresolved_issue_ids": [u["issue_id"] for u in unresolved],
        "rejected_issue_ids": plan.get("rejected_issue_ids", []),
        "fallback_decisions": warnings,
        "created_output_files": [str(output_docx.resolve()), str(output_log.resolve()), str(unresolved_path.resolve())],
        "warnings": warnings,
        "failures": failures,
        "document_map_path": str(document_map.resolve()),
        "issue_log_path": str(issue_log.resolve()),
    }
    output_log.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    if unresolved:
        unresolved_path.write_text(
            "\n".join(
                [
                    "# Unresolved Issues",
                    "",
                    *[
                        f"- {item['issue_id']}: {item['reason']} ({item['recommended_next_action']})"
                        for item in unresolved
                    ],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        unresolved_path.write_text("# Unresolved Issues\n\nNone.\n", encoding="utf-8")
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply approved QA changes to a DOCX reviewed copy.")
    ap.add_argument("--source-docx", required=True, type=Path)
    ap.add_argument("--output-docx", required=True, type=Path)
    ap.add_argument("--issue-log", required=True, type=Path)
    ap.add_argument("--application-plan", required=True, type=Path)
    ap.add_argument("--document-map", required=True, type=Path)
    ap.add_argument("--application-log", required=True, type=Path)
    ap.add_argument("--unresolved", required=True, type=Path)
    args = ap.parse_args()

    args.output_docx.parent.mkdir(parents=True, exist_ok=True)
    args.application_log.parent.mkdir(parents=True, exist_ok=True)
    args.unresolved.parent.mkdir(parents=True, exist_ok=True)

    apply_application(
        source_docx=args.source_docx,
        output_docx=args.output_docx,
        issue_log=args.issue_log,
        application_plan=args.application_plan,
        document_map=args.document_map,
        output_log=args.application_log,
        unresolved_path=args.unresolved,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
