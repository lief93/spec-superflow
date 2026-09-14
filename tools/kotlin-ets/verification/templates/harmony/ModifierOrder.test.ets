import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { describe, expect, it } from '@ohos/hypium';

export default function abilityTest() {
  describe('ModifierOrderNative', () => {
    it('modifierGeometryAndBoundary', 0, async () => {
      const driver = Driver.create();
      await abilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName: 'com.joker.kit', abilityName: 'EntryAbility'
      });
      await driver.delayMs(1500);
      const outer = await driver.findComponent(ON.id('outer-hit'));
      const inner = await driver.findComponent(ON.id('inner-hit'));
      expect(outer !== null && inner !== null).assertTrue();
      const a = await outer.getBounds();
      const b = await inner.getBounds();
      hilog.info(0, 'ModifierGeometry', '%{public}s', JSON.stringify({ outer: a, inner: b }));
      expect(a.right - a.left).assertEqual(98);
      expect(a.bottom - a.top).assertEqual(56);
      expect(b.right - b.left).assertEqual(70);
      expect(b.bottom - b.top).assertEqual(28);
      await driver.click(a.left + 7, (a.top + a.bottom) / 2);
      await driver.delayMs(600);
      expect(await driver.findComponent(ON.text('Hits 1')) !== null).assertTrue();
      await driver.click(b.left - 7, (b.top + b.bottom) / 2);
      await driver.delayMs(600);
      // The actual Compose instrumentation oracle expands this isolated inner
      // touch target and reports Hits 2 for the padding-ring probe.
      expect(await driver.findComponent(ON.text('Hits 2')) !== null).assertTrue();
      await driver.click((b.left + b.right) / 2, (b.top + b.bottom) / 2);
      await driver.delayMs(600);
      expect(await driver.findComponent(ON.text('Hits 3')) !== null).assertTrue();
    });
  });
}
