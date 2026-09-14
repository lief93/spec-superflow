import { interfaceCase, classCase, plainCase, ancestorCase, chainCase,
  identityCase, selfCase, orderCase } from '../generated/r2b/BoundedReceivers';
import { stringRead } from '../generated/r2b/BoundedCases';
import { scenario as combined } from '../generated/r2b/combined';
import { scenario as secondJar } from '../generated/r2b/second-jar';

@Entry
@Component
struct R2BoundedDependencies {
  build() {
    Column() {
      Text(interfaceCase(2).toString())
      Text(classCase(2).toString())
      Text(plainCase(2).toString())
      Text(ancestorCase(2).toString())
      Text(chainCase(2).toString())
      Text(identityCase(2).toString())
      Text(selfCase(2).toString())
      Text(orderCase(2))
      Text(stringRead('bounded'))
      Text(combined(2))
      Text(secondJar(2))
    }
  }
}
