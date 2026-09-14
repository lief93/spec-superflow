interface CheckedInterface { fun read(): Int }
fun isChecked(value: Any): Boolean = value is CheckedInterface
