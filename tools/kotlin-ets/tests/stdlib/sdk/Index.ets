import { arithmetic, interpolation } from '../generated/Scalars';
import { mapped, mutation } from '../generated/Lists';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(interpolation('stdlib', arithmetic(7, 3)))
      Text(mapped(10).toString())
      Text(mutation(17).toString())
    }
  }
}
