package dev.ets

/** Native font metrics preserve Compose's first/last-line leading without an extra UI node. */
internal val materialTypographySupport = """
class __etsMaterialTypography implements AttributeModifier<TextAttribute> {
  private size: number;
  private lineHeight: number;
  private weight: number;
  private tracking: number;

  constructor(size: number, lineHeight: number, weight: number, tracking: number) {
    this.size = size;
    this.lineHeight = lineHeight;
    this.weight = weight;
    this.tracking = tracking;
  }

  applyNormalAttribute(instance: TextAttribute): void {
    const font = new __etsDrawing.Font();
    font.setSize(fp2px(this.size));
    const metrics = font.getMetrics();
    const leading = px2vp(Math.max(0, metrics.descent - metrics.ascent - fp2px(this.lineHeight)) / 2);
    instance.fontSize(this.size).lineHeight(this.lineHeight).fontWeight(this.weight)
      .letterSpacing(this.tracking).halfLeading(true).padding({ top: leading, bottom: leading });
  }
}
""".trimIndent().lines()
