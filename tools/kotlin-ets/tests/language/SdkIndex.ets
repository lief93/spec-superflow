import { languageSlice } from '../language/LanguageSlice';
import { dataSlice, describe, checked, safe, Named, namedLabel } from '../language/DataSlice';
import { scopeSlice } from '../language/ScopeSlice';
import { controlSlice } from '../language/ControlSlice';
import { singletonSlice, singletonInitCount } from '../language/SingletonSlice';
import { accessorSlice } from '../language/AccessorSlice';
import { orderedConcatenation } from '../language/Concatenation';
import { localsScenario } from '../language/LocalFunctions';
import { localCases } from '../language/LocalGeneric';
import { stepped, capturedIterations } from '../language/Loops';
import { traceFilter } from '../language/Filter';

@Entry
@Component
struct Index {
  private result: string = '';

  aboutToAppear(): void {
    this.result = languageSlice() + dataSlice() + describe('text') + checked('text') +
      safe('text') + namedLabel(new Named('x')) + scopeSlice().toString() +
      controlSlice().toString() + singletonInitCount().toString() + singletonSlice().toString() +
      accessorSlice(5, 4) + orderedConcatenation(7) + localsScenario(5) + localCases(5) +
      stepped(1, 7, 2) + capturedIterations(0, 3) + traceFilter([-1, 0, 2], false, true);
  }

  build() {
    Column() {
      Text(this.result)
    }
  }
}
