import { construct, nativeRoot } from '../modules/Application';
import { dispatchRoots, dispatchInheritance, dispatchGeneric, dispatchDefaults, dispatchEarly } from '../modules/Dispatch';
import { protectedConstruction } from '../modules/Visibility';

@Entry
@Component
struct Index {
  build() {
    Text(construct(7) + nativeRoot(7) + dispatchRoots(7) + dispatchInheritance(7) +
      dispatchGeneric(7) + dispatchDefaults(7) + dispatchEarly(7) + protectedConstruction(7))
  }
}
