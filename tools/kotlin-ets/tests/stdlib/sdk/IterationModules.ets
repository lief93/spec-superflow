import { transfer, continuedCursor, nullableTransfer, rangeTransfer } from '../generated/IteratorBridge';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(transfer(4, 7).toString())
      Text(continuedCursor().toString())
      Text((nullableTransfer(9) ?? 0).toString())
      Text(rangeTransfer(-2147483648, 2147483647).toString())
    }
  }
}
