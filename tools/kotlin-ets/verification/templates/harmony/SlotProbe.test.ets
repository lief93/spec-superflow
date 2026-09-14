import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { describe, expect, it } from '@ohos/hypium';

export default function abilityTest() {
  describe('WrappedBuilderLayoutProbe', () => {
    it('preservesCallerColumnAndRow', 0, async () => {
      const driver = Driver.create();
      await abilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName: 'com.joker.kit', abilityName: 'EntryAbility'
      });
      await driver.delayMs(1200);
      const names: string[] = ['before', 'one', 'two', 'after'];
      const columnFirst = await driver.findComponent(ON.id('column-before'));
      const rowFirst = await driver.findComponent(ON.id('row-before'));
      expect(columnFirst !== null && rowFirst !== null).assertTrue();
      const origin = await columnFirst.getBounds();
      const rowOrigin = await rowFirst.getBounds();
      expect(rowOrigin.top - origin.top).assertEqual(280);
      for (let index = 0; index < names.length; index++) {
        const column = await driver.findComponent(ON.id('column-' + names[index]));
        const row = await driver.findComponent(ON.id('row-' + names[index]));
        expect(column !== null && row !== null).assertTrue();
        const a = await column.getBounds();
        const b = await row.getBounds();
        hilog.info(0, 'SlotProbeBounds', '%{public}s', JSON.stringify({ name: names[index], column: a, row: b }));
        expect(a.right - a.left).assertEqual(140);
        expect(a.bottom - a.top).assertEqual(70);
        expect(b.right - b.left).assertEqual(140);
        expect(b.bottom - b.top).assertEqual(70);
        expect(a.left).assertEqual(origin.left);
        expect(a.top - origin.top).assertEqual(index * 70);
        expect(b.left - rowOrigin.left).assertEqual(index * 140);
        expect(b.top).assertEqual(rowOrigin.top);
      }
    });
  });
}
