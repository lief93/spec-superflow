package declarationvariance

fun main() {
    for (seed in intArrayOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(covariance(seed))
        println(contravariance(seed))
        println(nested(seed))
        println(property(seed))
        println(mixed(seed))
        println(nullable(seed))
        println(broadBound(seed))
        println(narrowBound(seed))
        println(classBound(seed))
        println(nominalBound(seed))
        println(independent(seed))
        println(independentGeneric(seed))
        println(independentClass(seed))
        println(independentSelf(seed))
        println(independentChain(seed))
        println(independentDiamond(seed))
        println(originalMultiple(seed))
        println(classInterface(seed))
        println(interfaceClass(seed))
        println(classInterfaceReturn(seed))
        println(classInterfaceHolder(seed))
        println(classInterfaceMutation(seed))
    }
}
