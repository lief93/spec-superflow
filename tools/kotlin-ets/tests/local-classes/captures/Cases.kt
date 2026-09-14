package capturefixture

fun immutableCase(seed: Int): String {
    class View(val offset: Int) {
        val initial = seed + offset
        fun read(): Int = seed + offset + initial
    }
    val first = View(1)
    val second = View(2)
    return "${first.read()}|${second.read()}|${first.read()}"
}

fun makeShared(seed: Int): () -> String {
    var state = seed
    class Counter(val step: Int) {
        fun next(): Int {
            state += step
            return state
        }
        fun read(): Int = state
    }
    val first = Counter(1)
    val second = Counter(2)
    val bump = { state += 10 }
    return {
        val a = first.next()
        bump()
        val b = second.next()
        "$a|$b|${first.read()}|$state"
    }
}

fun sharedCase(seed: Int): String {
    val first = makeShared(seed)
    val second = makeShared(seed + 100)
    return "${first()} / ${first()} / ${second()} / ${first()}"
}

fun objectCase(seed: Int): String {
    val model = Model(seed)
    class Reader(val offset: Int) {
        fun read(): Int = model.value + offset
        fun write(value: Int) { model.value = value }
    }
    val first = Reader(1)
    val second = Reader(2)
    val before = first.read()
    second.write(seed + 10)
    return "$before|${first.read()}|${second.read()}|${model.value}"
}

fun replacedObjectCase(seed: Int): String {
    var model = Model(seed)
    class Handle {
        fun read(): Int = model.value
    }
    val handle = Handle()
    val before = handle.read()
    model = Model(seed + 1)
    return "$before|${handle.read()}"
}

fun defaultCase(seed: Int): String {
    val trace = Trace()
    class Defaulted(val first: Int = trace.mark("D", seed), val second: Int = trace.mark("E", seed + 1)) {
        init { trace.mark("I", first + second) }
        fun read(): String = "$seed:$first:$second:${trace.log}"
    }
    val named = Defaulted(second = trace.mark("B", seed + 2), first = trace.mark("A", seed + 1))
    val a = named.read()
    val defaults = Defaulted()
    val b = defaults.read()
    val partial = Defaulted(first = trace.mark("F", seed))
    return "$a|$b|${partial.read()}|${trace.log}"
}

fun collisionCase(seed: Int): String {
    class Collision(val `$seed`: Int, val `$seed_0`: Int) {
        fun read(): Int = seed + `$seed` + `$seed_0`
    }
    val first = Collision(2, 3)
    val second = Collision(4, 5)
    return "${first.read()}|${second.read()}|${first.`$seed`}|${first.`$seed_0`}"
}
