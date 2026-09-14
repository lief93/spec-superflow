@file:JvmName("ExtensionFacade")
@file:JvmMultifileClass
package extensionbinary

inline fun <Value : Any> Value.unsupported(action: (Value) -> Value): Value = action(this)
