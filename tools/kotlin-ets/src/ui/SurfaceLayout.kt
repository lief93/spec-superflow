package dev.ets

/** Material Surface/Card containers propagate parent minima to their content root. */
internal val surfaceLayoutSupport = """
@Component
struct EtsComposeSurface {
  @Builder private emptyContent() {}
  @BuilderParam content: () => void = this.emptyContent;
  @Prop column: boolean = false;
  @Prop fixedWidth: boolean = false;
  @Prop fixedHeight: boolean = false;

  onMeasureSize(info: GeometryInfo, children: Array<Measurable>, constraint: ConstraintSizeOptions): SizeResult {
    let width = Number(constraint.minWidth ?? 0);
    let height = Number(constraint.minHeight ?? 0);
    // ArkUI reports an explicit component size as a maximum, not a minimum.
    if (this.fixedWidth && Number.isFinite(Number(constraint.maxWidth))) width = Number(constraint.maxWidth);
    if (this.fixedHeight && Number.isFinite(Number(constraint.maxHeight))) height = Number(constraint.maxHeight);
    const childConstraint: ConstraintSizeOptions = {
      minWidth: width, minHeight: height, maxWidth: constraint.maxWidth, maxHeight: constraint.maxHeight
    };
    for (let child of children) {
      const result = child.measure(childConstraint);
      width = Math.max(width, result.width);
      height = Math.max(height, result.height);
    }
    return { width: width, height: height };
  }

  onPlaceChildren(info: GeometryInfo, children: Array<Layoutable>, constraint: ConstraintSizeOptions): void {
    for (let child of children) {
      child.layout({ x: 0, y: 0 });
    }
  }

  build() {
    if (this.column) {
      Column() {
        this.content()
      }
    } else {
      this.content()
    }
  }
}
""".trimIndent().lines()
