import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { describe, expect, it } from '@ohos/hypium';

export default function abilityTest() {
  describe('SourceValuesNative', () => {
    it('evaluatesSourceInitializersOnce', 0, async () => {
      const driver = Driver.create();
      await abilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName: 'com.joker.kit', abilityName: 'EntryAbility'
      });
      await driver.delayMs(1500);
      const labels = await driver.findComponents(ON.text('Value 1'));
      expect(labels.length).assertEqual(2);
      expect(await driver.findComponent(ON.text('Count 2')) !== null).assertTrue();
      expect(await driver.findComponent(ON.text('Value 2')) === null).assertTrue();
      const first = await labels[0].getBounds();
      const second = await labels[1].getBounds();
      expect(first.bottom <= second.top || second.bottom <= first.top).assertTrue();
      await driver.delayMs(1200);
      expect((await driver.findComponents(ON.text('Value 1'))).length).assertEqual(2);
      expect(await driver.findComponent(ON.text('Count 2')) !== null).assertTrue();
    });
  });
}
