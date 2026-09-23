import { scenario } from '../modules/Application';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(scenario(3))
    }
  }
}
