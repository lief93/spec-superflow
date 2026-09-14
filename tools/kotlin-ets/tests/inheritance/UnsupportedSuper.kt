open class SuperBase { open fun read(): Int = 3 }
class SuperChild : SuperBase() { override fun read(): Int = super.read() + 1 }
