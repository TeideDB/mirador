"""PDF render output node — document assembly engine with markdown template support.

Supports markdown templates with {{directives}} for layout primitives:
  # Heading, ## Heading 2, ### Heading 3
  **bold**, *italic* inline formatting
  --- horizontal divider
  | col | col | static markdown tables
  {{columns: 50, 50}}...|||...{{/columns}} multi-column layout
  {{columns: 40, 60 | bg=#4AAECC}}...|||...{{/columns}} with background
  {{box}}...{{/box}} bordered frame
  {{box | bg=#f0f0f0}}...{{/box}} frame with background
  {{metrics}}label | column | agg | format{{/metrics}} KPI cards
  {{kv}}Label | Value{{/kv}} key-value pairs
  {{chart: bar, x=col, y=col}} chart from data
  {{table: max_rows=200, totals=col1}} data table from dataframe
  {{image: path, width=200, align=center}} embedded image
  {{page_break}}, {{spacer: 20}} layout control
  {{row_count}}, {{col_count}} template variables
"""

from typing import Any
from pathlib import Path
from dataclasses import dataclass, field
import re

from mirador.nodes.base import BaseNode, NodeMeta, NodePort


# ---- Render context -----------------------------------------------------------

@dataclass
class RenderContext:
    """Carries shared state through section renderers."""
    df_data: dict[str, list]   # column_name -> list of values
    columns: list[str]
    n_rows: int
    theme: dict
    styles: Any                # ReportLab getSampleStyleSheet()
    page_width: float
    page_height: float
    rl: Any = field(default=None, repr=False)  # {"colors": ...}


# ---- Helpers ------------------------------------------------------------------

def hex_to_color(colors_mod, h: str):
    h = h.lstrip("#")
    if len(h) == 6:
        return colors_mod.Color(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)
    return colors_mod.gray


def bind_data(text: str, ctx: RenderContext) -> str:
    """Replace {{row_count}}, {{col_count}}, {{column_name}} placeholders."""
    text = text.replace("{{row_count}}", str(ctx.n_rows))
    text = text.replace("{{col_count}}", str(len(ctx.columns)))
    for col in ctx.columns:
        text = text.replace("{{" + col + "}}", col)
    return text


def md_inline(text: str) -> str:
    """Convert markdown bold/italic to ReportLab HTML tags."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    return text


def _compute_agg(col_data: list, agg: str):
    nums = []
    for v in col_data:
        try:
            nums.append(float(v))
        except (ValueError, TypeError):
            pass
    if not nums:
        return len(col_data) if agg == "count" else 0
    if agg == "sum":
        return sum(nums)
    elif agg == "avg":
        return sum(nums) / len(nums)
    elif agg == "min":
        return min(nums)
    elif agg == "max":
        return max(nums)
    elif agg == "count":
        return len(col_data)
    return 0


def _make_para_style(ctx, name, **overrides):
    """Create a ParagraphStyle from theme + overrides."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    font = overrides.pop("fontName", ctx.theme.get("font_family", "Helvetica"))
    sz = overrides.pop("fontSize", ctx.theme.get("font_size", 9))
    align_map = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}
    align = align_map.get(overrides.pop("alignment", "left"), TA_LEFT)

    return ParagraphStyle(name, fontName=font, fontSize=sz, leading=sz + 5,
                          alignment=align, **overrides)


# ---- Markdown template parser -------------------------------------------------

def _parse_directive_args(args_str: str) -> dict:
    """Parse 'key=value, key=value' or 'positional, key=value' into dict."""
    result = {"_positional": []}
    for part in args_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            # Try numeric conversion
            try:
                v = int(v)
            except ValueError:
                try:
                    v = float(v)
                except ValueError:
                    pass
            result[k] = v
        else:
            result["_positional"].append(part)
    return result


def _parse_block_options(args_str: str) -> tuple[str, dict]:
    """Parse 'main_args | opt1 opt2=val' into (main_args, options_dict)."""
    if "|" in args_str:
        main, opts_str = args_str.split("|", 1)
        opts = {}
        for token in opts_str.strip().split():
            if "=" in token:
                k, v = token.split("=", 1)
                opts[k.strip()] = v.strip()
            else:
                opts[token.strip()] = True
        return main.strip(), opts
    return args_str.strip(), {}


