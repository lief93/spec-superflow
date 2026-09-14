import { binaryScenario } from '../generated/Binary';
import { transfer, continuedCursor, nullableTransfer, rangeTransfer } from '../generated/IteratorBridge';
import { constructors, copiedArray, listCaptures, composed } from '../generated/LanguageIteration';
import { arrayFactory, listSum } from '../generated/LibraryIteration';

@Entry
@Component
struct Dependencies {
  build() {
    Column() {
      Text(binaryScenario(2))
      Text(transfer(4, 7).toString())
      Text(continuedCursor().toString())
      Text((nullableTransfer(9) ?? 0).toString())
      Text(rangeTransfer(-2147483648, 2147483647).toString())
      Text(constructors(2))
      Text(copiedArray<number>([1, 2]).length.toString())
      Text(listCaptures([1, 2]))
      Text(composed(1, 8, 2))
      Text(listSum(arrayFactory(2, 3)).toString())
    }
  }
}
