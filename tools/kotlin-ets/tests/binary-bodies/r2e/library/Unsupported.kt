package memberboundaries

class Stateful(val offset: Int) {
    inline fun apply(value: Int): Int = value + offset
}

open class OpenMember {
    inline fun apply(value: Int): Int = value + 1
}

class GenericMember<T> {
    inline fun apply(value: Int): Int = value + 1
}

class ReifiedMember {
    inline fun <reified T> apply(value: T): Boolean = value is String
}

class ConstructorMember {
    inline fun apply(value: Int): ConstructorMember = ConstructorMember()
}

class OrdinaryHelperMember {
    inline fun apply(value: Int): Int = helper(value)
    fun helper(value: Int): Int = value + 1
}
