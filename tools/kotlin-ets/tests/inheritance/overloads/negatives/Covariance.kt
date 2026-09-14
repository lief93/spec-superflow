open class Animal
class Dog : Animal()
open class Factory {
    open fun make(value: Int): Animal = Animal()
    open fun make(value: String): Animal = Animal()
}
class Dogs : Factory() { override fun make(value: Int): Dog = Dog() }
