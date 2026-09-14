package genericbinary

inline fun <reified Value> unsupported(value: Value): Boolean = value is String
