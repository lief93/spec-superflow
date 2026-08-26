import { Component, Driver, ON } from '@kit.TestKit';

const COMPONENT_BOUNDS_SCHEMA: string = 'android-to-harmony.component-bounds.v1';
const SAFE_TOKEN: RegExp = /^[A-Za-z0-9._:/#@-]{1,120}$/;

export interface ComponentBoundsDescriptor {
  id: string;
  semanticKey: string;
}

export interface ScreenshotDimensions {
  width: number;
  height: number;
}

export interface ComponentBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ComponentBoundsEntry {
  id: string;
  type: string;
  semantic_key: string;
  bounds: ComponentBounds;
}

export interface ComponentBoundsInventory {
  schema: string;
  screenshot_dimensions: ScreenshotDimensions;
  components: ComponentBoundsEntry[];
}

function isSafeToken(value: string): boolean {
  return SAFE_TOKEN.test(value);
}

export async function collectComponentBounds(driver: Driver,
  descriptors: ComponentBoundsDescriptor[]): Promise<ComponentBoundsInventory> {
  const displaySize = await driver.getDisplaySize();
  const displayWidth: number = Math.floor(displaySize.x);
  const displayHeight: number = Math.floor(displaySize.y);
  const components: ComponentBoundsEntry[] = [];

  for (const descriptor of descriptors) {
    if (!isSafeToken(descriptor.id) || !isSafeToken(descriptor.semanticKey)) {
      continue;
    }
    try {
      const component: Component = await driver.findComponent(ON.id(descriptor.id));
      if (component === null || component === undefined) {
        continue;
      }
      const componentType: string = await component.getType();
      if (!isSafeToken(componentType)) {
        continue;
      }
      const rect = await component.getBounds();
      const left: number = Math.max(0, Math.floor(rect.left));
      const top: number = Math.max(0, Math.floor(rect.top));
      const right: number = Math.min(displayWidth, Math.ceil(rect.right));
      const bottom: number = Math.min(displayHeight, Math.ceil(rect.bottom));
      if (left >= right || top >= bottom) {
        continue;
      }
      components.push({
        id: descriptor.id,
        type: componentType,
        semantic_key: descriptor.semanticKey,
        bounds: {
          x: left,
          y: top,
          width: right - left,
          height: bottom - top
        }
      });
    } catch (_) {
      // Missing, destroyed, or invisible components are not part of this screenshot inventory.
    }
  }

  return {
    schema: COMPONENT_BOUNDS_SCHEMA,
    screenshot_dimensions: {
      width: displayWidth,
      height: displayHeight
    },
    components: components
  };
}
