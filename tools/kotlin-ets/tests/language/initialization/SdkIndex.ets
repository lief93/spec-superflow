import { before, methodFirst, propertyFirst, writeFirst, defaultFirst, legacyInitializer,
  readFailure, readOuterFailure } from '../modules/Consumer';

@Entry
@Component
struct Index {
  @State result: string = '';

  aboutToAppear(): void {
    this.result = before() + methodFirst() + propertyFirst() + writeFirst(3) + defaultFirst() + legacyInitializer();
    try {
      readFailure();
    } catch (error) {
      this.result += (error as Error).name;
    }
    try {
      readOuterFailure();
    } catch (error) {
      this.result += (error as Error).name;
    }
  }

  build() {
    Text(this.result)
  }
}
