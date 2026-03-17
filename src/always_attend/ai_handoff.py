"""Prepare source artifacts for external multimodal AI processing."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from always_attend.agent_protocol import SourceArtifact


COURSE_RE = re.compile(r"\b[A-Z]{3}\d{4}\b")
WEEK_RE = re.compile(r"\bweek\s*(\d{1,2})\b", re.I)
GROUP_RE = re.compile(r"\b(?:group|grp)\s*([A-Za-z0-9_-]+)\b", re.I)


IMAGE_URL_RE = re.compile(r"https?://[^\s\"'<>]+?\.(?:png|jpg|jpeg|webp|gif)(?:\?[^\s\"'<>]*)?", re.I)


class _ImageUrlExtractor(HTMLParser):
    """Extract image URLs from HTML fragments."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag.lower() != "img":
            return
        for key, value in attrs:
            if key.lower() == "src" and value:
                self.urls.append(value)


def _iter_text_nodes(payload: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            texts.extend(_iter_text_nodes(value))
    elif isinstance(payload, list):
        for value in payload:
            texts.extend(_iter_text_nodes(value))
    elif isinstance(payload, str):
        texts.append(payload)
    return texts


def _extract_course_code(text: str) -> str | None:
    match = COURSE_RE.search((text or "").upper())
    if match:
        return match.group(0)
    return None


def _extract_image_urls(texts: list[str]) -> list[str]:
    urls: list[str] = []
    for text in texts:
        urls.extend(IMAGE_URL_RE.findall(text))
        if "<img" in text.lower():
            parser = _ImageUrlExtractor()
            parser.feed(text)
            urls.extend(parser.urls)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _extract_week_hints(texts: list[str]) -> list[int]:
    values: set[int] = set()
    for text in texts:
        for match in WEEK_RE.finditer(text):
            values.add(int(match.group(1)))
    return sorted(values)


def _extract_group_hints(texts: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in GROUP_RE.finditer(text):
            group = match.group(1).upper()
            if group in seen:
                continue
            seen.add(group)
            values.append(group)
    return values


def _filter_texts_by_week(texts: list[str], requested_week: int | None) -> list[str]:
    if requested_week is None:
        return texts
    filtered: list[str] = []
    for text in texts:
        weeks = [int(match.group(1)) for match in WEEK_RE.finditer(text)]
        if not weeks or requested_week in weeks:
            filtered.append(text)
    return filtered


def _artifact_kind(*, has_images: bool, has_html: bool, has_text: bool) -> str:
    if has_images and has_text:
        return "mixed"
    if has_images:
        return "image"
    if has_html and has_text:
        return "html"
    return "text"


def _extract_text_snippets(texts: list[str], *, limit: int = 8) -> list[str]:
    snippets: list[str] = []
    for text in texts:
        normalized = re.sub(r"\s+", " ", text).strip()
        if len(normalized) < 20:
            continue
        snippets.append(normalized[:400])
    deduped: list[str] = []
    seen: set[str] = set()
    for snippet in snippets:
        if snippet in seen:
            continue
        seen.add(snippet)
        deduped.append(snippet)
    return deduped[:limit]


def build_source_artifact(
    *,
    source: str,
    command: list[str],
    payload: Any,
    requested_courses: set[str],
    requested_week: int | None = None,
) -> SourceArtifact:
    """Build a compact handoff artifact from a source payload."""
    texts = _iter_text_nodes(payload)
    has_html = any("<" in text and ">" in text for text in texts)
    image_urls = _extract_image_urls(texts)
    filtered_texts = _filter_texts_by_week(texts, requested_week)
    snippets = _extract_text_snippets(filtered_texts)
    week_hints = _extract_week_hints(texts)
    group_hints = _extract_group_hints(texts)

    discovered_courses = sorted(
        {
            course
            for text in filtered_texts
            for course in [_extract_course_code(text)]
            if course and (not requested_courses or course in requested_courses)
        }
    )
    notes: list[str] = []
    if image_urls:
        notes.append("Image URLs are included for external multimodal analysis.")
    if not image_urls:
        notes.append("No image URLs were found in this source payload.")
    if not snippets:
        notes.append("No substantial text snippets were extracted from this source payload.")
    if requested_week is not None:
        notes.append(f"Text snippets were filtered for Week {requested_week} when explicit week markers were available.")

    return SourceArtifact(
        source=source,
        command=command,
        course_codes=discovered_courses,
        week_hints=week_hints,
        group_hints=group_hints,
        artifact_kind=_artifact_kind(has_images=bool(image_urls), has_html=has_html, has_text=bool(snippets)),
        image_urls=image_urls,
        text_snippets=snippets,
        notes=notes,
    )
