import { describe, entryLocalValue } from '../modules/Entry';
import { tail, numbersLocalValue } from '../modules/Numbers';
import { functionCases } from '../modules/Functions';
import { classCases } from '../modules/Classes';
import { localCases } from '../modules/LocalGeneric';
import { inlineSourceScenario, crossFileScenario } from '../modules/Inline';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(describe(41))
      Text(tail('modules'))
      Text(`${entryLocalValue(41)}:${numbersLocalValue(41)}`)
      Text(functionCases(3))
      Text(classCases(3))
      Text(localCases(3))
      Text(inlineSourceScenario(1))
      Text(`${crossFileScenario(3)}`)
    }
  }
}
