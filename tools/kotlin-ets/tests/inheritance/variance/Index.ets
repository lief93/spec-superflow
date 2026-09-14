import { covariance, contravariance, nested, property, mixed, nullable } from '../modules/Cases';
import { broadBound, narrowBound, classBound, nominalBound } from '../modules/Bounds';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(`${covariance(7)},${contravariance(7)},${nested(7)},${property(7)},${mixed(7)},${nullable(7)}`)
      Text(`${broadBound(7)},${narrowBound(7)},${classBound(7)},${nominalBound(7)}`)
    }
  }
}
