import { AbilityConstant, UIAbility, Want } from '@kit.AbilityKit';
import { window } from '@kit.ArkUI';
import { hilog } from '@kit.PerformanceAnalysisKit';

export default class EntryAbility extends UIAbility {
  onCreate(_want: Want, _launchParam: AbilityConstant.LaunchParam): void {
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    const mainWindow = windowStage.getMainWindowSync();
    mainWindow.setWindowLayoutFullScreen(true).catch(() => {});
    mainWindow.setWindowSystemBarEnable(['status', 'navigation']).catch(() => {});
    windowStage.loadContent('pages/Index', (error) => {
      if (error.code) {
        hilog.error(
          0x0000,
          'EntryAbility',
          'Failed to load content: %{public}s',
          JSON.stringify(error) ?? ''
        );
      }
    });
  }
}