def _parse_md_table(lines: list[str]) -> dict:
    """Parse markdown table lines into a static_table section."""
    rows = []
    headers = None
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # Skip separator row (---|----|---)
        if all(re.match(r'^:?-+:?$', c.strip()) for c in cells if c.strip()):
            continue
        if headers is None:
            headers = cells
        else:
            rows.append(cells)
    return {"type": "static_table", "headers": headers or [], "rows": rows}


def parse_template(text: str) -> list[dict]:
    """Parse markdown template with {{directives}} into sections array."""
    sections = []
    lines = text.split("\n")
    n = len(lines)
    i = 0

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Empty line — skip
        if not stripped:
            i += 1
            continue

        # Heading: # H1, ## H2, ### H3
        m = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if m:
            level = len(m.group(1))
            text_content = md_inline(m.group(2))
            sections.append({"type": "heading", "text": text_content, "level": level})
            i += 1
            continue

        # Horizontal rule: --- or *** or ___
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            sections.append({"type": "divider", "color": "#cccccc", "thickness": 1})
            i += 1
            continue

        # Block directive: {{columns: ...}}, {{box}}, {{metrics}}, {{kv}}
        m = re.match(r'^\{\{(columns|box|metrics|kv)(?::\s*(.+?))?\s*(?:\|(.+?))?\}\}$', stripped)
        if m:
            block_type = m.group(1)
            block_args = m.group(2) or ""
            block_opts_str = m.group(3) or ""
            # Parse options after |
            opts = {}
            if block_opts_str:
                for token in block_opts_str.strip().split():
                    if "=" in token:
                        k, v = token.split("=", 1)
                        opts[k.strip()] = v.strip()
                    else:
                        opts[token.strip()] = True

            # Collect lines until {{/block_type}}
            end_tag = "{{/" + block_type + "}}"
            block_lines = []
            i += 1
            while i < n and lines[i].strip() != end_tag:
                block_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip end tag

            sec = _parse_block(block_type, block_args, opts, block_lines)
            if sec:
                sections.append(sec)
            continue

        # Inline directive: {{page_break}}, {{spacer: 20}}, {{chart: ...}}, {{table: ...}}, {{image: ...}}
        m = re.match(r'^\{\{(\w+)(?::\s*(.+?))?\}\}$', stripped)
        if m:
            directive = m.group(1)
            args = m.group(2) or ""
            sec = _parse_inline_directive(directive, args)
            if sec:
                sections.append(sec)
            i += 1
            continue

        # Markdown table: | col | col |
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_lines = []
            while i < n and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            sec = _parse_md_table(table_lines)
            if sec and (sec.get("headers") or sec.get("rows")):
                sections.append(sec)
            continue

        # Regular text paragraph — collect until empty line or structural element
        para_lines = []
        while i < n:
            l = lines[i].strip()
            if not l:
                i += 1
                break
            if (re.match(r'^#{1,3}\s', l) or
                re.match(r'^(-{3,}|\*{3,}|_{3,})$', l) or
                re.match(r'^\{\{', l) or
                (l.startswith("|") and "|" in l[1:])):
                break
            para_lines.append(lines[i])
            i += 1

        if para_lines:
            content = md_inline("\n".join(para_lines))
            sections.append({"type": "text", "content": content})

    return sections


def _parse_inline_directive(directive: str, args_str: str) -> dict | None:
    """Parse an inline {{directive: args}} into a section dict."""
    if directive == "page_break":
        return {"type": "page_break"}

    if directive == "spacer":
        try:
            h = int(args_str.strip())
        except ValueError:
            h = 20
        return {"type": "spacer", "height": h}

    if directive == "chart":
        parsed = _parse_directive_args(args_str)
        pos = parsed.get("_positional", [])
        return {
            "type": "chart",
            "chart_type": pos[0] if pos else "bar",
            "x_column": parsed.get("x", ""),
            "y_column": parsed.get("y", ""),
            "width": parsed.get("width", 500),
            "height": parsed.get("height", 300),
        }

    if directive == "table":
        parsed = _parse_directive_args(args_str)
        totals = parsed.get("totals", "")
        total_cols = [c.strip() for c in totals.split(";")] if isinstance(totals, str) and totals else []
        return {
            "type": "table",
            "columns": parsed.get("columns", ""),
            "max_rows": parsed.get("max_rows", 1000),
            "total_columns": total_cols,
        }

    if directive == "image":
        parsed = _parse_directive_args(args_str)
        pos = parsed.get("_positional", [])
        return {
            "type": "image",
            "path": pos[0] if pos else "",
            "width": parsed.get("width", 0),
            "height": parsed.get("height", 0),
            "align": parsed.get("align", "left"),
        }

    return None


