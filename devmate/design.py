"""Document & report quality linter, typography token system, and table validator.
Provides automated verification and repair for markdown, HTML, and structured documents
to eliminate blank rows, malformed table columns, unreadable palettes, and placeholder leaks.
"""

import math
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# ============================================================================
# 1. DESIGN TOKENS & COLOR PALETTES
# ============================================================================

def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    """Convert a 3-char or 6-char hex string (with or without #) to an (R, G, B) tuple."""
    clean = hex_code.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join([c * 2 for c in clean])
    if len(clean) != 6:
        raise ValueError(f"Invalid hex color code: '{hex_code}'")
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB integers (0-255) to uppercase 6-char hex string with #."""
    return f"#{min(255, max(0, r)):02X}{min(255, max(0, g)):02X}{min(255, max(0, b)):02X}"


def relative_luminance(hex_code: str) -> float:
    """
    Calculate the relative luminance of a hex color per W3C WCAG 2.1 specs.
    Returns float in range [0.0 (pure black), 1.0 (pure white)].
    """
    r, g, b = hex_to_rgb(hex_code)
    vals = []
    for c in (r, g, b):
        s = c / 255.0
        vals.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast_ratio(foreground_hex: str, background_hex: str) -> float:
    """
    Compute WCAG contrast ratio between two hex colors.
    Returns a float from 1.0 to 21.0.
    Formula: (L1 + 0.05) / (L2 + 0.05) where L1 is the lighter luminance.
    """
    l1 = relative_luminance(foreground_hex)
    l2 = relative_luminance(background_hex)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


@dataclass
class ColorToken:
    name: str
    hex: str
    role: str = ""

    @property
    def rgb(self) -> Tuple[int, int, int]:
        return hex_to_rgb(self.hex)

    def contrast_with(self, other_hex: str) -> float:
        return contrast_ratio(self.hex, other_hex)

    def is_wcag_aa(self, bg_hex: str, large_text: bool = False) -> bool:
        """Check if color combination passes WCAG AA (4.5:1 for normal text, 3:1 for large text)."""
        ratio = self.contrast_with(bg_hex)
        return ratio >= (3.0 if large_text else 4.5)

    def is_wcag_aaa(self, bg_hex: str, large_text: bool = False) -> bool:
        """Check if color combination passes WCAG AAA (7.0:1 for normal text, 4.5:1 for large text)."""
        ratio = self.contrast_with(bg_hex)
        return ratio >= (4.5 if large_text else 7.0)


@dataclass
class ColorPalette:
    name: str
    primary: ColorToken
    secondary: ColorToken
    accent: ColorToken
    background: ColorToken
    surface: ColorToken
    text_primary: ColorToken
    text_secondary: ColorToken
    border: ColorToken
    success: ColorToken
    warning: ColorToken
    error: ColorToken

    def validate_contrast(self) -> List[str]:
        """Validate all text-to-background combinations against WCAG AA standards."""
        issues = []
        # Main text on background
        ratio1 = self.text_primary.contrast_with(self.background.hex)
        if ratio1 < 4.5:
            issues.append(f"Low contrast: text_primary ({self.text_primary.hex}) on background ({self.background.hex}) = {ratio1}:1 (requires >= 4.5:1)")

        # Secondary text on background
        ratio2 = self.text_secondary.contrast_with(self.background.hex)
        if ratio2 < 3.0:
            issues.append(f"Low contrast: text_secondary ({self.text_secondary.hex}) on background ({self.background.hex}) = {ratio2}:1 (requires >= 3.0:1)")

        # Primary header contrast
        ratio3 = self.primary.contrast_with(self.background.hex)
        if ratio3 < 3.0:
            issues.append(f"Low contrast: primary ({self.primary.hex}) on background ({self.background.hex}) = {ratio3}:1 (requires >= 3.0:1)")

        return issues


