from __future__ import annotations
from dataclasses import dataclass, field
from ui_migration.common import arkts_string
from ui_migration.naming import source_identifier


@dataclass
class ArkUIDocument:
    root: dict
    body: list[str]
    font_faces: list[dict]
    border_builders: list[list[str]]
    overlay_builders: list[list[str]]
    scaffold_states: dict
    constraint_states: dict
    drawing_color_filter: bool
    font_metrics: bool
    layout_pixels: bool
    business_interfaces: list[str] = field(default_factory=list)
    business_methods: list[str] = field(default_factory=list)
    material_item_states: dict = field(default_factory=dict)
    style_token_imports: list[str] = field(default_factory=list)

    def render(self):
        struct_name = source_identifier(self.root['composable'])
        lines = [
            "// Generated only from the audited source-generated version_json.",
            "// Unresolved behavior is recorded in the paired .migration manifest.",
            "",
        ]
        lines.extend(self.style_token_imports)
        if self.drawing_color_filter or self.font_metrics:
            lines.extend(["import drawing from '@ohos.graphics.drawing';", ""])
        if self.font_metrics:
            lines.extend(["import { LengthMetrics } from '@ohos.arkui.node';", ""])
        lines.extend(self.business_interfaces)
        lines.extend([
            "@Component",
            f"export struct {struct_name} {{",
        ])
        for border_builder in self.border_builders:
            lines.extend(border_builder)
        for overlay_builder in self.overlay_builders:
            lines.extend(overlay_builder)
        for name in self.scaffold_states.values():
            lines.extend([f'  @State private {name}{slot.title()}: number = 0' for slot in ('topBar', 'bottomBar')])
        for name in self.material_item_states.values():
            lines.append(f'  @State private {name}: boolean = false')
        for state in self.constraint_states.values():
            for axis in sorted(state['axes']):
                lines.append(f"  @State private {state['name']}{axis.title()}: number = 0")
        if self.layout_pixels:
            lines.extend([
                "  private layoutPx(value: number): string {",
                "    return Math.round(this.getUIContext().vp2px(value)) + 'px'",
                "  }",
                "",
            ])
        if self.font_metrics:
            lines.extend([
                "  private nativeFontSize(size: number): string {",
                "    return Math.floor(this.getUIContext().fp2px(size)) + 'px'",
                "  }",
                "",
                "  private nativeLinePixels(file: Resource, size: number): number {",
                "    const font = new drawing.Font()",
                "    font.setTypeface(drawing.Typeface.makeFromRawFile(file))",
                "    font.setSize(this.getUIContext().fp2px(size))",
                "    const metrics = font.getMetrics()",
                "    return Math.round(metrics.descent) - Math.round(metrics.ascent)",
                "  }",
                "",
                "  private nativeBaselineBottom(file: Resource, size: number, lineHeight: number): number {",
                "    const font = new drawing.Font()",
                "    font.setTypeface(drawing.Typeface.makeFromRawFile(file))",
                "    font.setSize(this.getUIContext().fp2px(size))",
                "    const metrics = font.getMetrics()",
                "    const natural = Math.round(metrics.descent) - Math.round(metrics.ascent)",
                "    const leading = Math.max(0, Math.round(this.getUIContext().fp2px(lineHeight)) - natural)",
                "    return this.getUIContext().px2vp(Math.round(metrics.descent) + Math.ceil(leading / 2))",
                "  }",
                "",
                "  private nativeBaselinePixels(file: Resource, size: number, shift: number): number {",
                "    const font = new drawing.Font()",
                "    font.setTypeface(drawing.Typeface.makeFromRawFile(file))",
                "    font.setSize(this.getUIContext().fp2px(size))",
                "    return -Math.ceil(font.getMetrics().ascent * shift)",
                "  }",
                "",
                "  private nativeBaselineOffset(file: Resource, size: number, shift: number): string {",
                "    return this.nativeBaselinePixels(file, size, shift) + 'px'",
                "  }",
                "",
                "  private nativeLineHeight(file: Resource, size: number, shift: number = 0): string {",
                "    return (this.nativeLinePixels(file, size) + Math.abs(this.nativeBaselinePixels(file, size, shift))) + 'px'",
                "  }",
                "",
                "  private nativeShiftedLineHeight(file: Resource, size: number, shift: number): string {",
                "    return this.nativeLinePixels(file, size) + 'px'",
                "  }",
                "",
                "  private nativeMinLinesHeight(file: Resource, size: number, requested: number, count: number, padding: number): string {",
                "    const natural = this.nativeLinePixels(file, size)",
                "    const extra = Math.max(0, Math.round(this.getUIContext().fp2px(requested)) - natural)",
                "    return (natural * count + extra * (count - 1) + Math.round(this.getUIContext().vp2px(padding))) + 'px'",
                "  }",
                "",
                "  private nativeLineSpacing(file: Resource, size: number, requested: number): LengthMetrics {",
                "    return LengthMetrics.px(Math.max(0, Math.round(this.getUIContext().fp2px(requested)) - this.nativeLinePixels(file, size)))",
                "  }",
                "",
            ])
        if self.font_faces:
            lines.extend([
                "  aboutToAppear(): void {",
                "    const fontManager = this.getUIContext().getFont()",
            ])
            for face in self.font_faces:
                lines.append(
                    "    fontManager.registerFont({ familyName: "
                    f"{arkts_string(face['alias'])}, familySrc: $rawfile({arkts_string(face['rawfile'])}) }})"
                )
            lines.extend(("  }", ""))
        lines.append("  build() {")
        lines.extend([
            "    Stack() {",
            *['  ' + line for line in self.body],
            "    }",
            "      .alignContent(Alignment.TopStart)",
            "      .width('100%')",
            "      .height('100%')",
        ])
        lines.extend(("  }", ""))
        lines.extend(self.business_methods)
        lines.extend(("}", ""))
        return "\n".join(lines)