def _parse_block(block_type: str, args_str: str, opts: dict, lines: list[str]) -> dict | None:
    """Parse a block directive into a section dict."""
    if block_type == "columns":
        return _parse_block_columns(args_str, opts, lines)
    elif block_type == "box":
        return _parse_block_box(args_str, opts, lines)
    elif block_type == "metrics":
        return _parse_block_metrics(lines)
    elif block_type == "kv":
        return _parse_block_kv(lines)
    return None


def _parse_block_columns(args_str: str, opts: dict, lines: list[str]) -> dict:
    """Parse {{columns: 55, 45 | bg=#4AAECC border}}...|||...{{/columns}}"""
    # Parse layout percentages
    layout = []
    if args_str:
        for part in args_str.split(","):
            try:
                layout.append(int(part.strip()))
            except ValueError:
                pass

    # Split columns by |||
    col_texts = []
    current = []
    for line in lines:
        if line.strip() == "|||":
            col_texts.append("\n".join(current))
            current = []
        else:
            current.append(line)
    col_texts.append("\n".join(current))

    if not layout:
        layout = [100 // max(len(col_texts), 1)] * len(col_texts)

    cols = []
    for text in col_texts:
        content = md_inline(text.strip())
        cols.append({"content": content})

    sec = {"type": "columns", "layout": layout, "cols": cols}
    if opts.get("bg"):
        sec["bg"] = opts["bg"]
    if opts.get("border"):
        sec["border"] = True
    return sec


def _parse_block_box(args_str: str, opts: dict, lines: list[str]) -> dict:
    """Parse {{box | bg=#f0f0f0 border}}...{{/box}}"""
    content = md_inline("\n".join(lines).strip())
    sec = {"type": "box", "content": content}
    if opts.get("bg"):
        sec["bg"] = opts["bg"]
    if opts.get("border") or not opts.get("bg"):
        sec["border"] = True  # default to bordered
    return sec


def _parse_block_metrics(lines: list[str]) -> dict:
    """Parse {{metrics}} block — each line: label | column | agg | format"""
    items = []
    for line in lines:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            item = {"label": parts[0], "column": parts[1], "agg": parts[2]}
            if len(parts) >= 4 and parts[3]:
                item["format"] = parts[3]
            items.append(item)
    return {"type": "metrics", "items": items}


def _parse_block_kv(lines: list[str]) -> dict:
    """Parse {{kv}} block — each line: Label | Value"""
    items = []
    for line in lines:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) == 2:
            items.append({"label": parts[0], "value": parts[1]})
        elif len(parts) == 1 and parts[0]:
            items.append({"label": parts[0], "value": ""})
    return {"type": "key_value", "items": items}


# ---- Dispatcher ---------------------------------------------------------------

def render_section(section: dict, ctx: RenderContext) -> list:
    """Dispatch a single section to its renderer. Returns list[Flowable]."""
    sec_type = section.get("type", "")
    renderer = SECTION_RENDERERS.get(sec_type)
    if not renderer:
        from reportlab.platypus import Paragraph
        return [Paragraph(f"<i>[Unknown section: {sec_type}]</i>", ctx.styles["Normal"])]
    try:
        return renderer(section, ctx)
    except Exception as e:
        from reportlab.platypus import Paragraph
        return [Paragraph(f"<i>[Error in {sec_type}: {e}]</i>", ctx.styles["Normal"])]


# ---- Section renderers --------------------------------------------------------