# Institutional & Industry Themes
THEME_ACADEMIC_NAVY = ColorPalette(
    name="Academic Navy",
    primary=ColorToken("Primary", "#0B192C", "Institutional headers & emphasis"),
    secondary=ColorToken("Secondary", "#1E3E62", "Subheadings & accents"),
    accent=ColorToken("Accent", "#00879E", "Interactive callouts & pills"),
    background=ColorToken("Background", "#FFFFFF", "Document page canvas"),
    surface=ColorToken("Surface", "#F8FAFC", "Table alternating rows & callout boxes"),
    text_primary=ColorToken("Text Primary", "#111827", "Standard reading copy"),
    text_secondary=ColorToken("Text Secondary", "#4B5563", "Captions and secondary metadata"),
    border=ColorToken("Border", "#CBD5E1", "Table and rule dividers"),
    success=ColorToken("Success", "#059669", "Affirmative verification badges"),
    warning=ColorToken("Warning", "#D97706", "Pending review flags"),
    error=ColorToken("Error", "#DC2626", "Critical issue highlights"),
)

THEME_EMERALD_TECH = ColorPalette(
    name="Emerald Tech",
    primary=ColorToken("Primary", "#064E3B", "Primary dark forest header"),
    secondary=ColorToken("Secondary", "#047857", "Supporting medium green"),
    accent=ColorToken("Accent", "#10B981", "Bright emerald indicator"),
    background=ColorToken("Background", "#FFFFFF", "Document page canvas"),
    surface=ColorToken("Surface", "#F0FDF4", "Light green tint card background"),
    text_primary=ColorToken("Text Primary", "#0F172A", "Dark charcoal body text"),
    text_secondary=ColorToken("Text Secondary", "#475569", "Medium slate metadata"),
    border=ColorToken("Border", "#A7F3D0", "Table borders and dividers"),
    success=ColorToken("Success", "#10B981", "Passing checks"),
    warning=ColorToken("Warning", "#F59E0B", "Warning alerts"),
    error=ColorToken("Error", "#EF4444", "Error indicators"),
)

THEME_CRIMSON_EXECUTIVE = ColorPalette(
    name="Crimson Executive",
    primary=ColorToken("Primary", "#7F1D1D", "Rich burgundy titles"),
    secondary=ColorToken("Secondary", "#991B1B", "Section headers"),
    accent=ColorToken("Accent", "#DC2626", "Key KPI callouts"),
    background=ColorToken("Background", "#FFFFFF", "Canvas"),
    surface=ColorToken("Surface", "#FEF2F2", "Warm highlight background"),
    text_primary=ColorToken("Text Primary", "#1C1917", "Deep warm dark text"),
    text_secondary=ColorToken("Text Secondary", "#57534E", "Muted metadata text"),
    border=ColorToken("Border", "#FECACA", "Borders and rules"),
    success=ColorToken("Success", "#15803D", "Verification pass"),
    warning=ColorToken("Warning", "#B45309", "Warning items"),
    error=ColorToken("Error", "#B91C1C", "Critical errors"),
)

THEME_SLATE_MINIMAL = ColorPalette(
    name="Slate Minimal",
    primary=ColorToken("Primary", "#0F172A", "Deep slate headings"),
    secondary=ColorToken("Secondary", "#334155", "Subtitles and key terms"),
    accent=ColorToken("Accent", "#64748B", "Refined accents"),
    background=ColorToken("Background", "#FFFFFF", "Clean white canvas"),
    surface=ColorToken("Surface", "#F1F5F9", "Subtle gray card surfaces"),
    text_primary=ColorToken("Text Primary", "#0F172A", "Near-black text"),
    text_secondary=ColorToken("Text Secondary", "#64748B", "Muted text"),
    border=ColorToken("Border", "#E2E8F0", "Dividers"),
    success=ColorToken("Success", "#16A34A", "Passed"),
    warning=ColorToken("Warning", "#D97706", "Review"),
    error=ColorToken("Error", "#DC2626", "Failed"),
)

BUILTIN_THEMES = {
    "academic": THEME_ACADEMIC_NAVY,
    "navy": THEME_ACADEMIC_NAVY,
    "emerald": THEME_EMERALD_TECH,
    "tech": THEME_EMERALD_TECH,
    "crimson": THEME_CRIMSON_EXECUTIVE,
    "executive": THEME_CRIMSON_EXECUTIVE,
    "slate": THEME_SLATE_MINIMAL,
    "minimal": THEME_SLATE_MINIMAL,
}


