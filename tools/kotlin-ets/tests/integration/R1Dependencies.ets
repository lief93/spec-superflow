import { dispatch, abstractDispatch, constructorEffects } from '../generated/Inheritance';
import { crossFileNullable, crossFileStrings } from '../generated/QuantifierCases';
import { safeLength, choose } from '../generated/NullEquality';
import { scenario as sameFacade } from '../generated/same';
import { scenario as crossFacade } from '../generated/cross-facade';
import { scenario as secondJar } from '../generated/second-jar';

@Entry
@Component
struct R1Dependencies {
  build() {
    Column() {
      Text(dispatch(2).toString())
      Text(abstractDispatch(2).toString())
      Text(constructorEffects(2).toString())
      Text(crossFileNullable([null, 1, null]).toString())
      Text(crossFileStrings(['go', 'stop', 'later']).toString())
      Text(safeLength('letters').toString())
      Text(choose(null, 7).toString())
      Text(sameFacade(2))
      Text(crossFacade(2))
      Text(secondJar(2))
    }
  }
}
