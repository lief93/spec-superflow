interface MemberGeneric<T> { fun <U> select(value: U): U }
class MemberGenericText : MemberGeneric<String> {
    override fun <U> select(value: U): U = value
}