def render_title_page(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from datetime import date

    colors = ctx.rl["colors"]
    primary = hex_to_color(colors, ctx.theme.get("primary_color", "#4b6777"))
    font = ctx.theme.get("font_family", "Helvetica")

    title_style = ParagraphStyle(
        "TitlePage", fontName=f"{font}-Bold" if font == "Helvetica" else font,
        fontSize=28, leading=34, alignment=TA_CENTER, textColor=primary, spaceAfter=12)
    sub_style = ParagraphStyle(
        "TitleSub", fontName=font, fontSize=14, leading=20,
        alignment=TA_CENTER, textColor=colors.Color(0.4, 0.4, 0.4), spaceAfter=8)
    date_style = ParagraphStyle(
        "TitleDate", fontName=font, fontSize=11, leading=16,
        alignment=TA_CENTER, textColor=colors.Color(0.5, 0.5, 0.5))

    els = [Spacer(1, ctx.page_height * 0.3)]
    els.append(Paragraph(bind_data(section.get("title", "Report"), ctx), title_style))
    if section.get("subtitle"):
        els.append(Paragraph(bind_data(section["subtitle"], ctx), sub_style))
    if section.get("show_date", True):
        els.append(Spacer(1, 8))
        els.append(Paragraph(date.today().strftime("%B %d, %Y"), date_style))
    els.append(PageBreak())
    return els


def render_heading(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle

    colors = ctx.rl["colors"]
    primary = hex_to_color(colors, ctx.theme.get("primary_color", "#4b6777"))
    font = ctx.theme.get("font_family", "Helvetica")
    level = section.get("level", 1)
    sz = {1: 18, 2: 15, 3: 12}.get(level, 18)

    style = ParagraphStyle(
        f"H{level}", fontName=f"{font}-Bold" if font == "Helvetica" else font,
        fontSize=sz, leading=sz + 6, textColor=primary, spaceBefore=8, spaceAfter=4)
    return [Paragraph(bind_data(section.get("text", ""), ctx), style), Spacer(1, 4)]


def render_text(section: dict, ctx: RenderContext) -> list:
    """Rich text with alignment, font size override, bold, color."""
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    colors = ctx.rl["colors"]
    font = ctx.theme.get("font_family", "Helvetica")
    base_size = ctx.theme.get("font_size", 9)

    sz = section.get("font_size", base_size + 1)
    bold = section.get("bold", False)
    color_hex = section.get("color", "")
    align_str = section.get("align", "left")

    align_map = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}
    text_color = hex_to_color(colors, color_hex) if color_hex else colors.Color(0.2, 0.2, 0.2)
    fn = f"{font}-Bold" if (font == "Helvetica" and bold) else font

    style = ParagraphStyle("TextSec", fontName=fn, fontSize=sz, leading=sz + 5,
                           alignment=align_map.get(align_str, TA_LEFT), textColor=text_color)

    content = bind_data(section.get("content", ""), ctx)
    content = content.replace("\n", "<br/>")
    if bold and font != "Helvetica":
        content = f"<b>{content}</b>"
    return [Paragraph(content, style), Spacer(1, 4)]


def render_table(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Table, TableStyle, Spacer

    colors = ctx.rl["colors"]
    font = ctx.theme.get("font_family", "Helvetica")
    font_size = ctx.theme.get("font_size", 9)

    cols_str = section.get("columns", "").strip()
    render_cols = [c.strip() for c in cols_str.split(",") if c.strip()] if cols_str else list(ctx.columns)
    if not render_cols:
        return []

    max_rows = min(section.get("max_rows", 1000), ctx.n_rows)

    header = render_cols
    rows = []
    for i in range(max_rows):
        row = []
        for col in render_cols:
            vals = ctx.df_data.get(col)
            row.append(str(vals[i]) if vals and i < len(vals) else "")
        rows.append(row)

    total_cols = section.get("total_columns", [])
    footer = None
    if total_cols:
        footer = []
        for col in render_cols:
            if col in total_cols:
                col_data = ctx.df_data.get(col, [])
                total = _compute_agg(col_data[:max_rows], "sum")
                try:
                    footer.append(format(total, ",.2f"))
                except (ValueError, TypeError):
                    footer.append(str(total))
            else:
                footer.append("")
        if footer:
            footer[0] = footer[0] or "TOTAL"

    header_bg = hex_to_color(colors, section.get("header_bg_color", ctx.theme.get("primary_color", "#4b6777")))
    header_text = hex_to_color(colors, section.get("header_text_color", "#ffffff"))
    alt_row = hex_to_color(colors, section.get("alternating_row_color", "#f0f4f7"))

    table_content = [header] + rows
    if footer:
        table_content.append(footer)

    t = Table(table_content, repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), header_text),
        ("FONTNAME", (0, 0), (-1, 0), f"{font}-Bold" if font == "Helvetica" else font),
        ("FONTSIZE", (0, 0), (-1, 0), font_size + 1),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("FONTSIZE", (0, 1), (-1, -1), font_size),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(table_content)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), alt_row))
    if footer:
        last = len(table_content) - 1
        cmds.append(("FONTNAME", (0, last), (-1, last), f"{font}-Bold" if font == "Helvetica" else font))
        cmds.append(("LINEABOVE", (0, last), (-1, last), 1, colors.Color(0.3, 0.3, 0.3)))

    t.setStyle(TableStyle(cmds))
    return [t, Spacer(1, 8)]


