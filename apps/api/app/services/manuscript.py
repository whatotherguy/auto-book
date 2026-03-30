from __future__ import annotations

import re
from pathlib import Path

import fitz


def clean_line_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_drop_cap_spacing(text: str, font_size: float) -> str:
    if font_size >= 24:
        return re.sub(r"^([A-Z])\s+([a-z])", r"\1\2", text)
    return text


def merge_drop_cap_lines(lines: list[dict]) -> list[dict]:
    merged: list[dict] = []
    index = 0

    while index < len(lines):
        current = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else None

        if (
            next_line
            and len(current["text"]) == 1
            and current["text"].isalpha()
            and next_line["text"]
            and next_line["text"][0].islower()
            and current["font_size"] > next_line["font_size"] * 1.35
            and abs(current["bbox"][1] - next_line["bbox"][1]) < max(current["font_size"], next_line["font_size"]) * 1.8
        ):
            merged.append(
                {
                    **next_line,
                    "text": f"{current['text']}{next_line['text']}",
                    "font_size": max(current["font_size"], next_line["font_size"]),
                    "bbox": (
                        min(current["bbox"][0], next_line["bbox"][0]),
                        min(current["bbox"][1], next_line["bbox"][1]),
                        max(current["bbox"][2], next_line["bbox"][2]),
                        max(current["bbox"][3], next_line["bbox"][3]),
                    ),
                }
            )
            index += 2
            continue

        merged.append(current)
        index += 1

    return merged


def build_page_lines(page: fitz.Page) -> list[dict]:
    page_dict = page.get_text("dict")
    lines: list[dict] = []

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = clean_line_text("".join(span.get("text", "") for span in spans))
            if not text:
                continue

            font_size = max((float(span.get("size", 0.0)) for span in spans), default=0.0)
            text = normalize_drop_cap_spacing(text, font_size)
            bbox = tuple(line.get("bbox", block.get("bbox", (0.0, 0.0, 0.0, 0.0))))
            lines.append(
                {
                    "text": text,
                    "font_size": font_size,
                    "bbox": bbox,
                }
            )

    lines.sort(key=lambda item: (round(item["bbox"][1], 1), item["bbox"][0]))
    return merge_drop_cap_lines(lines)


def join_page_lines(lines: list[dict]) -> str:
    if not lines:
        return ""

    text_parts: list[str] = []
    previous: dict | None = None

    for line in lines:
        text = line["text"]
        if previous is None:
            text_parts.append(text)
            previous = line
            continue

        vertical_gap = float(line["bbox"][1]) - float(previous["bbox"][3])
        is_heading = line["font_size"] > previous["font_size"] * 1.25 or previous["font_size"] > line["font_size"] * 1.25

        if previous["text"].endswith("-"):
            text_parts[-1] = text_parts[-1][:-1] + text
        elif (
            len(previous["text"]) == 1
            and previous["text"].isalpha()
            and text
            and text[0].islower()
            and previous["font_size"] > line["font_size"] * 1.35
        ):
            text_parts.append(text)
        elif vertical_gap > max(line["font_size"], previous["font_size"]) * 0.9 or is_heading:
            text_parts.append("\n\n" + text)
        else:
            text_parts.append(" " + text)

        previous = line

    return "".join(text_parts).strip()


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> tuple[str, int]:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_texts: list[str] = []

    for page in document:
        page_text = join_page_lines(build_page_lines(page))
        if page_text:
            page_texts.append(page_text)

    return "\n\n".join(page_texts).strip(), len(document)


def extract_text_from_manuscript_file(filename: str, file_bytes: bytes) -> tuple[str, dict]:
    suffix = Path(filename).suffix.lower()

    if suffix == ".txt":
        text = file_bytes.decode("utf-8-sig", errors="ignore").strip()
        return text, {"type": "txt", "pages": 1}

    if suffix == ".pdf":
        text, page_count = extract_text_from_pdf_bytes(file_bytes)
        return text, {"type": "pdf", "pages": page_count}

    raise ValueError("Unsupported manuscript file type")
