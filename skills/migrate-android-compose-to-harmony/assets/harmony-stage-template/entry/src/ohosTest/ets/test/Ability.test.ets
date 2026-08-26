import { Want } from '@kit.AbilityKit';
import { abilityDelegatorRegistry, Driver, ON } from '@kit.TestKit';
import { describe, expect, it } from '@ohos/hypium';

const MAIN_WANT: Want = {
  bundleName: '__BUNDLE_NAME__',
  moduleName: 'entry',
  abilityName: 'EntryAbility'
};

export default function abilityTest() {
  describe('MigrationSmokeUiTest', () => {
    it('launchesMigratedApplication', 0, async () => {
      const delegator = abilityDelegatorRegistry.getAbilityDelegator();
      const driver: Driver = Driver.create();
      await delegator.startAbility(MAIN_WANT);
      const title = await driver.waitForComponent(
        ON.text('__PROJECT_NAME__ migration ready'),
        8000
      );
      expect(title !== null && title !== undefined).assertTrue();
    });
  });
}
