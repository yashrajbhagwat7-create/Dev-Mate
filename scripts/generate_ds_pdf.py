#!/usr/bin/env python3
"""Generate a PDF of data structures guide from markdown with proper formatting."""

import os
from pathlib import Path
from fpdf import FPDF
import markdown

# --- Read markdown source ---
md_path = Path(__file__).resolve().parent.parent / "docs" / "data_structures_guide.md"
with open(md_path, "r", encoding="utf-8") as f:
    md_text = f.read()

# --- Convert markdown to HTML for structure parsing ---
html_content = markdown.markdown(md_path_content=md_text)

# --- Build a simple PDF directly from markdown sections ---
class DataStructurePDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 5, "DevMate Data Structures Guide", 0, 0, "R")
            self.ln(1)
            self.set_draw_color(200, 200, 200)
            self.line(self.get_x(), self.get_y(), self.get_x() + 190, self.get_y())
            self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")

    def chapter_title(self, title):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(30, 58, 138)  # Deep blue
        self.multi_cell(0, 10, title)
        self.ln(1)

    def section_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(30, 58, 138)
        self.multi_cell(0, 7, title)
        self.ln(0.5)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(5, 150, 105)  # Emerald green
        self.multi_cell(0, 5, title)
        self.ln(0.5)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 5, text)
        self.ln(0.5)

    def code_block(self, code):
        self.set_font("Courier", "", 8)
        self.set_text_color(40, 40, 40)
        # Split into lines
        lines = code.split("\n")
        for line in lines:
            if line.strip():
                self.multi_cell(0, 4, line, border=0)
        self.set_text_color(0, 0, 0)
        self.ln(1)


# --- Simple markdown-to-PDF parser ---
def parse_md_to_pdf(md_text, pdf):
    lines = md_text.split("\n")
    
    in_code = False
    code_lines = []
    table_rows = []
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        
        # Page break
        if stripped == "---":
            if code_lines and in_code:
                pdf.code_block("\n".join(code_lines))
                code_lines = []
            in_code = False
            pdf.add_page()
            continue
        
        # Code block start/end
        if stripped.startswith("```"):
            if in_code:
                pdf.code_block("\n".join(code_lines))
                code_lines = []
            in_code = not in_code
            continue
        
        if in_code:
            code_lines.append(line)
            continue
        
        # Table handling
        if "|" in stripped and not stripped.startswith("|---"):
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(stripped)
            continue
        elif in_table and stripped == "":
            # End table
            pdf.set_font("Courier", "", 8)
            for row in table_rows:
                cells = [c.strip() for c in row.split("|")]
                display = " | ".join(cells)
                pdf.multi_cell(0, 4, display)
            pdf.ln(1)
            in_table = False
            table_rows = []
            continue
        
        # Headings
        if stripped.startswith("### "):
            if code_lines:
                pdf.code_block("\n".join(code_lines))
                code_lines = []
            pdf.sub_title(stripped[4:])
        elif stripped.startswith("## "):
            pdf.section_title(stripped[3:])
        elif stripped.startswith("# "):
            pdf.chapter_title(stripped[2:])
        
        # Bullet points
        elif stripped.startswith("- "):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 5, f"  • {stripped[2:]}")
        
        # Numbered lists
        elif stripped.startswith("1. "):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 5, f"  1. {stripped[3:]}")
        
        # Regular paragraph
        elif stripped and not stripped.startswith("#"):
            pdf.body_text(stripped)
    
    # Handle any remaining content
    if code_lines and in_code:
        pdf.code_block("\n".join(code_lines))


# --- Generate PDF ---
pdf = DataStructurePDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()

parse_md_to_pdf(md_text, pdf)

output_path = "devmate/data_structures_guide.pdf"
pdf.output(output_path)

print(f"PDF generated at: {output_path}")
print(f"File size: {os.path.getsize(output_path)} bytes")
