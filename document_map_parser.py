from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator
import xml.etree.ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NS = {
    "w": W_NS,
    "r": R_NS,
    "w15": W15_NS,
}

W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
W15 = f"{{{W15_NS}}}"

NUMERIC_RE = re.compile(
    r"""
    (?<!\w)
    (?:
        [£$€]\s?-?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|b|million|billion|thousand))?%?
        |
        -?\d[\d,]*(?:\.\d+)?%?
    )
    (?!\w)
    """,
    re.VERBOSE,
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_RE = re.compile(r"\s+")
HEADING_STYLE_RE = re.compile(r"(?:^|[^A-Za-z])Heading\s*(\d+)?", re.IGNORECASE)
REPORT_HEADING_RE = re.compile(r"^ReportHeading(\d+)?$", re.IGNORECASE)
FIELD_REFERENCE_RE = re.compile(r"\b(?:Figure|Table|Appendix|Annex)\s+\d+[A-Za-z]?\b", re.IGNORECASE)
SOURCE_NOTE_RE = re.compile(
    r"\b(?:Source|Sources|Note|Notes)\s*:\s*([^\n\r]+)",
    re.IGNORECASE,
)
TOC_STYLE_RE = re.compile(r"^TOC\d*$", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+|mailto:\S+", re.IGNORECASE)
FOOTNOTE_MARKER_RE = re.compile(r"\[fn:(\d+)\]")


@dataclass(frozen=True)
class StyleInfo:
    style_id: str
    name: str | None
    outline_level: int | None
    based_on: str | None
    style_type: str | None


@dataclass(frozen=True)
class BlockText:
    location: str
    text: str
    kind: str
    table_id: str | None = None
    table_element: ET.Element | None = None
    row_index: int | None = None
    col_index: int | None = None


def qn(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def qn15(tag: str) -> str:
    return f"{{{W15_NS}}}{tag}"


def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def compact_summary(text: str, limit: int = 240) -> str:
    text = normalize_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def is_true_like(value: str | None) -> bool:
    return value in {"true", "1", "yes", "on"}


def local_name(elem: ET.Element) -> str:
    return strip_ns(elem.tag)


class DocxMapParser:
    def __init__(self, docx_path: Path):
        self.docx_path = docx_path
        self.zf = zipfile.ZipFile(docx_path)
        self.styles = self._load_styles()
        self.footnotes = self._load_footnotes()
        self.endnotes = self._load_endnotes()
        self.comments = self._load_comments()
        self.relationships = self._load_relationships("word/_rels/document.xml.rels")
        self.document = self._load_xml("word/document.xml")
        self.body = self.document.find("w:body", NS)
        if self.body is None:
            raise ValueError("word/document.xml does not contain w:body")

    def close(self) -> None:
        self.zf.close()

    def _load_xml(self, name: str) -> ET.Element:
        with self.zf.open(name) as fh:
            return ET.parse(fh).getroot()

    def _load_optional_xml(self, name: str) -> ET.Element | None:
        if name not in self.zf.namelist():
            return None
        return self._load_xml(name)

    def _load_styles(self) -> dict[str, StyleInfo]:
        root = self._load_optional_xml("word/styles.xml")
        styles: dict[str, StyleInfo] = {}
        if root is None:
            return styles
        for style in root.findall("w:style", NS):
            style_id = style.get(qn("styleId"), "")
            name_node = style.find("w:name", NS)
            outline_node = style.find("w:pPr/w:outlineLvl", NS)
            based_on_node = style.find("w:basedOn", NS)
            style_type = style.get(qn("type"))
            outline_level = None
            if outline_node is not None:
                outline_raw = outline_node.get(qn("val"))
                if outline_raw is not None and outline_raw.isdigit():
                    outline_level = int(outline_raw)
            styles[style_id] = StyleInfo(
                style_id=style_id,
                name=name_node.get(qn("val")) if name_node is not None else None,
                outline_level=outline_level,
                based_on=based_on_node.get(qn("val")) if based_on_node is not None else None,
                style_type=style_type,
            )
        return styles

    def _load_footnotes(self) -> dict[str, ET.Element]:
        root = self._load_optional_xml("word/footnotes.xml")
        if root is None:
            return {}
        notes: dict[str, ET.Element] = {}
        for node in root.findall("w:footnote", NS):
            note_id = node.get(qn("id"))
            if note_id is not None:
                notes[note_id] = node
        return notes

    def _load_endnotes(self) -> dict[str, ET.Element]:
        root = self._load_optional_xml("word/endnotes.xml")
        if root is None:
            return {}
        notes: dict[str, ET.Element] = {}
        for node in root.findall("w:endnote", NS):
            note_id = node.get(qn("id"))
            if note_id is not None:
                notes[note_id] = node
        return notes

    def _load_comments(self) -> dict[str, ET.Element]:
        root = self._load_optional_xml("word/comments.xml")
        if root is None:
            return {}
        comments: dict[str, ET.Element] = {}
        for node in root.findall("w:comment", NS):
            comment_id = node.get(qn("id"))
            if comment_id is not None:
                comments[comment_id] = node
        return comments

    def _load_relationships(self, rel_path: str) -> dict[str, str]:
        root = self._load_optional_xml(rel_path)
        if root is None:
            return {}
        rels: dict[str, str] = {}
        for rel in root:
            rel_id = rel.get(f"{{{R_NS}}}Id")
            target = rel.get(f"{{{R_NS}}}Target")
            if rel_id and target:
                rels[rel_id] = target
        return rels

    def build(self, document_id: str) -> dict:
        paragraphs: list[dict] = []
        headings: list[dict] = []
        tables: list[dict] = []
        footnote_parts: list[dict] = []
        reference_parts: list[dict] = []
        numeric_claims: list[dict] = []
        extraction_notes: list[str] = []
        limitations: list[str] = []
        seen_references: set[tuple[str, str]] = set()

        section_counter = 0
        paragraph_counter = 0
        table_counter = 0
        reference_counter = 0
        numeric_counter = 0
        heading_path: list[str] = []
        current_section_id = "sec_0000"

        if self._package_has_tracked_changes():
            extraction_notes.append(
                "Tracked changes are present in the source package; deleted text and instruction text were skipped during visible-text assembly."
            )
        if self.comments:
            extraction_notes.append(
                "Comment markers are present in the source package; comments were not converted into document content."
            )

        for block in self._iter_body_blocks(self.body):
            if block.kind == "paragraph":
                paragraph = block.text
                style_id, style_name = self._paragraph_style(block.location)
                style_info = self.styles.get(style_id or "")
                if self._is_navigation_artifact(paragraph, style_id, style_name):
                    continue
                level = self._heading_level(style_id, style_name, style_info, paragraph)
                if level is not None:
                    section_counter += 1
                    current_section_id = f"sec_{section_counter:04d}"
                    heading_path = self._update_heading_path(heading_path, level, paragraph)
                    headings.append(
                        {
                            "section_id": current_section_id,
                            "heading_path": heading_path.copy(),
                            "text": paragraph,
                            "level": level,
                            "page_or_location_if_available": None,
                        }
                    )
                    continue

                paragraph_counter += 1
                paragraph_id = f"p_{paragraph_counter:04d}"
                paragraph_entry = {
                    "paragraph_id": paragraph_id,
                    "section_id": current_section_id,
                    "heading_path": heading_path.copy(),
                    "text": paragraph,
                    "page_or_location_if_available": None,
                    "style_if_available": style_name or style_id,
                }
                paragraphs.append(paragraph_entry)
                numeric_claims.extend(
                    self._extract_numeric_claims_from_text(
                        text=paragraph,
                        location=paragraph_id,
                        surrounding=paragraph,
                        section_id=current_section_id,
                        heading_path=heading_path,
                        table_context=None,
                        start_index=numeric_counter,
                    )
                )
                numeric_counter = len(numeric_claims)
                reference_parts.extend(
                    self._extract_reference_parts(
                        text=paragraph,
                        location=paragraph_id,
                        section_id=current_section_id,
                        heading_path=heading_path,
                        seen=seen_references,
                        next_id=reference_counter,
                    )
                )
                reference_counter = len(reference_parts)

            elif block.kind == "table":
                table_counter += 1
                table_id = f"t_{table_counter:04d}"
                table_element = self._location_lookup.get(block.location)
                table_entry, table_claims, table_refs = self._extract_table(
                    table_element=table_element,
                    table_id=table_id,
                    section_id=current_section_id,
                    heading_path=heading_path,
                    next_numeric_id=numeric_counter,
                    next_reference_id=reference_counter,
                    seen_references=seen_references,
                )
                if table_entry is not None:
                    tables.append(table_entry)
                    numeric_claims.extend(table_claims)
                    reference_parts.extend(table_refs)
                    numeric_counter = len(numeric_claims)
                    reference_counter = len(reference_parts)

        footnote_parts, footnote_claims, footnote_refs = self._extract_footnotes_and_endnotes(
            heading_path=heading_path,
            start_numeric_id=len(numeric_claims),
            start_reference_id=len(reference_parts),
            seen_references=seen_references,
        )
        numeric_claims.extend(footnote_claims)
        reference_parts.extend(footnote_refs)

        if not tables:
            limitations.append("No visible tables were extracted from the package after filtering hidden layout scaffolding.")
        if not footnote_parts and self.footnotes:
            limitations.append("Footnote part was present but no usable footnote content was extracted.")
        if not self.relationships:
            limitations.append("No document relationships part was available for hyperlink or footnote linkage resolution.")
        limitations.append("Page numbers are not available from DOCX text extraction.")
        limitations.append("Field codes, comments, and tracked revisions were only partially interpreted for visible-text reconstruction.")
        limitations.append("Hidden layout wrappers were filtered heuristically and may undercount non-text content in unusual templates.")

        return {
            "document_id": document_id,
            "source_docx_path": str(self.docx_path.resolve()),
            "headings": headings,
            "paragraphs": paragraphs,
            "tables": tables,
            "footnotes": footnote_parts,
            "references": reference_parts,
            "numeric_claims": numeric_claims,
            "extraction_notes": extraction_notes
            or [
                "Headings were inferred from Word styles where available.",
                "Page locations are omitted because DOCX text extraction does not provide them directly.",
            ],
            "limitations": limitations,
        }

    def _package_has_tracked_changes(self) -> bool:
        doc_xml = self.document
        return bool(doc_xml.findall(".//w:ins", NS) or doc_xml.findall(".//w:del", NS))

    def _paragraph_style(self, block_location: str) -> tuple[str | None, str | None]:
        # `block_location` carries the XML path-like token used by the iterator.
        node = self._location_lookup.get(block_location)
        if node is None:
            return None, None
        ppr = node.find("w:pPr", NS)
        if ppr is None:
            return None, None
        style_node = ppr.find("w:pStyle", NS)
        if style_node is None:
            return None, None
        style_id = style_node.get(qn("val"))
        style_name = None
        if style_id and style_id in self.styles:
            style_name = self.styles[style_id].name
        return style_id, style_name

    def _heading_level(
        self,
        style_id: str | None,
        style_name: str | None,
        style_info: StyleInfo | None,
        text: str,
    ) -> int | None:
        if self._is_navigation_artifact(text, style_id, style_name):
            return None
        candidates = [style_id or "", style_name or ""]
        if style_info and style_info.outline_level is not None:
            return style_info.outline_level + 1
        for candidate in candidates:
            if not candidate:
                continue
            match = re.search(r"Heading\s*(\d+)", candidate, re.IGNORECASE)
            if match:
                return max(1, int(match.group(1)))
            match = REPORT_HEADING_RE.match(candidate)
            if match:
                return int(match.group(1) or 1)
        if style_id in {"Title"} or style_name in {"Title"}:
            return 1
        return None

    def _is_navigation_artifact(
        self,
        text: str,
        style_id: str | None,
        style_name: str | None,
    ) -> bool:
        lowered = normalize_text(text).lower()
        if lowered in {"top of form", "bottom of form", "table of contents"}:
            return True
        for candidate in (style_id or "", style_name or ""):
            if not candidate:
                continue
            if candidate.lower().startswith("toc"):
                return True
            if TOC_STYLE_RE.match(candidate):
                return True
        return False

    def _update_heading_path(self, current: list[str], level: int, text: str) -> list[str]:
        updated = current[: max(level - 1, 0)]
        updated.append(text)
        return updated

    def _iter_body_blocks(self, body: ET.Element) -> Iterator[BlockText]:
        self._location_lookup: dict[str, ET.Element] = {}
        counter = 0

        def recurse(node: ET.Element, hidden: bool = False) -> Iterator[BlockText]:
            nonlocal counter
            for child in list(node):
                tag = local_name(child)
                if tag == "sectPr":
                    continue
                if tag == "sdt" and self._sdt_is_hidden(child):
                    continue
                if tag == "sdt":
                    yield from recurse(child, hidden=hidden)
                    continue
                if tag == "p":
                    counter += 1
                    token = f"node_{counter:05d}"
                    self._location_lookup[token] = child
                    text = self._paragraph_visible_text(child)
                    if text:
                        yield BlockText(location=token, text=text, kind="paragraph")
                    continue
                if tag == "tbl":
                    counter += 1
                    token = f"node_{counter:05d}"
                    self._location_lookup[token] = child
                    yield BlockText(
                        location=token,
                        text=self._table_visible_text(child),
                        kind="table",
                        table_id=token,
                        table_element=child,
                    )
                    continue
                yield from recurse(child, hidden=hidden)

        yield from recurse(body)

    def _sdt_is_hidden(self, sdt: ET.Element) -> bool:
        pr = sdt.find("w:sdtPr", NS)
        if pr is None:
            return False
        appearance = pr.find("w15:appearance", NS)
        if appearance is not None and appearance.get(qn15("val")) == "hidden":
            return True
        alias = pr.find("w:alias", NS)
        alias_val = alias.get(qn("val")) if alias is not None else None
        if alias_val and "layout table" in alias_val.lower():
            return True
        tag = pr.find("w:tag", NS)
        tag_val = tag.get(qn("val")) if tag is not None else None
        if tag_val and "layout table" in tag_val.lower():
            return True
        return False

    def _paragraph_visible_text(self, paragraph: ET.Element) -> str:
        return normalize_text(self._visible_text(paragraph))

    def _visible_text(self, element: ET.Element) -> str:
        parts: list[str] = []

        def walk(node: ET.Element, in_deleted: bool = False, in_instr: bool = False) -> None:
            tag = local_name(node)
            if tag in {"del", "moveFrom"}:
                in_deleted = True
            if tag in {"instrText"}:
                in_instr = True
            if tag in {"commentRangeStart", "commentRangeEnd", "bookmarkStart", "bookmarkEnd", "fldChar"}:
                pass
            elif tag == "tab":
                parts.append("\t")
            elif tag in {"br", "cr"}:
                parts.append("\n")
            elif tag == "footnoteReference":
                marker = node.get(qn("id"))
                if marker is not None:
                    parts.append(f"[fn:{marker}]")
            elif tag == "endnoteReference":
                marker = node.get(qn("id"))
                if marker is not None:
                    parts.append(f"[en:{marker}]")
            elif tag in {"t", "delText"} and not in_deleted and not in_instr:
                if node.text:
                    parts.append(node.text)
            elif node.text and tag not in {"pPr", "rPr", "tblPr", "trPr", "tcPr", "sdtPr", "sdtEndPr"} and not in_deleted and not in_instr:
                parts.append(node.text)
            for child in list(node):
                walk(child, in_deleted=in_deleted, in_instr=in_instr)
            if node.tail and not in_deleted and not in_instr:
                parts.append(node.tail)

        walk(element)
        return normalize_text("".join(parts))

    def _table_visible_text(self, tbl: ET.Element) -> str:
        return self._visible_text(tbl)

    def _extract_table(
        self,
        table_element: ET.Element | None,
        table_id: str,
        section_id: str,
        heading_path: list[str],
        next_numeric_id: int,
        next_reference_id: int,
        seen_references: set[tuple[str, str]],
    ) -> tuple[dict | None, list[dict], list[dict]]:
        if table_element is None:
            return None, [], []
        rows: list[list[str]] = []
        row_cells_text: list[str] = []
        table_claims: list[dict] = []
        table_refs: list[dict] = []
        for row_index, row in enumerate(table_element.findall(".//w:tr", NS), start=1):
            row_values: list[str] = []
            for col_index, cell in enumerate(row.findall("w:tc", NS), start=1):
                cell_text = self._visible_text(cell)
                cell_text = normalize_text(cell_text)
                row_values.append(cell_text)
            if any(cell.strip() for cell in row_values):
                rows.append(row_values)
                row_cells_text.append(" | ".join(cell for cell in row_values if cell))

        visible_rows = [row for row in rows if any(cell.strip() for cell in row)]
        if not visible_rows:
            return None, [], []

        first_row = visible_rows[0]
        flat_cells = [cell for row in visible_rows for cell in row if cell]
        summary_bits = [f"{len(visible_rows)} row(s)", f"{max((len(r) for r in visible_rows), default=0)} column(s)"]
        if first_row:
            summary_bits.append(f"header: {' / '.join(first_row[:3])}")
        if flat_cells:
            summary_bits.append(f"cells: {compact_summary('; '.join(flat_cells[:6]), 160)}")

        table_entry = {
            "id": table_id,
            "location": f"{section_id}/{table_id}",
            "summary": compact_summary(" ; ".join(summary_bits), 240),
        }

        table_claims.extend(
            self._extract_numeric_claims_from_text(
                text="\n".join(row_cells_text),
                location=table_id,
                surrounding="\n".join(row_cells_text),
                section_id=section_id,
                heading_path=heading_path,
                table_context=table_id,
                start_index=next_numeric_id,
            )
        )
        table_refs.extend(
            self._extract_reference_parts(
                text="\n".join(row_cells_text),
                location=table_id,
                section_id=section_id,
                heading_path=heading_path,
                seen=seen_references,
                next_id=next_reference_id,
            )
        )
        return table_entry, table_claims, table_refs

    def _extract_reference_parts(
        self,
        text: str,
        location: str,
        section_id: str,
        heading_path: list[str],
        seen: set[tuple[str, str]],
        next_id: int,
    ) -> list[dict]:
        parts: list[dict] = []
        text = normalize_text(text)
        matches: list[str] = []

        for pattern in (SOURCE_NOTE_RE, FIELD_REFERENCE_RE):
            for match in pattern.finditer(text):
                matches.append(match.group(0))
        for match in URL_RE.finditer(text):
            matches.append(match.group(0))
        for match in FOOTNOTE_MARKER_RE.finditer(text):
            matches.append(f"Footnote reference {match.group(1)}")

        if not matches:
            return parts

        for match_text in matches:
            key = (location, match_text)
            if key in seen:
                continue
            seen.add(key)
            next_id += 1
            parts.append(
                {
                    "id": f"ref_{next_id:04d}",
                    "location": location,
                    "summary": compact_summary(match_text, 240),
                    "section_id": section_id,
                    "heading_path": heading_path.copy(),
                }
            )
        return parts

    def _extract_numeric_claims_from_text(
        self,
        text: str,
        location: str,
        surrounding: str,
        section_id: str,
        heading_path: list[str],
        table_context: str | None,
        start_index: int,
    ) -> list[dict]:
        claims: list[dict] = []
        text = normalize_text(text)
        if not text:
            return claims
        sentences = SENTENCE_SPLIT_RE.split(text) if text else [text]
        next_id = start_index
        for sentence in sentences:
            sentence = normalize_text(sentence)
            if not sentence:
                continue
            for match in NUMERIC_RE.finditer(sentence):
                value = match.group(0)
                if not re.search(r"\d", value):
                    continue
                next_id += 1
                unit = "%"
                if value.startswith(("£", "$", "€")):
                    unit = value[0]
                elif value.endswith("%"):
                    unit = "%"
                else:
                    unit = None
                claims.append(
                    {
                        "claim_id": f"num_{next_id:04d}",
                        "location": location,
                        "raw_text": value,
                        "number": self._claim_number(value),
                        "unit": unit,
                        "surrounding_sentence": compact_summary(sentence, 280),
                        "nearby_table_or_figure_if_available": table_context
                        or self._nearby_table_or_figure(sentence),
                    }
                )
        return claims

    def _claim_number(self, value: str) -> int | float | str:
        stripped = value.lstrip("£$€").rstrip("%")
        stripped = stripped.replace(",", "")
        stripped = stripped.replace(" ", "")
        if stripped and stripped[0] == "-" and stripped[1:].isdigit():
            try:
                return int(stripped)
            except ValueError:
                return stripped
        try:
            if "." in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped

    def _nearby_table_or_figure(self, sentence: str) -> str | None:
        match = FIELD_REFERENCE_RE.search(sentence)
        if match:
            return match.group(0)
        return None

    def _extract_footnotes_and_endnotes(
        self,
        heading_path: list[str],
        start_numeric_id: int,
        start_reference_id: int,
        seen_references: set[tuple[str, str]],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        parts: list[dict] = []
        numeric_claims: list[dict] = []
        refs: list[dict] = []
        next_footnote_id = 0
        next_numeric_id = start_numeric_id
        next_reference_id = start_reference_id

        for note_id, note in self.footnotes.items():
            if note_id in {"-1", "0"}:
                continue
            text = self._visible_text(note)
            text = normalize_text(text)
            if not text:
                continue
            next_footnote_id += 1
            part_id = f"fn_{next_footnote_id:04d}"
            parts.append(
                {
                    "id": part_id,
                    "location": f"footnote:{note_id}",
                    "summary": compact_summary(text, 240),
                    "note_id": note_id,
                }
            )
            numeric_claims.extend(
                self._extract_numeric_claims_from_text(
                    text=text,
                    location=part_id,
                    surrounding=text,
                    section_id="sec_0000",
                    heading_path=heading_path,
                    table_context=None,
                    start_index=next_numeric_id,
                )
            )
            next_numeric_id = start_numeric_id + len(numeric_claims)
            refs.extend(
                self._extract_reference_parts(
                    text=text,
                    location=part_id,
                    section_id="sec_0000",
                    heading_path=heading_path,
                    seen=seen_references,
                    next_id=next_reference_id,
                )
            )
            next_reference_id = start_reference_id + len(refs)

        for note_id, note in self.endnotes.items():
            text = normalize_text(self._visible_text(note))
            if not text:
                continue
            next_footnote_id += 1
            part_id = f"fn_{next_footnote_id:04d}"
            parts.append(
                {
                    "id": part_id,
                    "location": f"endnote:{note_id}",
                    "summary": compact_summary(text, 240),
                    "note_id": note_id,
                }
            )
            numeric_claims.extend(
                self._extract_numeric_claims_from_text(
                    text=text,
                    location=part_id,
                    surrounding=text,
                    section_id="sec_0000",
                    heading_path=heading_path,
                    table_context=None,
                    start_index=next_numeric_id,
                )
            )
            next_numeric_id = start_numeric_id + len(numeric_claims)
            refs.extend(
                self._extract_reference_parts(
                    text=text,
                    location=part_id,
                    section_id="sec_0000",
                    heading_path=heading_path,
                    seen=seen_references,
                    next_id=next_reference_id,
                )
            )
            next_reference_id = start_reference_id + len(refs)

        return parts, numeric_claims, refs


def parse_document_map(docx_path: Path, document_id: str | None = None) -> dict:
    parser = DocxMapParser(docx_path)
    try:
        return parser.build(document_id or docx_path.stem)
    finally:
        parser.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract a document map from a DOCX file.")
    parser.add_argument("docx_path", type=Path, help="Path to the source DOCX file")
    parser.add_argument("--document-id", default=None, help="Document id to embed in the output JSON")
    parser.add_argument("--output", type=Path, default=None, help="Write the JSON output to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    document_map = parse_document_map(args.docx_path, args.document_id)
    rendered = json.dumps(document_map, ensure_ascii=False, separators=(",", ":"))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
