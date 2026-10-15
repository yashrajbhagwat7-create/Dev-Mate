"""Unit and integration tests for Document & Report Quality Linter, Design Tokens, and Table Validator (Day 3)."""

import json
import pytest
from pathlib import Path

from devmate.config import Config
from devmate.tools import ToolBox
from devmate.design import (
    hex_to_rgb,
    rgb_to_hex,
    relative_luminance,
    contrast_ratio,
    ColorToken,
    ColorPalette,
    TypographyScale,
    THEME_ACADEMIC_NAVY,
    THEME_EMERALD_TECH,
    THEME_CRIMSON_EXECUTIVE,
    THEME_SLATE_MINIMAL,
    get_theme,
    IssueSeverity,
    TableLinter,
    DocumentLinter,
    lint_document,
)
from devmate.ui import render_lint_report


# ============================================================================
# 1. COLOR TOKENS & WCAG CONTRAST TESTS
# ============================================================================

def test_hex_to_rgb_valid():
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("#000000") == (0, 0, 0)
    assert hex_to_rgb("0B192C") == (11, 25, 44)
    assert hex_to_rgb("#FFF") == (255, 255, 255)
    assert hex_to_rgb("000") == (0, 0, 0)


def test_hex_to_rgb_invalid():
    with pytest.raises(ValueError):
        hex_to_rgb("invalid")
    with pytest.raises(ValueError):
        hex_to_rgb("#12345")


def test_rgb_to_hex():
    assert rgb_to_hex(255, 255, 255) == "#FFFFFF"
    assert rgb_to_hex(0, 0, 0) == "#000000"
    assert rgb_to_hex(11, 25, 44) == "#0B192C"


def test_relative_luminance():
    assert relative_luminance("#000000") == pytest.approx(0.0, abs=1e-4)
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0, abs=1e-4)


def test_contrast_ratio():
    # Black on white is maximum 21.0
    bw = contrast_ratio("#000000", "#FFFFFF")
    assert bw == 21.0

    # Same color is 1.0
    same = contrast_ratio("#123456", "#123456")
    assert same == 1.0

    # Academic navy on white should have high contrast (> 10:1)
    navy_on_white = contrast_ratio("#0B192C", "#FFFFFF")
    assert navy_on_white > 14.0


def test_color_token_wcag():
    token = ColorToken("Navy Header", "#0B192C")
    assert token.rgb == (11, 25, 44)
    assert token.is_wcag_aa("#FFFFFF") is True
    assert token.is_wcag_aaa("#FFFFFF") is True

    # Low contrast color
    light_gray = ColorToken("Light Gray", "#E2E8F0")
    assert light_gray.is_wcag_aa("#FFFFFF") is False


def test_theme_retrieval_and_contrast():
    theme = get_theme("academic")
    assert theme.name == "Academic Navy"
    assert theme.primary.hex == "#0B192C"

    # Builtin academic theme should pass contrast validation
    issues = theme.validate_contrast()
    assert len(issues) == 0

    # Emerald theme check
    emerald = get_theme("emerald")
    assert emerald.name == "Emerald Tech"
    assert emerald.primary.hex == "#064E3B"

    # Fallback to academic
    fallback = get_theme("nonexistent")
    assert fallback.name == "Academic Navy"


def test_typography_scale():
    typo = TypographyScale()
    assert typo.title == 24.0
    assert typo.body == 10.5
    assert typo.h1 > typo.h2 > typo.h3 > typo.body


# ============================================================================
# 2. TABLE LINTER & AUTO-REPAIR TESTS
# ============================================================================

def test_table_linter_valid_markdown():
    valid_table = """
| Metric | Q1 | Q2 |
|---|---|---|
| Revenue | 100 | 120 |
| Users | 500 | 650 |
"""
    result = TableLinter.lint_markdown_table(valid_table)
    assert result.is_valid is True
    assert result.column_count == 3
    assert result.row_count == 3  # 1 header + 2 body rows
    assert not any(i.severity == IssueSeverity.CRITICAL for i in result.issues)


