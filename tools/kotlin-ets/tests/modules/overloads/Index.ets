import { TokenModel } from '../modules/TokenModel';
import { OverloadMethods } from '../modules/OverloadMethods';
import { callFirst, callSecond, callText, callPair, callReserved, callUnchanged, callMemberNumber, callMemberText, callMemberPair, callMemberReserved, callStaticNumber, callStaticText, callRenderedNumber } from '../modules/OverloadCalls';

@Entry
@Component
struct Index {
  private model: TokenModel = new TokenModel('overloads');
  private service: OverloadMethods = new OverloadMethods();

  build() {
    Column() {
      Text(callFirst(7).toString())
      Text(callSecond(7).toString())
      Text(callText('text'))
      Text(callPair(2, 3).toString())
      Text(callReserved())
      Text(callUnchanged(this.model).text)
      Text(callMemberNumber(this.service, 9).toString())
      Text(callMemberText(this.service, 'member'))
      Text(callMemberPair(this.service, 3, 4).toString())
      Text(callMemberReserved(this.service))
      Text(callStaticNumber(11).toString())
      Text(callStaticText('static'))
      Text(callRenderedNumber(13).toString())
    }
  }
}
