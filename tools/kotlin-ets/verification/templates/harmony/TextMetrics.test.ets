import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { describe, expect, it } from '@ohos/hypium';

export default function abilityTest() {
  describe('TextMetricsDiagnostic', () => {
    it('recordsNativeTypographyMetrics', 0, async () => {
      const driver = Driver.create();
      await abilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName: 'com.joker.kit', abilityName: 'EntryAbility'
      });
      await driver.delayMs(1200);
      for (const id of ['title-natural', 'title-line', 'title-half', 'chapter-half',
        'body-half', 'body-line', 'button-half', 'button-line',
        'title-measured', 'chapter-measured', 'body-measured']) {
        const component = await driver.findComponent(ON.id(id));
        expect(component !== null).assertTrue();
        const bounds = await component.getBounds();
        expect(bounds.right > bounds.left && bounds.bottom > bounds.top).assertTrue();
        hilog.info(0, 'TextMetricsProbe', '%{public}s', JSON.stringify({ id: id, bounds: bounds }));
      }
    });
  });
}