def test_table_linter_mismatched_columns():
    bad_table = """
| Name | Age | City |
|---|---|---|
| Alice | 24 |
| Bob | 30 | Paris | Extra |
"""
    result = TableLinter.lint_markdown_table(bad_table)
    assert result.is_valid is False
    mismatches = [i for i in result.issues if i.category == "Column Mismatch"]
    assert len(mismatches) >= 2


def test_table_linter_missing_delimiter():
    no_delim_table = """
| Header 1 | Header 2 |
| Data 1 | Data 2 |
"""
    result = TableLinter.lint_markdown_table(no_delim_table)
    assert result.is_valid is False
    assert any(i.category == "Table Delimiter" for i in result.issues)


def test_table_linter_blank_rows():
    table_with_blanks = """
| Metric | Value |
|---|---|
| Alpha | 10 |
| | |
| Beta | 20 |
"""
    result = TableLinter.lint_markdown_table(table_with_blanks)
    blank_issues = [i for i in result.issues if i.category == "Blank Row"]
    assert len(blank_issues) >= 1


def test_auto_repair_markdown_table():
    messy_table = """
| Name | Role | Department |
| Alice | Engineer |
| | |
| Bob | Manager | Sales | Extra |
| Charlie | Designer | UX |
"""
    repaired = TableLinter.auto_repair_markdown_table(messy_table, fill_empty_with="N/A")
    lines = repaired.strip().splitlines()

    # Should have header, delimiter, and 3 clean body rows (blank row dropped)
    assert len(lines) == 5
    assert "---" in lines[1]
    assert "N/A" in lines[2]  # Alice was missing Department
    assert "Alice" in lines[2]
    assert "Bob" in lines[3]
    assert "Charlie" in lines[4]

    # Re-linting the repaired table should now be valid
    lint_check = TableLinter.lint_markdown_table(repaired)
    assert lint_check.is_valid is True


def test_table_linter_html_tables():
    html_with_mismatch = """
    <table>
      <tr><th>Name</th><th>Score</th></tr>
      <tr><td>Alice</td><td>95</td></tr>
      <tr><td>Bob</td><td>88</td><td>Extra</td></tr>
    </table>
    """
    issues = TableLinter.lint_html_tables(html_with_mismatch)
    assert any(i.category == "HTML Column Mismatch" for i in issues)


def test_table_linter_html_empty_cells():
    html_empty = """
    <table>
      <tr><th>A</th><th>B</th></tr>
      <tr><td>1</td><td></td></tr>
    </table>
    """
    issues = TableLinter.lint_html_tables(html_empty)
    assert any(i.category == "HTML Empty Cell" for i in issues)


# ============================================================================
# 3. DOCUMENT LINTER & SCORE ENGINE TESTS
# ============================================================================

def test_document_linter_placeholder_detection():
    doc = """
# Project Proposal
This project will launch in [TODO: Insert date].
The budget is [TBD].
Lorem ipsum dolor sit amet, consectetur adipiscing elit.
"""
    linter = DocumentLinter()
    report = linter.lint_text(doc)
    assert report.is_valid is True  # Warning, not critical
    assert report.warning_count >= 3
    assert report.score < 90
    categories = [i.category for i in report.issues]
    assert "Placeholder Leak" in categories


def test_document_linter_heading_hierarchy():
    bad_headings = """
# Chapter 1: Introduction
### Subsection 1.1 (Skipped H2!)
Content here.
"""
    linter = DocumentLinter()
    report = linter.lint_text(bad_headings)
    hierarchy_issues = [i for i in report.issues if i.category == "Typography Hierarchy"]
    assert len(hierarchy_issues) == 1
    assert "jumped from H1 directly to H3" in hierarchy_issues[0].message


