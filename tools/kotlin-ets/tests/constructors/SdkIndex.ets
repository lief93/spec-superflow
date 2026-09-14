import { construct, nativeRoot } from '../modules/Application';
import { dispatchRoots, dispatchInheritance, dispatchGeneric, dispatchDefaults, dispatchEarly } from '../modules/Dispatch';

@Entry
@Component
struct Index {
  build() {
    Text(construct(7) + nativeRoot(7) + dispatchRoots(7) + dispatchInheritance(7) +
      dispatchGeneric(7) + dispatchDefaults(7) + dispatchEarly(7))
  }
}
