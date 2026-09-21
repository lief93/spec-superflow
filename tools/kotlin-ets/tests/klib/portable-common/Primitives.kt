package portablecommon

// Signature-only KLIB. These are the entire target-specific boundary.
external fun <T> newList(): MutableList<T>
external fun <T> append(values: MutableList<T>, value: T): Boolean
external fun exhausted(): Nothing
