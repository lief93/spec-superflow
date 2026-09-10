export interface ProjectTextStyle {
  size: number;
  weight: number;
  foreground: ResourceColor;
  height: number;
}

export class ProjectTypography {
  // Example data only; replace this lookup with the project's Harmony style library.
  static getStyle(key: string): ProjectTextStyle {
    if (key === 'title') {
      return { size: 24, weight: 700, foreground: '#202124', height: 32 };
    }
    return { size: 18, weight: 400, foreground: '#333333', height: 26 };
  }

  static fontSize(key: string): number {
    return ProjectTypography.getStyle(key).size;
  }

  static fontWeight(key: string): number {
    return ProjectTypography.getStyle(key).weight;
  }

  static color(key: string): ResourceColor {
    return ProjectTypography.getStyle(key).foreground;
  }

  static lineHeight(key: string): number {
    return ProjectTypography.getStyle(key).height;
  }
}
