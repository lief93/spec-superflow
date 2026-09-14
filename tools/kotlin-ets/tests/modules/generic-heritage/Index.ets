import { TokenModel } from '../modules/TokenModel';
import { ModelHolder } from '../modules/ModelHolder';
import { TextHolder } from '../modules/TextHolder';
import { Middle } from '../modules/Middle';
import { readDirect, readBase, readInterface, readGeneric, readText } from '../modules/Consumers';

@Entry
@Component
struct Index {
  private model: ModelHolder = new ModelHolder(new TokenModel('typed model'));

  build() {
    Column() {
      Text(readDirect(this.model).text)
      Text(readBase(this.model).text)
      Text(readInterface(this.model).text)
      Text(readGeneric<TokenModel>(this.model).text)
      Text(readText(new TextHolder('typed text')))
      Text(readGeneric<number>(new Middle<number>(7)).toString())
    }
  }
}
