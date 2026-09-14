import { AbilityConstant, ConfigurationConstant, UIAbility, Want } from '@kit.AbilityKit';
import { display, window } from '@kit.ArkUI';
import { hilog } from '@kit.PerformanceAnalysisKit';

export default class EntryAbility extends UIAbility {
  onCreate(_want: Want, _launchParam: AbilityConstant.LaunchParam): void {
    hilog.info(0, 'SliceIdentity', '%{public}s', '__GENERATED_SHA256__');
    const application = this.context.getApplicationContext();
    application.setLanguage('en-US');
    application.setFontSizeScale(1);
    application.setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_LIGHT);
  }

  async onWindowStageCreate(stage: window.WindowStage): Promise<void> {
    const mainWindow = stage.getMainWindowSync();
    await mainWindow.setWindowLayoutFullScreen(true);
    await mainWindow.setWindowSystemBarEnable([]);
    await stage.loadContent('pages/Index');
    setTimeout(() => {
      hilog.info(0, 'SliceEnvironment', '%{public}s', JSON.stringify({
        config: this.context.config,
        resource: this.context.resourceManager.getConfigurationSync(),
        density: display.getDefaultDisplaySync().densityPixels,
        insetPolicy: 'fullscreen-hidden-system-bars',
        window: mainWindow.getWindowProperties().windowRect
      }));
    }, 800);
  }
}
