import { TokenModel } from '../modules/TokenModel';
import { ModelHolder } from '../modules/ModelHolder';
import { TextHolder } from '../modules/TextHolder';
import { Middle } from '../modules/Middle';
import { ReaderBox } from '../modules/ReaderBox';
import { readClass, readInterface, readParametric, readChain } from '../modules/BoundedCalls';
import { acceptClass, acceptInterface } from '../modules/Signatures';

@Entry
@Component
struct Index {
  private reader: ModelHolder = new ModelHolder(new TokenModel('bounded model'));

  aboutToAppear(): void {
    acceptClass<ModelHolder>(this.reader);
    acceptInterface<ModelHolder>(this.reader);
  }

  build() {
    Column() {
      Text(readClass<ModelHolder>(this.reader).text)
      Text(readInterface<ModelHolder>(this.reader).text)
      Text(readParametric<TokenModel, ModelHolder>(this.reader).text)
      Text(readChain<Middle<TokenModel>, ModelHolder>(this.reader).text)
      Text(new ReaderBox<ModelHolder>(this.reader).read().text)
      Text(readParametric<string, TextHolder>(new TextHolder('bounded text')))
      Text(readParametric<number, Middle<number>>(new Middle<number>(7)).toString())
    }
  }
}
