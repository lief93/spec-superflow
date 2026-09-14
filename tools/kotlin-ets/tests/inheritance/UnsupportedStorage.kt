open class StorageBase(private val value: Int) { fun read(): Int = value }
class StorageChild(private val value: Int) : StorageBase(1)
