import { covariance, contravariance, nested, property, mixed, nullable } from '../modules/Cases';
import { broadBound, narrowBound, classBound, nominalBound } from '../modules/Bounds';
import { independent, independentGeneric, independentClass, independentSelf, independentChain, independentDiamond, originalMultiple } from '../modules/Independent';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(`${covariance(7)},${contravariance(7)},${nested(7)},${property(7)},${mixed(7)},${nullable(7)}`)
      Text(`${broadBound(7)},${narrowBound(7)},${classBound(7)},${nominalBound(7)}`)
      Text(`${independent(7)},${independentGeneric(7)},${independentClass(7)},${independentSelf(7)},${independentChain(7)},${independentDiamond(7)},${originalMultiple(7)}`)
    }
  }
}
