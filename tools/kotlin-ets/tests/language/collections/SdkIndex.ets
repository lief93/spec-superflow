import { observations } from '../modules/Application';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(observations().join('\n'))
    }
  }
}
