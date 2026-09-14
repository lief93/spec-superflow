import { Dashboard } from '../modules/Dashboard';
import { LabelModel } from '../modules/Model';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Dashboard(new LabelModel())
    }
  }
}
