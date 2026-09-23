import { bodyFirst, constructedState, injectedBox, injectedState } from '../generated/Calls';

@Entry
@Component
struct Index {
  build() {
    Column() {
      Text(injectedState().label)
      Text(injectedBox().value.label)
      Text(constructedState().label)
      Text(bodyFirst().label)
    }
  }
}
