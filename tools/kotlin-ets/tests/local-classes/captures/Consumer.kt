package capturefixture

fun cases(seed: Int): String =
    "${immutableCase(seed)}\n${sharedCase(seed)}\n${objectCase(seed)}\n${replacedObjectCase(seed)}\n${defaultCase(seed)}\n${collisionCase(seed)}"
