import { interfaceCase, inheritedCase, substitutionsCase, constraintsCase,
  boundedCase, effectsCase } from '../generated/r2c/GenericMethods';
import { genericMethodSdkCheck } from '../generated/r2c/SdkConsumer';
import { scenario as combined } from '../generated/r2c/combined';
import { scenario as secondJar } from '../generated/r2c/second-jar';

@Entry
@Component
struct R2MethodDependencies {
  build() {
    Column() {
      Text(interfaceCase(2))
      Text(inheritedCase(2))
      Text(substitutionsCase(2))
      Text(constraintsCase(2))
      Text(boundedCase(2))
      Text(effectsCase(2))
      Text(genericMethodSdkCheck().toString())
      Text(combined(2))
      Text(secondJar(2))
    }
  }
}
