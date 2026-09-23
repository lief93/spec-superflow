export function projectToken(key: string): boolean {
  return key.length > 0;
}

export function projectColor(key: string): number {
  return key === 'brand' ? 0xff336699 : 0xff000000;
}

export function projectFont(key: string): string {
  return key === 'headline' ? 'sans-serif' : 'serif';
}

export function projectDimension(key: string): number {
  return key === 'spacing' ? 16 : 0;
}

export function projectString(key: string): string {
  return key === 'welcome' ? 'Welcome' : key;
}

export function projectImage(key: string): Resource {
  return $r('app.media.project_input');
}

export function projectDependency(name: string): string {
  return name === 'clock' ? 'target-clock' : name;
}
