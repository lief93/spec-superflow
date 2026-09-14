import { arityCase, numericCase, memberCase, genericCase,
  classGenericCase, effectsCase } from '../generated/r2d/Overloads';
import { overloadSdkCheck } from '../generated/r2d/SdkConsumer';
import { scenario as combined } from '../generated/r2d/combined';
import { scenario as split } from '../generated/r2d/split';
import { scenario as reversed } from '../generated/r2d/reversed';

@Entry
@Component
struct R2OverloadDependencies {
  build() {
    Column() {
      Text(arityCase(2))
      Text(numericCase(2))
      Text(memberCase(2))
      Text(genericCase(2))
      Text(classGenericCase(2))
      Text(effectsCase(2))
      Text(overloadSdkCheck().toString())
      Text(combined(1))
      Text(split(1))
      Text(reversed(1))
    }
  }
}
