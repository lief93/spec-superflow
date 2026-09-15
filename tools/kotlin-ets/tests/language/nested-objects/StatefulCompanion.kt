package nestedobjects

var count = 0
class Owner {
    companion object {
        val seed = initialize()
    }
}
fun initialize(): Int { count += 1; return count }
fun checkInitialization(): Int { Owner(); return count }
