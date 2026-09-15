package fieldvalues
import fieldapi.Api
class Source(var value: Int)
fun value(): Int { val source = Source(3); source.value = 4; return Api.value + source.value }
fun wrong(): Int = Api.wrong
fun effect(): Int = Api.effect
fun unclaimed(): Int = Api.unclaimed
fun write() { Api.value = 3 }
