import { genericDispatch, parameterized, nestedArguments, stringDispatch,
  constructorEffects, genericCaller, migratedGeneric } from '../generated/r2/GenericHeritage';
import { primitiveTransfer, stringTransfer, objectTransfer, boxedTransfer,
  nullableTransfer, arrayReplacement, sourceUnmodified } from '../generated/r2/GenericCases';
import { scenario as combined } from '../generated/r2/combined';
import { scenario as secondJar } from '../generated/r2/second-jar';

@Entry
@Component
struct R2Dependencies {
  build() {
    Column() {
      Text(genericDispatch(2))
      Text(parameterized(2).toString())
      Text(nestedArguments(2).toString())
      Text(stringDispatch(2))
      Text(constructorEffects(2))
      Text(genericCaller(2).toString())
      Text(migratedGeneric().toString())
      Text(primitiveTransfer(2, 3).toString())
      Text(stringTransfer(12, 34))
      Text(objectTransfer(2, 3).toString())
      Text(boxedTransfer(2).toString())
      Text((nullableTransfer(2) ?? 0).toString())
      Text(arrayReplacement(2, 3).toString())
      Text(sourceUnmodified().toString())
      Text(combined(2))
      Text(secondJar(2))
    }
  }
}
