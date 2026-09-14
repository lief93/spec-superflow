package extensionbinary

inline fun <reified Value : Any> Value.unsupported(): Boolean = this is String
