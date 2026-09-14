import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { describe, expect, it } from '@ohos/hypium';

export default function abilityTest() {
  describe('MaterialTextDiagnostic', () => {
    it('appliesMaterialTextContexts', 0, async () => {
      const driver = Driver.create();
      await abilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName: 'com.joker.kit', abilityName: 'EntryAbility'
      });
      await driver.delayMs(1200);
      const labels: string[] = ['Body', 'Large body', 'Wrapped label', 'Explicit label', 'Body restored'];
      const heights: number[] = [84, 100, 70, 70, 84];
      for (let i = 0; i < labels.length; i++) {
        const component = await driver.findComponent(ON.text(labels[i]));
        expect(component !== null).assertTrue();
        const bounds = await component.getBounds();
        hilog.info(0, 'MaterialTextBounds', '%{public}s', JSON.stringify({ text: labels[i], bounds: bounds }));
        expect(Math.abs(bounds.bottom - bounds.top - heights[i]) <= 3.5).assertTrue();
      }
    });
  });
}