def test_document_linter_broken_links():
    doc = """
Read the [documentation]() here.
![Architecture Diagram]()
"""
    linter = DocumentLinter()
    report = linter.lint_text(doc)
    assert any(i.category == "Broken Link" for i in report.issues)
    assert any(i.category == "Broken Media" for i in report.issues)


def test_document_linter_clean_document():
    clean_doc = """
# System Overview

## 1. Introduction
This document describes the software architecture.

## 2. Component Matrix
| Component | Status | Version |
|---|---|---|
| Core API | Active | 1.0.0 |
| Frontend | Active | 2.1.0 |

## 3. Conclusion
Everything is fully verified.
"""
    linter = DocumentLinter()
    report = linter.lint_text(clean_doc)
    assert report.is_valid is True
    assert report.critical_count == 0
    assert report.score >= 95
    assert "Excellent" in report.summary


def test_document_linter_auto_fix_content():
    content = """
# Report

| Col A | Col B |
| 1 |
| | |
| 2 | 3 |

End of report.
"""
    linter = DocumentLinter()
    fixed = linter.auto_fix_content(content)
    assert "| 1     | -     |" in fixed
    assert "| 2     | 3     |" in fixed

    # Verify fixed content lints cleanly
    re_lint = linter.lint_text(fixed)
    assert re_lint.critical_count == 0


# ============================================================================
# 4. TOOLBOX & UI INTEGRATION TESTS
# ============================================================================

@pytest.fixture
def test_workspace(tmp_path):
    # Setup valid document
    doc_path = tmp_path / "valid_doc.md"
    doc_path.write_text("# Title\n\n## Subtitle\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")

    # Setup messy document with broken table
    messy_path = tmp_path / "broken_doc.md"
    messy_path.write_text("# Report\n\n| X | Y |\n| 1 |\n", encoding="utf-8")

    cfg = Config(root=tmp_path)
    box = ToolBox(cfg)
    return tmp_path, box, doc_path, messy_path


def test_toolbox_lint_document_pass(test_workspace):
    tmp_path, box, doc_path, _ = test_workspace
    res_str = box.lint_document("valid_doc.md")
    data = json.loads(res_str)

    assert data["status"] == "PASS"
    assert data["score"] >= 95
    assert data["critical"] == 0

    # Verify memory log
    recent = box.memory.recent_activity(limit=1)
    assert recent[0]["action"] == "LINT"
    assert recent[0]["status"] == "PASS"


def test_toolbox_lint_document_auto_fix(test_workspace):
    tmp_path, box, _, messy_path = test_workspace
    # First lint without fix -> should detect critical error
    res_str = box.lint_document("broken_doc.md", auto_fix=False)
    data = json.loads(res_str)
    assert data["status"] == "FAIL"
    assert data["critical"] > 0

    # Second lint with auto_fix -> repairs file
    fix_str = box.lint_document("broken_doc.md", auto_fix=True)
    fix_data = json.loads(fix_str)
    assert fix_data["auto_fix"] is True

    # Backup should exist in .devmate/backups/
    backups = list((tmp_path / ".devmate" / "backups").glob("*_broken_doc.md"))
    assert len(backups) >= 1

    # Re-reading the file on disk should show balanced table
    content = messy_path.read_text(encoding="utf-8")
    assert "| X   | Y   |" in content
    assert "| 1   | -   |" in content


def test_toolbox_lint_document_security(test_workspace):
    tmp_path, box, _, _ = test_workspace

    # Traversal rejection
    with pytest.raises(ValueError):
        box.lint_document("../outside.md")

    # Secret / protected file rejection
    with pytest.raises(PermissionError):
        box.lint_document(".env")


def test_render_lint_report_ui():
    doc = "# Note\n[TODO: Fix this]\n"
    report = lint_document(doc, is_file=False)
    card = render_lint_report(report)

    assert "Document Quality Linter" in card
    assert "SCORE" in card
    assert "Placeholder Leak" in card
