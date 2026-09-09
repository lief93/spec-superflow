from __future__ import annotations
import re
from decimal import Decimal, ROUND_HALF_UP
from ui_migration.arkui.formatting import page_number
from ui_migration.common import arkts_string, decimal_literal


class TypographyEmitter:
    def __init__(self, fonts, layout, unresolved, tokens=None):
        self.fonts = fonts
        self.layout = layout
        self.unresolved = unresolved
        self.uses_font_metrics = False
        from .style_tokens import StyleTokenEmitter
        self.tokens = tokens or StyleTokenEmitter()

    def emit(self, component, prefix, is_text, is_text_field):
        style = component['style']
        lines, emitted_phase_paths = [], set()
        if is_text or is_text_field:
            typography = style["typography"]
            line_break = {'simple': 'GREEDY', 'heading': 'BALANCED', 'paragraph': 'HIGH_QUALITY'}.get(typography.get('line_break'))
            if line_break:
                lines.append(f'{prefix}  .lineBreakStrategy(LineBreakStrategy.{line_break})')
                emitted_phase_paths.add('style.typography.line_break')
            font_style = {'normal': 'Normal', 'italic': 'Italic'}.get(typography.get('font_style'))
            if font_style:
                lines.append(f"{prefix}  .fontStyle(FontStyle.{font_style})")
                emitted_phase_paths.add('style.typography.font_style')
            page_font_family = typography["font_family"]
            font_size = typography["font_size_sp"]
            token_size = self.tokens.expression(component, 'typography.font_size_sp')
            token_family = self.tokens.expression(component, 'typography.font_family')
            if token_size:
                lines.append(f'{prefix}  .fontSize({token_size})')
                emitted_phase_paths.add('style.typography.font_size_sp')
            elif font_size is not None:
                rendered_font_size = Decimal(str(font_size))
                if is_text_field:
                    rendered_font_size = rendered_font_size.quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                if is_text and self.fonts.alias(str(page_font_family or ''), typography.get('font_weight')):
                    self.uses_font_metrics = True
                    lines.append(f"{prefix}  .fontSize(this.nativeFontSize({page_number(font_size)}))")
                else:
                    lines.append(f"{prefix}  .fontSize({decimal_literal(rendered_font_size)})")
                emitted_phase_paths.add("style.typography.font_size_sp")
            font_weight = typography["font_weight"]
            token_weight = self.tokens.expression(component, 'typography.font_weight')
            if token_weight or font_weight is not None:
                lines.append(f"{prefix}  .fontWeight({token_weight or font_weight})")
                emitted_phase_paths.add("style.typography.font_weight")
            if token_family:
                lines.append(f'{prefix}  .fontFamily({token_family})')
                emitted_phase_paths.add('style.typography.font_family')
            elif isinstance(page_font_family, str):
                alias = self.fonts.alias(page_font_family, typography.get("font_weight"))
                if alias is not None or page_font_family in {"sans-serif", "serif", "monospace", "HarmonyOS Sans"}:
                    lines.append(f"{prefix}  .fontFamily({arkts_string(alias or page_font_family)})")
                    emitted_phase_paths.add("style.typography.font_family")
                else:
                    self.unresolved(component, "style.typography.font_family", f"font family {page_font_family} has no verified registered asset")
            color = typography["color"]
            token_color = self.tokens.expression(component, 'typography.color')
            if token_color or color is not None:
                lines.append(f"{prefix}  .fontColor({token_color or arkts_string(color)})")
                emitted_phase_paths.add("style.typography.color")
            line_height = typography["line_height_sp"]
            token_height = self.tokens.expression(component, 'typography.line_height_sp')
            font_alias = self.fonts.alias(str(page_font_family or ''), typography.get("font_weight"))
            font_face = next((face for face in self.fonts.faces if face['alias'] == font_alias), None)
            untrimmed = (typography.get('line_height_alignment') == 'center'
                         and typography.get('line_height_trim') == 'none'
                         and typography.get('include_font_padding') is False and line_height is not None)
            if token_height:
                lines.append(f'{prefix}  .lineHeight({token_height})')
                emitted_phase_paths.add('style.typography.line_height_sp')
                if is_text and untrimmed:
                    lines.append(f'{prefix}  .halfLeading(true)')
            elif is_text and untrimmed:
                lines.append(f'{prefix}  .lineHeight({page_number(line_height)})')
                lines.append(f'{prefix}  .halfLeading(true)')
                emitted_phase_paths.update({'style.typography.' + field for field in
                    ('line_height_sp', 'include_font_padding', 'line_height_alignment', 'line_height_trim')})
            elif is_text and font_face is not None and font_size is not None and not token_family:
                self.uses_font_metrics = True
                args = f"$rawfile({arkts_string(font_face['rawfile'])}), {token_size or page_number(font_size)}"
                shift = typography.get('baseline_shift') or 0
                height_args = args + (', ' + page_number(shift) if shift else '')
                if not self.layout.page_snapshot_has_explicit_axis_size(component, 'height') and not any(
                    rule['kind'] == 'constraints' for rule in self.layout.page_snapshot_layout_rules(component)
                ) and (typography.get('min_lines') or 1) == 1:
                    lines.append(f"{prefix}  .constraintSize({{ minHeight: this.nativeLineHeight({height_args}) }})")
                line_helper = 'nativeShiftedLineHeight' if shift else 'nativeLineHeight'
                lines.append(f"{prefix}  .lineHeight(this.{line_helper}({height_args}))")
                if shift:
                    lines.append(f"{prefix}  .baselineOffset(this.nativeBaselineOffset({height_args}))")
                    emitted_phase_paths.add('style.typography.baseline_shift')
                lines.append(f"{prefix}  .halfLeading(true)")
                if line_height is not None:
                    lines.append(f"{prefix}  .lineSpacing(this.nativeLineSpacing({args}, {page_number(line_height)}), {{ onlyBetweenLines: true }})")
                    emitted_phase_paths.add("style.typography.line_height_sp")
            elif line_height is not None:
                lines.append(
                    f"{prefix}  .lineHeight({page_number(line_height)})"
                )
                emitted_phase_paths.add("style.typography.line_height_sp")
            letter_spacing = typography["letter_spacing_sp"]
            token_spacing = self.tokens.expression(component, 'typography.letter_spacing_sp')
            if token_spacing or letter_spacing is not None:
                lines.append(
                    f"{prefix}  .letterSpacing({token_spacing or page_number(letter_spacing)})"
                )
                emitted_phase_paths.add("style.typography.letter_spacing_sp")
            text_align = {
                "start": "TextAlign.Start",
                "center": "TextAlign.Center",
                "end": "TextAlign.End",
                "justify": "TextAlign.Justify",
            }.get(typography["text_align"])
            if text_align is not None:
                lines.append(f"{prefix}  .textAlign({text_align})")
                emitted_phase_paths.add("style.typography.text_align")
            max_lines = typography["max_lines"]
            soft_wrap = typography.get('soft_wrap')
            if soft_wrap is False:
                if is_text and re.search(r'[\n\r\u2028\u2029]', (component['style']['content'].get('text') or '')) is None:
                    lines.append(f'{prefix}  .maxLines(1)')
                    emitted_phase_paths.add('style.typography.soft_wrap')
                    if max_lines is not None:
                        emitted_phase_paths.add('style.typography.max_lines')
                else:
                    self.unresolved(component, 'style.typography.soft_wrap', 'unwrapped hard line breaks require paragraph-specific rendering')
            elif soft_wrap is True:
                emitted_phase_paths.add('style.typography.soft_wrap')
            if max_lines is not None and soft_wrap is not False:
                lines.append(f"{prefix}  .maxLines({max_lines})")
                emitted_phase_paths.add("style.typography.max_lines")
            min_lines = typography.get('min_lines')
            if min_lines == 1:
                emitted_phase_paths.add('style.typography.min_lines')
            elif min_lines is not None:
                if is_text and font_face is not None and font_size is not None and not token_family and not any(
                    rule['kind'] == 'constraints' for rule in self.layout.page_snapshot_layout_rules(component)
                ):
                    if not self.layout.page_snapshot_has_explicit_axis_size(component, 'height'):
                        padding = style['layout'].get('padding_dp') or {}
                        vertical_padding = float(padding.get('top', 0)) + float(padding.get('bottom', 0))
                        args = f"$rawfile({arkts_string(font_face['rawfile'])}), {token_size or page_number(font_size)}, {token_height or page_number(line_height or 0)}, {min_lines}, {page_number(vertical_padding)}"
                        lines.append(f'{prefix}  .constraintSize({{ minHeight: this.nativeMinLinesHeight({args}) }})')
                    emitted_phase_paths.add('style.typography.min_lines')
                else:
                    self.unresolved(component, 'style.typography.min_lines',
                        'minLines > 1 requires verified text font metrics without conflicting constraints; not a reference bbox height')
            overflow = {
                "clip": "TextOverflow.Clip",
                "ellipsis": "TextOverflow.Ellipsis",
            }.get(typography["overflow"])
            if overflow is not None:
                argument = overflow if is_text_field else f"{{ overflow: {overflow} }}"
                lines.append(f"{prefix}  .textOverflow({argument})")
                emitted_phase_paths.add("style.typography.overflow")
            decoration = {
                "none": "TextDecorationType.None",
                "underline": "TextDecorationType.Underline",
                "line_through": "TextDecorationType.LineThrough",
            }.get(typography["decoration"])
            if decoration is not None:
                lines.append(
                    f"{prefix}  .decoration({{ type: {decoration} }})"
                )
                emitted_phase_paths.add("style.typography.decoration")

        return lines, emitted_phase_paths