def get_theme(name: str = "academic") -> ColorPalette:
    """Retrieve a pre-configured theme by name or return default Academic Navy."""
    return BUILTIN_THEMES.get((name or "").strip().lower(), THEME_ACADEMIC_NAVY)


# Typography System
@dataclass
class TypographyScale:
    title: float = 24.0
    subtitle: float = 16.0
    h1: float = 14.0
    h2: float = 12.0
    h3: float = 11.0
    body: float = 10.5
    small: float = 9.5
    caption: float = 8.5
    line_height: float = 1.35
    font_academic: str = "Times New Roman"
    font_technical: str = "Segoe UI, Arial, sans-serif"
    font_code: str = "Consolas, 'Courier New', monospace"


# ============================================================================
# 2. TABLE LINTER & REPAIR ENGINE
# ============================================================================

class IssueSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class LintIssue:
    severity: IssueSeverity
    category: str
    message: str
    line: int = 0
    snippet: str = ""
    suggestion: str = ""


@dataclass
class TableLintResult:
    is_valid: bool
    issues: List[LintIssue] = field(default_factory=list)
    repaired_table: Optional[str] = None
    row_count: int = 0
    column_count: int = 0


class TableLinter:
    """
    Parses, validates, and auto-repairs Markdown and HTML tables.
    Eliminates blank rows, broken delimiters, mismatched column counts, and orphaned cells.
    """

    @staticmethod
    def parse_markdown_table(table_text: str) -> List[List[str]]:
        """Parse raw markdown table into a 2D list of stripped cell contents."""
        lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
        rows = []
        for line in lines:
            if not line.startswith("|"):
                continue
            # Strip outer pipes and split by pipe
            content = line
            if content.startswith("|"):
                content = content[1:]
            if content.endswith("|"):
                content = content[:-1]
            cells = [c.strip() for c in content.split("|")]
            rows.append(cells)
        return rows

    @classmethod
    def lint_markdown_table(cls, table_text: str, start_line: int = 1) -> TableLintResult:
        """
        Validate a single markdown table block.
        Checks for:
        - Mismatched column count between header and rows
        - Missing or broken separator delimiter line (|---|---|)
        - Empty rows (where all cells are blank)
        - Empty cells within data rows
        """
        raw_lines = table_text.strip().splitlines()
        issues: List[LintIssue] = []

        if len(raw_lines) < 2:
            issues.append(
                LintIssue(
                    severity=IssueSeverity.CRITICAL,
                    category="Table Structure",
                    message="Markdown table has fewer than 2 rows; cannot form a valid header and body.",
                    line=start_line,
                    snippet=table_text[:100],
                    suggestion="Add at least a header row and a delimiter row '|---|---|'."
                )
            )
            return TableLintResult(is_valid=False, issues=issues)

        # Inspect Header Row
        header_line = raw_lines[0].strip()
        if not (header_line.startswith("|") and header_line.endswith("|")):
            issues.append(
                LintIssue(
                    severity=IssueSeverity.WARNING,
                    category="Table Format",
                    message="Table header row should start and end with '|' pipes.",
                    line=start_line,
                    snippet=header_line,
                    suggestion="Ensure header is framed with pipes: | Col 1 | Col 2 |"
                )
            )

        header_cells = [c.strip() for c in header_line.strip("|").split("|")]
        col_count = len(header_cells)

        if col_count == 0 or all(not c for c in header_cells):
            issues.append(
                LintIssue(
                    severity=IssueSeverity.CRITICAL,
                    category="Table Header",
                    message="Table header contains no labeled columns.",
                    line=start_line,
                    snippet=header_line,
                    suggestion="Provide descriptive column names in the first row."
                )
            )

        # Inspect Delimiter Row
        delimiter_idx = -1
        delimiter_cells = []
        for idx in range(1, min(3, len(raw_lines))):
            line = raw_lines[idx].strip()
            # Delimiter pattern: e.g. |---|:---|---:|
            cleaned = re.sub(r"[\s\|\:\-]", "", line)
            if cleaned == "" and "-" in line:
                delimiter_idx = idx
                delimiter_cells = [c.strip() for c in line.strip("|").split("|")]
                break

        if delimiter_idx == -1:
            issues.append(
                LintIssue(
                    severity=IssueSeverity.CRITICAL,
                    category="Table Delimiter",
                    message="Missing standard Markdown table delimiter row (|---|---|).",
                    line=start_line + 1,
                    snippet=raw_lines[1] if len(raw_lines) > 1 else "",
                    suggestion="Add a separator row like '| ' + ' | '.join(['---'] * col_count) + ' |'."
                )
            )
        elif len(delimiter_cells) != col_count:
            issues.append(
                LintIssue(
                    severity=IssueSeverity.CRITICAL,
                    category="Column Mismatch",
                    message=f"Delimiter row defines {len(delimiter_cells)} columns, but header defines {col_count}.",
                    line=start_line + delimiter_idx,
                    snippet=raw_lines[delimiter_idx],
                    suggestion=f"Align delimiter columns to match the {col_count} header columns."
                )
            )

        # Inspect Data Rows
        body_start = (delimiter_idx + 1) if delimiter_idx != -1 else 1
        valid_data_rows = 0

        for offset, line in enumerate(raw_lines[body_start:], start=body_start):
            cur_line_no = start_line + offset
            stripped = line.strip()

            if not stripped:
                issues.append(
                    LintIssue(
                        severity=IssueSeverity.WARNING,
                        category="Blank Row",
                        message="Encountered empty blank row inside table block.",
                        line=cur_line_no,
                        snippet="(empty line)",
                        suggestion="Remove extraneous blank lines within table body."
                    )
                )
                continue

            cells = [c.strip() for c in stripped.strip("|").split("|")]

            # Check if all cells in the row are empty
            if all(c == "" for c in cells):
                issues.append(
                    LintIssue(
                        severity=IssueSeverity.WARNING,
                        category="Blank Row",
                        message="Table row exists but all cells are completely blank.",
                        line=cur_line_no,
                        snippet=stripped,
                        suggestion="Populate cell data or delete this empty row."
                    )
                )
                continue

            # Check column count
            if len(cells) != col_count:
                issues.append(
                    LintIssue(
                        severity=IssueSeverity.CRITICAL,
                        category="Column Mismatch",
                        message=f"Row has {len(cells)} cells, expected {col_count} (mismatched structure).",
                        line=cur_line_no,
                        snippet=stripped,
                        suggestion=f"Ensure this row has exactly {col_count} pipe-delimited values."
                    )
                )

            # Check individual empty cells
            empty_cell_indices = [i + 1 for i, c in enumerate(cells) if c == ""]
            if empty_cell_indices and len(empty_cell_indices) < len(cells):
                issues.append(
                    LintIssue(
                        severity=IssueSeverity.INFO,
                        category="Empty Cell",
                        message=f"Row has empty cell(s) at column(s) {empty_cell_indices}.",
                        line=cur_line_no,
                        snippet=stripped,
                        suggestion="Fill with data, a dash '-', or explicit placeholder."
                    )
                )

            valid_data_rows += 1

        is_valid = not any(iss.severity == IssueSeverity.CRITICAL for iss in issues)
        return TableLintResult(
            is_valid=is_valid,
            issues=issues,
            row_count=valid_data_rows + 1,
            column_count=col_count
        )

    @classmethod
    def auto_repair_markdown_table(cls, table_text: str, fill_empty_with: str = "-") -> str:
        """
        Repairs a malformed Markdown table:
        - Drops completely empty lines and all-blank rows
        - Normalizes column counts to match the header row
        - Auto-generates proper delimiter row if missing or broken
        - Pads cells neatly so columns line up with consistent spacing
        """
        raw_lines = [l.strip() for l in table_text.strip().splitlines() if l.strip()]
        if not raw_lines:
            return ""

        # Extract rows
        rows: List[List[str]] = []
        for line in raw_lines:
            # Check if it's a delimiter line
            cleaned = re.sub(r"[\s\|\:\-]", "", line)
            if cleaned == "" and "-" in line and len(rows) > 0:
                # Delimiter line - skip for now, we will regenerate it
                continue

            cells = [c.strip() for c in line.strip("|").split("|")]
            # Filter out all-empty rows
            if all(not c for c in cells):
                continue
            rows.append(cells)

        if not rows:
            return table_text

        # Target column count is dictated by header row
        header = rows[0]
        col_count = max(len(header), 1)

        # Normalize rows
        normalized_rows: List[List[str]] = []
        for idx, row in enumerate(rows):
            new_row = list(row)
            # If row is shorter than header, pad it
            if len(new_row) < col_count:
                new_row.extend([fill_empty_with] * (col_count - len(new_row)))
            # If row is longer, truncate excess trailing empty cells or join
            elif len(new_row) > col_count:
                new_row = new_row[:col_count]

            # In body rows, replace empty cells with fallback
            if idx > 0:
                new_row = [c if c != "" else fill_empty_with for c in new_row]

            normalized_rows.append(new_row)

        # Calculate max column widths for pretty alignment
        col_widths = [3] * col_count
        for row in normalized_rows:
            for c_idx, cell in enumerate(row):
                col_widths[c_idx] = max(col_widths[c_idx], len(cell))

        # Format output
        output_lines = []

        # 1. Header
        header_cells = [cell.ljust(col_widths[i]) for i, cell in enumerate(normalized_rows[0])]
        output_lines.append(f"| {' | '.join(header_cells)} |")

        # 2. Delimiter
        delimiters = ["-" * max(3, col_widths[i]) for i in range(col_count)]
        output_lines.append(f"| {' | '.join(delimiters)} |")

        # 3. Body Rows
        for row in normalized_rows[1:]:
            body_cells = [cell.ljust(col_widths[i]) for i, cell in enumerate(row)]
            output_lines.append(f"| {' | '.join(body_cells)} |")

        return "\n".join(output_lines)

    @classmethod
    def lint_html_tables(cls, html_content: str) -> List[LintIssue]:
        """
        Scan HTML content for <table> elements and evaluate their structural integrity.
        Flags:
        - Mismatched <td> counts compared to <th> headers
        - Missing <thead> or <th> elements
        - Completely empty <td></td> cells
        - Unclosed <table> tags
        """
        issues: List[LintIssue] = []

        # Count opening and closing table tags
        open_tables = len(re.findall(r"<table\b", html_content, re.IGNORECASE))
        close_tables = len(re.findall(r"</table>", html_content, re.IGNORECASE))

        if open_tables != close_tables:
            issues.append(
                LintIssue(
                    severity=IssueSeverity.CRITICAL,
                    category="HTML Structure",
                    message=f"Mismatched table tags: {open_tables} opening <table...> but {close_tables} closing </table> tags.",
                    suggestion="Verify all <table> blocks are closed properly."
                )
            )

        # Extract table blocks
        table_matches = re.finditer(r"<table\b[^>]*>(.*?)</table>", html_content, re.IGNORECASE | re.DOTALL)
        for t_idx, match in enumerate(table_matches, start=1):
            block = match.group(1)

            # Check header
            th_cells = re.findall(r"<th\b[^>]*>(.*?)</th>", block, re.IGNORECASE | re.DOTALL)
            tr_rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", block, re.IGNORECASE | re.DOTALL)

            if not th_cells:
                issues.append(
                    LintIssue(
                        severity=IssueSeverity.WARNING,
                        category="HTML Table",
                        message=f"Table #{t_idx} has no <th> header cells defined.",
                        suggestion="Add header cells using <th> for accessibility and clarity."
                    )
                )

            expected_cols = len(th_cells)
            for r_idx, tr in enumerate(tr_rows, start=1):
                td_cells = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.IGNORECASE | re.DOTALL)
                if not td_cells:
                    # Might be header row with <th> only
                    continue

                if expected_cols > 0 and len(td_cells) != expected_cols:
                    issues.append(
                        LintIssue(
                            severity=IssueSeverity.CRITICAL,
                            category="HTML Column Mismatch",
                            message=f"Table #{t_idx}, Row #{r_idx} has {len(td_cells)} <td> cells, expected {expected_cols}.",
                            snippet=tr.strip()[:100],
                            suggestion=f"Adjust <td> count to match header column count ({expected_cols})."
                        )
                    )

                # Check for empty cells
                for c_idx, cell in enumerate(td_cells, start=1):
                    clean_cell = cell.strip()
                    if clean_cell == "" or clean_cell == "<br>" or clean_cell == "<p></p>":
                        issues.append(
                            LintIssue(
                                severity=IssueSeverity.INFO,
                                category="HTML Empty Cell",
                                message=f"Table #{t_idx}, Row #{r_idx}, Col #{c_idx} is empty.",
                                suggestion="Fill with &nbsp; or content to prevent visual collapse."
                            )
                        )

        return issues


