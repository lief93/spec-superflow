package typecases

interface Named { val title: String; fun count(): Int }
interface Ranked : Named { fun rank(): Int }
open class Card(override val title: String) : Named {
    override fun count(): Int = title.length
    override fun toString(): String = title
}
class RankedCard(title: String) : Card(title), Ranked { override fun rank(): Int = 9 }
class Other
data class Holder(val card: Card?)
