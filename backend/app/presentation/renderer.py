import os
from typing import List, Dict, Any
from pptx import Presentation as PPTXPresentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import CategoryChartData

from app.presentation.themes import get_theme, PresentationTheme
from app.presentation.layout_engine import LayoutEngine, Rect
from app.schemas.presentation_spec import PresentationSpec, SlideSpec, Citation


class PresentationRenderer:
    def __init__(self, theme_name: str = "Professional"):
        self.theme: PresentationTheme = get_theme(theme_name)

    def render(self, spec: PresentationSpec, output_path: str) -> str:
        prs = PPTXPresentation()
        
        # Set 16:9 Widescreen dimensions (10.0 x 5.625 inches)
        prs.slide_width = Inches(LayoutEngine.SLIDE_WIDTH)
        prs.slide_height = Inches(LayoutEngine.SLIDE_HEIGHT)
        
        # Use blank slide layout (index 6 in default template)
        blank_slide_layout = prs.slide_layouts[6]

        for slide_spec in spec.slides:
            s_dict = slide_spec.model_dump() if hasattr(slide_spec, "model_dump") else slide_spec
            s_type = s_dict.get("type", "bullet")

            if s_type == "table":
                # Handle Table Pagination across slides if necessary
                columns = s_dict.get("columns", [])
                rows = s_dict.get("rows", [])
                paginated_specs = LayoutEngine.split_table_rows(columns, rows)
                
                for idx, p_spec in enumerate(paginated_specs, start=1):
                    slide = prs.slides.add_slide(blank_slide_layout)
                    self._apply_background(slide)
                    
                    title = s_dict.get("title", "Table Analysis")
                    if p_spec.get("total_parts", 1) > 1:
                        title += f" (Part {p_spec['part']} of {p_spec['total_parts']})"
                    
                    self._render_header(slide, title)
                    self._render_table(slide, p_spec["columns"], p_spec["rows"])
                    self._render_footer(slide, s_dict.get("citations", []))
            else:
                slide = prs.slides.add_slide(blank_slide_layout)
                self._apply_background(slide)

                if s_type == "title":
                    self._render_title_slide(slide, s_dict.get("title", ""), s_dict.get("subtitle", ""))
                elif s_type == "section":
                    self._render_section_slide(slide, s_dict.get("title", ""), s_dict.get("subtitle", ""))
                elif s_type == "bullet":
                    self._render_header(slide, s_dict.get("title", ""))
                    self._render_bullet_slide(slide, s_dict.get("bullets", []))
                    self._render_footer(slide, s_dict.get("citations", []))
                elif s_type == "two_column":
                    self._render_header(slide, s_dict.get("title", ""))
                    self._render_two_column_slide(slide, s_dict)
                    self._render_footer(slide, s_dict.get("citations", []))
                elif s_type == "chart":
                    self._render_header(slide, s_dict.get("title", ""))
                    self._render_chart_slide(slide, s_dict)
                    self._render_footer(slide, s_dict.get("citations", []))
                elif s_type == "quote":
                    self._render_header(slide, s_dict.get("title", ""))
                    self._render_quote_slide(slide, s_dict)
                    self._render_footer(slide, s_dict.get("citations", []))
                elif s_type == "summary":
                    self._render_header(slide, s_dict.get("title", ""))
                    self._render_summary_slide(slide, s_dict.get("key_takeaways", []))
                    self._render_footer(slide, s_dict.get("citations", []))
                else:
                    self._render_header(slide, s_dict.get("title", "Slide"))
                    self._render_bullet_slide(slide, ["Content block"])
                    self._render_footer(slide, s_dict.get("citations", []))

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        prs.save(output_path)
        return output_path

    def _apply_background(self, slide):
        bg = slide.background
        fill = bg.fill
        fill.solid()
        r, g, b = self.theme.colors.background
        fill.fore_color.rgb = RGBColor(r, g, b)

    def _render_header(self, slide, title_text: str):
        rect = LayoutEngine.get_title_rect()
        txBox = slide.shapes.add_textbox(Inches(rect.x), Inches(rect.y), Inches(rect.width), Inches(rect.height))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.name = self.theme.primary_font
        p.font.size = Pt(self.theme.heading_size)
        p.font.bold = True
        r, g, b = self.theme.colors.primary
        p.font.color.rgb = RGBColor(r, g, b)

    def _render_footer(self, slide, citations: List[Dict[str, Any]]):
        if not citations:
            return
        c_text = "Sources: " + ", ".join([f"{c.get('document_name', 'Doc')} (p. {c.get('page') or 'N/A'})" for c in citations[:2]])
        y_pos = LayoutEngine.SLIDE_HEIGHT - LayoutEngine.FOOTER_HEIGHT
        txBox = slide.shapes.add_textbox(
            Inches(LayoutEngine.MARGIN_LEFT),
            Inches(y_pos),
            Inches(LayoutEngine.SLIDE_WIDTH - LayoutEngine.MARGIN_LEFT - LayoutEngine.MARGIN_RIGHT),
            Inches(LayoutEngine.FOOTER_HEIGHT)
        )
        p = txBox.text_frame.paragraphs[0]
        p.text = c_text
        p.font.name = self.theme.secondary_font
        p.font.size = Pt(9)
        p.font.italic = True
        r, g, b = self.theme.colors.secondary
        p.font.color.rgb = RGBColor(r, g, b)

    def _render_title_slide(self, slide, title: str, subtitle: str):
        # Decorative Title Card Box
        card = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(1.0), Inches(1.2), Inches(8.0), Inches(3.2)
        )
        card.fill.solid()
        r, g, b = self.theme.colors.card_bg
        card.fill.fore_color.rgb = RGBColor(r, g, b)
        card.line.color.rgb = RGBColor(r, g, b)

        tf = card.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        
        p = tf.paragraphs[0]
        p.text = title
        p.font.name = self.theme.primary_font
        p.font.size = Pt(self.theme.title_size)
        p.font.bold = True
        pr, pg, pb = self.theme.colors.primary
        p.font.color.rgb = RGBColor(pr, pg, pb)
        p.alignment = PP_ALIGN.CENTER

        if subtitle:
            p2 = tf.add_paragraph()
            p2.text = subtitle
            p2.font.name = self.theme.secondary_font
            p2.font.size = Pt(self.theme.subtitle_size)
            sr, sg, sb = self.theme.colors.secondary
            p2.font.color.rgb = RGBColor(sr, sg, sb)
            p2.alignment = PP_ALIGN.CENTER

    def _render_section_slide(self, slide, title: str, subtitle: str):
        self._render_title_slide(slide, title, subtitle)

    def _render_bullet_slide(self, slide, bullets: List[str]):
        rect = LayoutEngine.get_content_rect()
        txBox = slide.shapes.add_textbox(Inches(rect.x), Inches(rect.y), Inches(rect.width), Inches(rect.height))
        tf = txBox.text_frame
        tf.word_wrap = True

        for idx, bullet in enumerate(bullets):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = f"• {bullet}"
            p.font.name = self.theme.secondary_font
            p.font.size = Pt(self.theme.body_size)
            r, g, b = self.theme.colors.text
            p.font.color.rgb = RGBColor(r, g, b)
            p.space_after = Pt(12)

    def _render_two_column_slide(self, slide, s_dict: Dict[str, Any]):
        left_rect, right_rect = LayoutEngine.get_two_column_rects()

        # Left Column Box
        left_box = slide.shapes.add_textbox(Inches(left_rect.x), Inches(left_rect.y), Inches(left_rect.width), Inches(left_rect.height))
        ltf = left_box.text_frame
        ltf.word_wrap = True
        lp = ltf.paragraphs[0]
        lp.text = s_dict.get("left_title", "Left Column")
        lp.font.bold = True
        lp.font.size = Pt(16)

        for b in s_dict.get("left_content", []):
            p = ltf.add_paragraph()
            p.text = f"• {b}"
            p.font.size = Pt(13)
            p.space_after = Pt(8)

        # Right Column Box
        right_box = slide.shapes.add_textbox(Inches(right_rect.x), Inches(right_rect.y), Inches(right_rect.width), Inches(right_rect.height))
        rtf = right_box.text_frame
        rtf.word_wrap = True
        rp = rtf.paragraphs[0]
        rp.text = s_dict.get("right_title", "Right Column")
        rp.font.bold = True
        rp.font.size = Pt(16)

        for b in s_dict.get("right_content", []):
            p = rtf.add_paragraph()
            p.text = f"• {b}"
            p.font.size = Pt(13)
            p.space_after = Pt(8)

    def _render_table(self, slide, columns: List[str], rows: List[List[str]]):
        rect = LayoutEngine.get_content_rect()
        num_rows = len(rows) + 1
        num_cols = max(len(columns), 1)

        table_shape = slide.shapes.add_table(
            num_rows, num_cols,
            Inches(rect.x), Inches(rect.y), Inches(rect.width), Inches(rect.height)
        )
        table = table_shape.table

        # Populate headers
        for col_idx, col_name in enumerate(columns):
            cell = table.cell(0, col_idx)
            cell.text = str(col_name)
            r, g, b = self.theme.colors.primary
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(r, g, b)
            for p in cell.text_frame.paragraphs:
                p.font.bold = True
                p.font.color.rgb = RGBColor(255, 255, 255)
                p.font.size = Pt(12)

        # Populate rows
        for row_idx, row in enumerate(rows, start=1):
            bg_color = self.theme.colors.card_bg if row_idx % 2 == 0 else self.theme.colors.background
            for col_idx, val in enumerate(row):
                if col_idx < num_cols:
                    cell = table.cell(row_idx, col_idx)
                    cell.text = str(val)
                    cell.fill.solid()
                    cr, cg, cb = bg_color
                    cell.fill.fore_color.rgb = RGBColor(cr, cg, cb)
                    for p in cell.text_frame.paragraphs:
                        p.font.size = Pt(11)
                        tr, tg, tb = self.theme.colors.text
                        p.font.color.rgb = RGBColor(tr, tg, tb)

    def _render_chart_slide(self, slide, s_dict: Dict[str, Any]):
        rect = LayoutEngine.get_content_rect()
        chart_type_str = s_dict.get("chart_type", "bar")
        labels = s_dict.get("labels", ["A", "B", "C"])
        values = s_dict.get("values", [10.0, 20.0, 30.0])

        chart_data = CategoryChartData()
        chart_data.categories = labels
        chart_data.add_series("Series 1", values)

        xl_chart_type = XL_CHART_TYPE.COLUMN_CLUSTERED
        if chart_type_str == "line":
            xl_chart_type = XL_CHART_TYPE.LINE
        elif chart_type_str == "pie":
            xl_chart_type = XL_CHART_TYPE.PIE

        slide.shapes.add_chart(
            xl_chart_type,
            Inches(rect.x), Inches(rect.y), Inches(rect.width), Inches(rect.height),
            chart_data
        )

    def _render_quote_slide(self, slide, s_dict: Dict[str, Any]):
        rect = LayoutEngine.get_content_rect()
        box = slide.shapes.add_textbox(Inches(rect.x), Inches(rect.y), Inches(rect.width), Inches(rect.height))
        tf = box.text_frame
        tf.word_wrap = True

        p = tf.paragraphs[0]
        p.text = f"“{s_dict.get('quote', '')}”"
        p.font.italic = True
        p.font.size = Pt(20)
        r, g, b = self.theme.colors.primary
        p.font.color.rgb = RGBColor(r, g, b)

        author = s_dict.get("author")
        if author:
            p2 = tf.add_paragraph()
            p2.text = f"— {author}"
            p2.font.bold = True
            p2.font.size = Pt(14)
            p2.space_before = Pt(12)

    def _render_summary_slide(self, slide, takeaways: List[str]):
        rect = LayoutEngine.get_content_rect()
        box = slide.shapes.add_textbox(Inches(rect.x), Inches(rect.y), Inches(rect.width), Inches(rect.height))
        tf = box.text_frame
        tf.word_wrap = True

        for idx, item in enumerate(takeaways):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = f"✔  {item}"
            p.font.size = Pt(14)
            p.font.bold = True
            r, g, b = self.theme.colors.accent
            p.font.color.rgb = RGBColor(r, g, b)
            p.space_after = Pt(14)