# ============================================================================
# 3. DOCUMENT LINTER & SCORE ENGINE
# ============================================================================

PLACEHOLDER_PATTERNS = [
    (r"\[TODO\b[^\]]*\]", "Unresolved [TODO] marker"),
    (r"\[TBD\b[^\]]*\]", "Unresolved [TBD] marker"),
    (r"\[INSERT\b[^\]]*\]", "Unresolved [INSERT] marker"),
    (r"\[PLACEHOLDER\b[^\]]*\]", "Unresolved [PLACEHOLDER] marker"),
    (r"\bLorem\s+ipsum\b", "Latin 'Lorem ipsum' filler text"),
    (r"\bFIXME\b", "Unresolved FIXME marker"),
    (r"\bXXX\b", "Suspicious placeholder token 'XXX'"),
]


@dataclass
class LintReport:
    file_path: str
    is_valid: bool
    score: int  # 0 to 100
    critical_count: int
    warning_count: int
    info_count: int
    issues: List[LintIssue]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "is_valid": self.is_valid,
            "score": self.score,
            "summary": self.summary,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "issues": [
                {
                    "severity": iss.severity.value,
                    "category": iss.category,
                    "message": iss.message,
                    "line": iss.line,
                    "snippet": iss.snippet,
                    "suggestion": iss.suggestion,
                }
                for iss in self.issues
            ],
        }


