import { covariance, contravariance, nested, property, mixed, nullable } from '../modules/Cases';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(`${covariance(7)},${contravariance(7)},${nested(7)},${property(7)},${mixed(7)},${nullable(7)}`)
    }
  }
}
