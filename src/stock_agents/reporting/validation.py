"""Output validation for AI analysis."""

from __future__ import annotations

import re
from datetime import datetime

REQUIRED_SECTIONS_SHORT_TERM = [
    "## boi canh thi truong chung khoan viet nam",
    "## danh gia tung ma",
    "## ket luan giai ngan thoi diem hien tai",
]

REQUIRED_SECTIONS_PORTFOLIO = [
    "## tom tat danh muc",
    "## khuyen nghi tung ma",
    "## ket luan",
]

URL_PATTERN = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def validate_analysis_output(
    analysis: str,
    as_of_date: datetime | None = None,
    mode: str = "short_term",
) -> dict:
    """Validate markdown analysis from OpenAI."""
    text = analysis or ""
    lowered = text.lower()
    errors: list[str] = []
    warnings: list[str] = []

    required = (
        REQUIRED_SECTIONS_SHORT_TERM
        if mode == "short_term"
        else REQUIRED_SECTIONS_PORTFOLIO
    )
    missing = [s for s in required if s not in lowered]
    if missing:
        errors.append("Thieu section bat buoc: " + ", ".join(missing))

    links = URL_PATTERN.findall(text)
    if not links:
        errors.append("Khong tim thay link nguon (http/https) trong output AI.")

    source_lines = [line.strip() for line in text.splitlines() if "http" in line.lower()]
    if source_lines and sum(
        "nguon tham khao" in line.lower() for line in text.splitlines()
    ) < 1:
        warnings.append("Co link nguon nhung thieu muc 'Nguon tham khao'.")

    if source_lines and as_of_date is not None:
        for line in source_lines:
            for date_text in DATE_PATTERN.findall(line):
                try:
                    cited = datetime.strptime(date_text, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if cited > as_of_date.date():
                    errors.append(
                        f"Nguon co ngay sau as_of ({date_text}): {line[:100]}"
                    )

    return {
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def build_validation_note(validation: dict, strict: bool = True) -> str:
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])
    if not errors and not warnings:
        return ""

    lines = ["## Canh bao xac thuc output AI", ""]
    if errors:
        lines.append("- Trang thai: KHONG DAT tieu chi xac thuc.")
        if strict:
            lines.append(
                "- Che do strict BAT: khong nen dung bao cao nay de ra quyet dinh."
            )
    else:
        lines.append("- Trang thai: DAT mot phan, can doc ky canh bao.")
    if warnings:
        lines.append("- Canh bao:")
        for w in warnings:
            lines.append(f"  - {w}")
    if errors:
        lines.append("- Loi:")
        for e in errors:
            lines.append(f"  - {e}")
    lines.append("")
    return "\n".join(lines)
