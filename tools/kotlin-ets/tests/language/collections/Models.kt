package collectioncases

data class Key(val id: Int, val name: String)
class Collision(val id: Int) {
    override fun hashCode(): Int = 7
    override fun equals(other: Any?): Boolean = other is Collision && id == other.id
}
class Identity
enum class Stage { FIRST, LAST }