def render_static_table(section: dict, ctx: RenderContext) -> list:
    """Render a static markdown table (headers + rows defined in template)."""
    from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    colors = ctx.rl["colors"]
    font = ctx.theme.get("font_family", "Helvetica")
    font_size = ctx.theme.get("font_size", 9)
    primary = hex_to_color(colors, ctx.theme.get("primary_color", "#4b6777"))

    headers = section.get("headers", [])
    rows = section.get("rows", [])
    if not headers and not rows:
        return []

    # Create paragraph styles for cell content (allows bold/italic)
    header_style = ParagraphStyle("STH", fontName=f"{font}-Bold" if font == "Helvetica" else font,
                                   fontSize=font_size + 1, leading=font_size + 6,
                                   alignment=TA_LEFT, textColor=colors.white)
    cell_style = ParagraphStyle("STC", fontName=font, fontSize=font_size,
                                 leading=font_size + 5, alignment=TA_LEFT)
    bold_cell_style = ParagraphStyle("STCB", fontName=f"{font}-Bold" if font == "Helvetica" else font,
                                      fontSize=font_size, leading=font_size + 5, alignment=TA_LEFT)

    def make_cell(text, is_header=False):
        text = bind_data(text, ctx)
        if is_header:
            return Paragraph(md_inline(text), header_style)
        # Check if entire cell is bold
        if text.startswith("<b>") or text.startswith("**"):
            text = md_inline(text)
            return Paragraph(text, cell_style)
        return Paragraph(md_inline(text), cell_style)

    table_data = []
    if headers:
        table_data.append([make_cell(h, is_header=True) for h in headers])
    for row in rows:
        table_data.append([make_cell(c) for c in row])

    if not table_data:
        return []

    t = Table(table_data, repeatRows=1 if headers else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if headers:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), primary))

    t.setStyle(TableStyle(cmds))
    return [t, Spacer(1, 8)]


def render_metrics(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    colors = ctx.rl["colors"]
    primary = hex_to_color(colors, ctx.theme.get("primary_color", "#4b6777"))
    font = ctx.theme.get("font_family", "Helvetica")
    items = section.get("items", [])
    if not items:
        return []

    label_style = ParagraphStyle("ML", fontName=font, fontSize=9, leading=12,
                                 alignment=TA_CENTER, textColor=colors.Color(0.5, 0.5, 0.5))
    value_style = ParagraphStyle("MV", fontName=f"{font}-Bold" if font == "Helvetica" else font,
                                 fontSize=16, leading=22, alignment=TA_CENTER, textColor=primary)

    labels, values = [], []
    for item in items:
        col_data = ctx.df_data.get(item.get("column", ""), [])
        val = _compute_agg(col_data, item.get("agg", "count"))
        fmt = item.get("format", "")
        try:
            val_str = format(val, fmt) if fmt else str(val)
        except (ValueError, TypeError):
            val_str = str(val)
        labels.append(Paragraph(item.get("label", ""), label_style))
        values.append(Paragraph(val_str, value_style))

    t = Table([values, labels], colWidths=[ctx.page_width / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.96, 0.97, 0.98)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.85, 0.85)),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.Color(0.85, 0.85, 0.85)),
    ]))
    return [t, Spacer(1, 10)]


