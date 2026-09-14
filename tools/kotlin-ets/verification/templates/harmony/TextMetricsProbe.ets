// SDK typography diagnostic only, never generated-translation acceptance.
import measure from '@ohos.measure';
import drawing from '@ohos.graphics.drawing';
import { hilog } from '@kit.PerformanceAnalysisKit';

@Entry
@Component
struct TextMetricsProbe {
  aboutToAppear(): void {
    for (const size of [24, 20, 16]) {
      const measured = measure.measureTextSize({ textContent: 'Hg', fontSize: size + 'fp', fontWeight: 400 });
      const font = new drawing.Font();
      font.setSize(fp2px(size));
      hilog.info(0, 'NativeFontMetrics', '%{public}s', JSON.stringify({ size: size,
        measured: measured, drawing: font.getMetrics() }));
    }
  }

  naturalLine(size: number, requested: number): number {
    const measured = measure.measureTextSize({ textContent: 'Hg', fontSize: size + 'fp', fontWeight: 400 });
    return Math.max(requested, px2vp(Number(measured.height)));
  }

  build() {
    Column() {
      Text('Field Notes').fontSize(24).id('title-natural')
      Text('Field Notes').fontSize(24).lineHeight(24).id('title-line')
      Text('Field Notes').fontSize(24).lineHeight(24).halfLeading(true).id('title-half')
      Text('Chapter 1').fontSize(20).lineHeight(24).halfLeading(true).id('chapter-half')
      Text('Page 1 of 4').fontSize(16).lineHeight(24).halfLeading(true).id('body-half')
      Text('Page 1 of 4').fontSize(16).lineHeight(24).id('body-line')
      Text('Continue').fontSize(16).lineHeight(20).halfLeading(true).id('button-half')
      Text('Continue').fontSize(16).lineHeight(20).id('button-line')
      Text('Field Notes').fontSize(24).lineHeight(this.naturalLine(24, 24)).halfLeading(true).id('title-measured')
      Text('Chapter 1').fontSize(20).lineHeight(this.naturalLine(20, 24)).halfLeading(true).id('chapter-measured')
      Text('Page 1 of 4').fontSize(16).lineHeight(this.naturalLine(16, 24)).halfLeading(true).id('body-measured')
    }.alignItems(HorizontalAlign.Start).width('100%').height('100%')
  }
}
