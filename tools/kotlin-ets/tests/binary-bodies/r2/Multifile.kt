@file:JvmName("GenericFacade")
@file:JvmMultifileClass
package genericbinary

inline fun <Value : Any> unsupported(value: Value, action: (Value) -> Value): Value = action(value)
