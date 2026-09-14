import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { describe, expect, it } from '@ohos/hypium';

// Expected values are the explicit Page.kt first-slice requirements.
export default function abilityTest() {
  describe('IndependentKotlinEts', () => {
    it('fourPagesBackAndCallback', 0, async () => {
      const delegator = abilityDelegatorRegistry.getAbilityDelegator();
      const driver = Driver.create();
      await delegator.startAbility({ bundleName: 'com.joker.kit', abilityName: 'EntryAbility' });
      const details: string[] = ['Observe the world around you.', 'Collect one small discovery.',
        'Connect it with a new idea.', 'Take your next step.'];
      const state = async (page: number, count: number): Promise<void> => {
        await driver.delayMs(1200);
        expect(await driver.waitForComponent(ON.text('Chapter ' + (page + 1)), 8000) !== null).assertTrue();
        expect(await driver.findComponent(ON.text(details[page])) !== null).assertTrue();
        expect(await driver.findComponent(ON.text('Page ' + (page + 1) + ' of 4')) !== null).assertTrue();
        expect(await driver.findComponent(ON.text('Callback ' + count)) !== null).assertTrue();
        expect(await driver.findComponent(ON.text(page === 3 ? 'Finish' : 'Continue')) !== null).assertTrue();
        const pager = await driver.findComponent(ON.id('pager'));
        const action = await driver.findComponent(ON.id('action-button'));
        expect(pager !== null && action !== null).assertTrue();
        const pagerBounds = await pager.getBounds();
        const actionBounds = await action.getBounds();
        expect(pagerBounds.bottom - pagerBounds.top).assertEqual(840);
        expect(actionBounds.bottom - actionBounds.top).assertEqual(168);
        expect(actionBounds.top > pagerBounds.bottom).assertTrue();
        for (let index = 0; index < 4; index++) {
          const indicator = await driver.findComponent(ON.id('indicator-' + index));
          expect(indicator !== null).assertTrue();
          const bounds = await indicator.getBounds();
          expect(bounds.right - bounds.left).assertEqual(70);
          expect(bounds.bottom - bounds.top).assertEqual(28);
          expect(bounds.top >= pagerBounds.bottom && bounds.bottom <= actionBounds.top).assertTrue();
        }
      };
      const swipe = async (back: boolean): Promise<void> => {
        const pager = await driver.findComponent(ON.id('pager'));
        expect(pager !== null).assertTrue();
        const b = await pager.getBounds();
        const y = Math.round((b.top + b.bottom) / 2);
        const left = Math.round(b.left + (b.right - b.left) * 0.18);
        const right = Math.round(b.left + (b.right - b.left) * 0.82);
        await driver.swipe(back ? left : right, y, back ? right : left, y, 1000);
      };
      await state(0, 0);
      for (let page = 1; page <= 3; page++) {
        await swipe(false);
        await state(page, 0);
      }
      await swipe(true);
      await state(2, 0);
      const button = await driver.findComponent(ON.id('action-button'));
      expect(button !== null).assertTrue();
      await button.click();
      await state(3, 1);
    });
  });
}
