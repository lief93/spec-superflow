open class SuperDefault { open fun pick(value: Int = 1): Int = value }
class SuperChild : SuperDefault() {
    override fun pick(value: Int): Int = super.pick(value) + 1
}