def render_chart(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Spacer

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from io import BytesIO
        from reportlab.platypus import Image
    except ImportError:
        from reportlab.platypus import Paragraph
        return [Paragraph("<i>[Chart: matplotlib not installed]</i>", ctx.styles["Normal"])]

    chart_type = section.get("chart_type", "bar")
    x_col, y_col = section.get("x_column", ""), section.get("y_column", "")
    width, height = section.get("width", 500), section.get("height", 300)
    x_data, y_data = ctx.df_data.get(x_col, []), ctx.df_data.get(y_col, [])

    if not x_data or not y_data:
        from reportlab.platypus import Paragraph
        return [Paragraph(f"<i>[Chart: missing '{x_col}' or '{y_col}']</i>", ctx.styles["Normal"])]

    max_pts = min(50, len(x_data), len(y_data))
    x_vals = [str(v) for v in x_data[:max_pts]]
    y_vals = []
    for v in y_data[:max_pts]:
        try:
            y_vals.append(float(v))
        except (ValueError, TypeError):
            y_vals.append(0)

    primary_hex = ctx.theme.get("primary_color", "#4b6777")
    fig, ax = plt.subplots(figsize=(width / 80, height / 80))
    if chart_type == "line":
        ax.plot(range(len(x_vals)), y_vals, color=primary_hex, linewidth=1.5)
    elif chart_type == "pie":
        ax.pie(y_vals, labels=x_vals, autopct="%1.1f%%", startangle=90)
    else:
        ax.bar(range(len(x_vals)), y_vals, color=primary_hex)
    if chart_type != "pie":
        ax.set_xticks(range(len(x_vals)))
        ax.set_xticklabels(x_vals, rotation=45, ha="right", fontsize=7)
        ax.set_xlabel(x_col, fontsize=8)
        ax.set_ylabel(y_col, fontsize=8)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return [Image(buf, width=width * 0.72, height=height * 0.72), Spacer(1, 8)]


def render_columns(section: dict, ctx: RenderContext) -> list:
    """Multi-column side-by-side layout with optional bg color and border."""
    from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    colors = ctx.rl["colors"]
    cols = section.get("cols", [])
    if not cols:
        return []

    layout = section.get("layout", [])
    if not layout:
        layout = [100 // len(cols)] * len(cols)

    widths = [ctx.page_width * (w / 100) for w in layout]
    font = ctx.theme.get("font_family", "Helvetica")
    base_size = ctx.theme.get("font_size", 9)

    row_cells = []
    for col_def in cols:
        child_sections = col_def.get("sections", [])
        content = col_def.get("content", "")

        if child_sections:
            flowables = []
            for child in child_sections:
                flowables.extend(render_section(child, ctx))
            row_cells.append(flowables)
        elif content:
            content = bind_data(content, ctx).replace("\n", "<br/>")
            style = ParagraphStyle("ColText", fontName=font, fontSize=base_size + 1,
                                   leading=base_size + 6, alignment=TA_LEFT)
            row_cells.append([Paragraph(content, style)])
        else:
            row_cells.append([Paragraph("", ctx.styles["Normal"])])

    t = Table([row_cells], colWidths=widths)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    bg_hex = section.get("bg")
    if bg_hex:
        cmds.append(("BACKGROUND", (0, 0), (-1, -1), hex_to_color(colors, bg_hex)))
        # White text on colored background
        cmds.append(("TEXTCOLOR", (0, 0), (-1, -1), colors.white))

    if section.get("border"):
        cmds.append(("BOX", (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)))
        cmds.append(("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.Color(0.7, 0.7, 0.7)))

    t.setStyle(TableStyle(cmds))
    return [t, Spacer(1, 6)]


def render_box(section: dict, ctx: RenderContext) -> list:
    """Bordered frame containing text, with optional background color."""
    from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    colors = ctx.rl["colors"]
    font = ctx.theme.get("font_family", "Helvetica")
    base_size = ctx.theme.get("font_size", 9)

    content = bind_data(section.get("content", ""), ctx).replace("\n", "<br/>")
    style = ParagraphStyle("BoxText", fontName=font, fontSize=base_size + 1,
                           leading=base_size + 6, alignment=TA_LEFT)

    t = Table([[Paragraph(content, style)]], colWidths=[ctx.page_width])
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]

    bg_hex = section.get("bg")
    if bg_hex:
        cmds.append(("BACKGROUND", (0, 0), (-1, -1), hex_to_color(colors, bg_hex)))

    if section.get("border", True):
        cmds.append(("BOX", (0, 0), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)))

    t.setStyle(TableStyle(cmds))
    return [t, Spacer(1, 6)]


def render_key_value(section: dict, ctx: RenderContext) -> list:
    """Key-value pair grid — label:value rows aligned neatly."""
    from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    colors = ctx.rl["colors"]
    font = ctx.theme.get("font_family", "Helvetica")
    base_size = ctx.theme.get("font_size", 9)
    items = section.get("items", [])
    if not items:
        return []

    label_width = section.get("label_width", 35)
    label_style = ParagraphStyle("KVL", fontName=f"{font}-Bold" if font == "Helvetica" else font,
                                 fontSize=base_size + 1, leading=base_size + 6,
                                 textColor=colors.Color(0.35, 0.35, 0.35), alignment=TA_LEFT)
    value_style = ParagraphStyle("KVV", fontName=font, fontSize=base_size + 1,
                                 leading=base_size + 6, textColor=colors.Color(0.15, 0.15, 0.15),
                                 alignment=TA_LEFT)

    rows = []
    for item in items:
        label = bind_data(md_inline(str(item.get("label", ""))), ctx)
        value = bind_data(md_inline(str(item.get("value", ""))), ctx)
        rows.append([Paragraph(label, label_style), Paragraph(value, value_style)])

    lw = ctx.page_width * (label_width / 100)
    vw = ctx.page_width - lw
    t = Table(rows, colWidths=[lw, vw])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [t, Spacer(1, 6)]


def render_divider(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Spacer
    from reportlab.platypus.flowables import HRFlowable

    colors = ctx.rl["colors"]
    color = hex_to_color(colors, section.get("color", "#cccccc"))
    thickness = section.get("thickness", 1)
    space = section.get("space_before", 6)

    hr = HRFlowable(width="100%", thickness=thickness, color=color,
                     spaceBefore=space, spaceAfter=space)
    return [hr]


def render_image(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Spacer, Paragraph, Image

    img_path = section.get("path", "")
    if not img_path or not Path(img_path).exists():
        return [Paragraph(f"<i>[Image not found: {img_path}]</i>", ctx.styles["Normal"])]

    kwargs = {}
    width = section.get("width", 0)
    height = section.get("height", 0)
    if width:
        kwargs["width"] = width
    if height:
        kwargs["height"] = height

    img = Image(img_path, **kwargs)

    align = section.get("align", "left")
    if align == "center":
        img.hAlign = "CENTER"
    elif align == "right":
        img.hAlign = "RIGHT"
    else:
        img.hAlign = "LEFT"

    return [img, Spacer(1, 6)]


def render_spacer(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import Spacer
    return [Spacer(1, section.get("height", 20))]


def render_page_break(section: dict, ctx: RenderContext) -> list:
    from reportlab.platypus import PageBreak
    return [PageBreak()]


SECTION_RENDERERS = {
    "title_page":    render_title_page,
    "heading":       render_heading,
    "text":          render_text,
    "table":         render_table,
    "static_table":  render_static_table,
    "metrics":       render_metrics,
    "chart":         render_chart,
    "columns":       render_columns,
    "box":           render_box,
    "key_value":     render_key_value,
    "divider":       render_divider,
    "image":         render_image,
    "spacer":        render_spacer,
    "page_break":    render_page_break,
}


# ---- Legacy migration ---------------------------------------------------------

def _migrate_legacy_config(config: dict) -> dict:
    """Ensure config has 'sections' (from template, sections, or legacy fields)."""
    # Template mode: parse markdown into sections
    if "template" in config:
        config = dict(config)
        config["sections"] = parse_template(config["template"])
        return config

    if "sections" in config:
        return config

    sections = []
    if config.get("title"):
        sections.append({"type": "heading", "text": config["title"], "level": 1})
    if config.get("subtitle"):
        sections.append({"type": "text", "content": config["subtitle"]})
    sections.append({
        "type": "table", "columns": config.get("columns", ""),
        "max_rows": config.get("max_rows", 1000),
        "header_bg_color": config.get("header_bg_color", "#4b6777"),
        "header_text_color": config.get("header_text_color", "#ffffff"),
        "alternating_row_color": config.get("alternating_row_color", "#f0f4f7"),
    })
    return {
        "output_path": config.get("output_path", "report.pdf"),
        "page_size": config.get("page_size", "A4"),
        "orientation": config.get("orientation", "portrait"),
        "theme": {
            "primary_color": config.get("header_bg_color", "#4b6777"),
            "font_family": config.get("font_family", "Helvetica"),
            "font_size": config.get("font_size", 9),
        },
        "show_header": config.get("show_header", True),
        "show_footer": config.get("show_footer", True),
        "footer_text": config.get("footer_text", ""),
        "sections": sections,
    }


# ---- Node class ---------------------------------------------------------------

class PdfRenderNode(BaseNode):
    meta = NodeMeta(
        id="pdf_render",
        label="PDF Report",
        category="output",
        description="Assemble PDF documents from markdown templates with {{directives}}",
        inputs=[NodePort(name="in", description="Dataframe to render as PDF")],
        outputs=[],
        config_schema={
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "default": "report.pdf"},
                "page_size": {"type": "string", "enum": ["A4", "Letter", "A3", "Legal"], "default": "A4"},
                "orientation": {"type": "string", "enum": ["portrait", "landscape"], "default": "portrait"},
                "theme": {
                    "type": "object",
                    "properties": {
                        "primary_color": {"type": "string", "default": "#4b6777"},
                        "font_family": {"type": "string", "enum": ["Helvetica", "Times-Roman", "Courier"], "default": "Helvetica"},
                        "font_size": {"type": "integer", "default": 9},
                    },
                },
                "show_header": {"type": "boolean", "default": True},
                "show_footer": {"type": "boolean", "default": True},
                "footer_text": {"type": "string", "default": ""},
                "template": {"type": "string", "description": "Markdown template with {{directives}}"},
                "sections": {
                    "type": "array",
                    "description": "Ordered list of document sections (alternative to template)",
                    "items": {"type": "object"},
                },
            },
        },
    )

    def execute(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, A3, letter, legal, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate
        except ImportError:
            return {"error": "reportlab not installed. Run: pip install reportlab"}

        table_data = inputs.get("df")
        if table_data is None:
            return {"error": "No input data"}

        config = _migrate_legacy_config(config)

        all_columns = inputs.get("columns", [])
        if hasattr(table_data, "columns"):
            all_columns = list(table_data.columns)

        n = len(table_data)
        data_dict = table_data.to_dict()

        df_data = {}
        for col in all_columns:
            val = data_dict.get(col)
            if isinstance(val, dict):
                df_data[col] = [val.get(i, "") for i in range(n)]
            elif isinstance(val, list):
                df_data[col] = val
            else:
                df_data[col] = []

        page_sizes = {"A4": A4, "A3": A3, "Letter": letter, "Legal": legal}
        ps = page_sizes.get(config.get("page_size", "A4"), A4)
        if config.get("orientation", "portrait") == "landscape":
            ps = landscape(ps)

        theme = config.get("theme", {})
        font = theme.get("font_family", "Helvetica")
        show_header = config.get("show_header", True)
        show_footer = config.get("show_footer", True)
        footer_text = config.get("footer_text", "")

        output_path = config.get("output_path", "report.pdf")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        def on_page(canvas, doc):
            if show_header:
                canvas.saveState()
                canvas.setFont(font, 8)
                canvas.setFillColor(colors.Color(0.5, 0.5, 0.5))
                canvas.drawString(doc.leftMargin, ps[1] - 25,
                                  config.get("output_path", "report.pdf"))
                canvas.restoreState()
            if show_footer:
                canvas.saveState()
                canvas.setFont(font, 8)
                canvas.setFillColor(colors.Color(0.5, 0.5, 0.5))
                ft = footer_text or f"Page {doc.page}"
                canvas.drawString(doc.leftMargin, 20, ft)
                canvas.restoreState()

        doc = SimpleDocTemplate(output_path, pagesize=ps,
                                topMargin=40 if show_header else 25,
                                bottomMargin=35 if show_footer else 20,
                                leftMargin=40, rightMargin=40)
        page_width = ps[0] - 80
        styles = getSampleStyleSheet()

        ctx = RenderContext(
            df_data=df_data, columns=all_columns, n_rows=n, theme=theme,
            styles=styles, page_width=page_width, page_height=ps[1],
            rl={"colors": colors})

        elements = []
        for sec in config.get("sections", []):
            elements.extend(render_section(sec, ctx))

        if not elements:
            from reportlab.platypus import Paragraph
            elements.append(Paragraph("<i>No sections configured</i>", styles["Normal"]))

        doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)

        import os
        return {
            "path": str(Path(output_path).resolve()),
            "size": os.path.getsize(output_path),
            "format": "pdf",
            "rows": n,
            "columns": all_columns,
            "pages": doc.page,
            "sections": len(config.get("sections", [])),
        }