class DocumentLinter:
    """
    Evaluates Markdown, HTML, and plain text documents for formatting,
    typography hierarchy, table integrity, and placeholder leakages.
    """

    def __init__(self, theme: ColorPalette = THEME_ACADEMIC_NAVY):
        self.theme = theme

    def lint_text(self, content: str, file_path: str = "<memory>") -> LintReport:
        """Analyze full document content and compile a scored quality report."""
        issues: List[LintIssue] = []
        lines = content.splitlines()

        # 1. Scan for Unresolved Placeholders and Hallucination Indicators
        for idx, line in enumerate(lines, start=1):
            for pat, desc in PLACEHOLDER_PATTERNS:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    issues.append(
                        LintIssue(
                            severity=IssueSeverity.WARNING,
                            category="Placeholder Leak",
                            message=f"{desc} detected.",
                            line=idx,
                            snippet=line.strip()[:100],
                            suggestion="Replace placeholder with validated factual content or explicit inquiry."
                        )
                    )

        # 2. Markdown Heading Hierarchy Check
        last_heading_level = 0
        for idx, line in enumerate(lines, start=1):
            m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
            if m:
                level = len(m.group(1))
                # Check for skipped heading level (e.g. H1 followed directly by H3)
                if last_heading_level > 0 and level > (last_heading_level + 1):
                    issues.append(
                        LintIssue(
                            severity=IssueSeverity.WARNING,
                            category="Typography Hierarchy",
                            message=f"Heading level skipped: jumped from H{last_heading_level} directly to H{level}.",
                            line=idx,
                            snippet=line.strip(),
                            suggestion=f"Use H{last_heading_level + 1} to preserve logical typographic hierarchy."
                        )
                    )
                last_heading_level = level

        # 3. Markdown Table Inspection
        table_blocks: List[Tuple[int, List[str]]] = []
        current_table: List[str] = []
        current_table_start = 0

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                if not current_table:
                    current_table_start = idx
                current_table.append(stripped)
            else:
                if current_table:
                    table_blocks.append((current_table_start, current_table))
                    current_table = []

        if current_table:
            table_blocks.append((current_table_start, current_table))

        for start_line, tbl_lines in table_blocks:
            tbl_text = "\n".join(tbl_lines)
            res = TableLinter.lint_markdown_table(tbl_text, start_line=start_line)
            issues.extend(res.issues)

        # 4. HTML Table & Structural Inspection
        if "<table" in content.lower():
            html_issues = TableLinter.lint_html_tables(content)
            issues.extend(html_issues)

        # 5. Empty Links & Broken Media Checks
        for idx, line in enumerate(lines, start=1):
            if re.search(r"\[[^\]]+\]\(\s*\)", line):
                issues.append(
                    LintIssue(
                        severity=IssueSeverity.WARNING,
                        category="Broken Link",
                        message="Empty link destination target: '[text]()'.",
                        line=idx,
                        snippet=line.strip()[:100],
                        suggestion="Provide a valid URL or file path destination."
                    )
                )
            if re.search(r"!\[[^\]]*\]\(\s*\)", line):
                issues.append(
                    LintIssue(
                        severity=IssueSeverity.WARNING,
                        category="Broken Media",
                        message="Empty image src destination target: '![]( )'.",
                        line=idx,
                        snippet=line.strip()[:100],
                        suggestion="Provide the path to the image or remove the tag."
                    )
                )

        # Calculate Quality Score
        crit_count = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)
        warn_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
        info_count = sum(1 for i in issues if i.severity == IssueSeverity.INFO)

        # Deductions: Critical -20 each, Warning -5 each, Info -1 each
        deductions = (crit_count * 20) + (warn_count * 5) + (info_count * 1)
        score = max(0, min(100, 100 - deductions))

        is_valid = crit_count == 0

        if score >= 90:
            summary = "Excellent document design & structural fidelity."
        elif score >= 75:
            summary = "Good quality with minor formatting or placeholder notices."
        elif score >= 50:
            summary = "Sub-optimal quality: table column mismatches or warnings detected."
        else:
            summary = "Failed quality validation: critical structural flaws or severe table errors."

        return LintReport(
            file_path=file_path,
            is_valid=is_valid,
            score=score,
            critical_count=crit_count,
            warning_count=warn_count,
            info_count=info_count,
            issues=issues,
            summary=summary,
        )

    def lint_file(self, file_path: Union[str, Path]) -> LintReport:
        """Read and validate an on-disk file."""
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Target document not found: {file_path}")

        text = p.read_text(encoding="utf-8", errors="replace")
        return self.lint_text(text, file_path=str(p))

    def auto_fix_content(self, content: str) -> str:
        """
        Automatically repair formatting flaws in content:
        - Auto-formats and aligns all markdown tables
        - Eliminates phantom blank lines inside tables
        - Normalizes trailing whitespace
        """
        lines = content.splitlines()
        reconstructed_lines: List[str] = []
        current_table: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                current_table.append(stripped)
            else:
                if current_table:
                    # Repair table
                    repaired = TableLinter.auto_repair_markdown_table("\n".join(current_table))
                    reconstructed_lines.extend(repaired.splitlines())
                    current_table = []
                reconstructed_lines.append(line.rstrip())

        if current_table:
            repaired = TableLinter.auto_repair_markdown_table("\n".join(current_table))
            reconstructed_lines.extend(repaired.splitlines())

        return "\n".join(reconstructed_lines) + "\n"


# Convenience module-level instances
default_linter = DocumentLinter()


def lint_document(path_or_content: str, is_file: bool = True) -> LintReport:
    """Quick helper to lint a document from path or raw string."""
    if is_file:
        return default_linter.lint_file(path_or_content)
    return default_linter.lint_text(path_or_content)
