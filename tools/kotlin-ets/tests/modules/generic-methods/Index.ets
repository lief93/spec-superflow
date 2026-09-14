import { TokenModel } from '../modules/TokenModel';
import { Holder } from '../modules/Holder';
import { MethodBase } from '../modules/MethodBase';
import { MethodDerived } from '../modules/MethodDerived';
import { callDirect, callBase, callInterface, callRead, callChain, callBounded, callInherited, callAccept } from '../modules/MethodCalls';
import { callTypeOnly } from '../modules/TypeCalls';

@Entry
@Component
struct Index {
  private model: TokenModel = new TokenModel('generic methods');
  private service: MethodDerived = new MethodDerived();
  private reader: Holder<TokenModel> = new Holder<TokenModel>(this.model);

  aboutToAppear(): void {
    callAccept(this.service, this.reader);
    callTypeOnly(new MethodBase<number>());
  }

  build() {
    Column() {
      Text(callDirect(this.service, this.model, 'direct'))
      Text(callBase(this.service, this.model, 7).toString())
      Text(callInterface(this.service, this.model, this.model).text)
      Text(callRead(this.service, this.reader).text)
      Text(callChain(this.service, this.reader).text)
      Text(callBounded<TokenModel, MethodDerived>(this.service, this.model, 9).toString())
      Text(callInherited(this.service, this.model).text)
    }
  }
}
