package captureconstruction

fun combined(seed: Int): String = localChain(seed) + "|" + localRoot(seed) + "|" +
    innerChain(seed) + "|" + innerRoot(seed) + "|" + initializer(seed) + "|" + collision(seed) + "|" + localDispatch(seed) +
    "|" + localPersistent(seed) + "|" + innerDispatch(seed) + "|" + capturedHeritage(seed) + "|" + capturedHeritageDispatch(seed)
