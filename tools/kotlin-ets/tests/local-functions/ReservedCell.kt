package localfixture

class __etsSharedCell<T>(var value: T)

fun reservedCell(): Int = __etsSharedCell(1).value
