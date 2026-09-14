import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { describe, expect, it } from '@ohos/hypium';

export default function abilityTest() {
  describe('TouchDispatchDiagnostic', () => {
    it('routesNearestAdjacentTargets', 0, async () => {
      const driver = Driver.create();
      await abilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName: 'com.joker.kit', abilityName: 'EntryAbility'
      });
      await driver.delayMs(1200);
      expect(await driver.findComponent(ON.text('Selected -1 Hits 0')) !== null).assertTrue();
      const xs: number[] = [62, 90, 118, 146, 103, 105, 106, 118];
      const selected: number[] = [0, 1, 2, 3, 1, 2, 2, 2];
      for (let i = 0; i < xs.length; i++) {
        await driver.click(Math.round(xs[i] * 3.5), 196);
        await driver.delayMs(500);
        expect(await driver.findComponent(ON.text('Selected ' + selected[i] + ' Hits ' + (i + 1))) !== null).assertTrue();
      }
    });
  });
}
