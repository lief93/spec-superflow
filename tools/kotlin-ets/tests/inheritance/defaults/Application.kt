package defaultfixture

fun defaults(seed: Int): String {
    val effects = Effects()
    val child = DefaultChild(effects, seed)
    val base: DefaultBase = child
    val first = effects.receiver(base).calculate(right = effects.number("A", seed))
    val second = child.calculate()
    val explicit = base.calculate(effects.number("L", 1), effects.number("Q", 2))
    val final = child.finalValue()
    return "$first:$second:$explicit:$final:${effects.trace}"
}

fun genericDefaults(seed: Int): String {
    val base: DefaultBase = DefaultChild(Effects(), seed)
    val strings: GenericDefaults<String> = StringDefaults()
    val abstract: AbstractDefaults = ConcreteDefaults()
    return "${base.choose(seed)}:${base.choose<String?>(null)}:${strings.choose()}:${strings.choose(fallback = "other")}:${abstract.calculate()}"
}

fun closureDefaults(seed: Int): String {
    val base: DefaultBase = DefaultChild(Effects(), seed)
    return "${base.apply(seed)}:${base.apply(seed) { it - 1 }}"
}

fun recursiveDefaults(seed: Int): String {
    val value: RecursiveDefaults = RecursiveChild()
    return "${value.calculate()}:${value.remaining}:${value.calculate(seed)}"
}

fun nullableDefaults(seed: Int): String {
    val value = NullableChild()
    return "${value.optional()}:${value.optional(null)}:${value.optional("provided")}"
}

fun bitwiseDefaults(seed: Int): String = "${seed.and(-1)}:${seed.and(Int.MIN_VALUE)}:${seed.and(0)}"

fun wideDefaults(seed: Int): String {
    val value = WideChild()
    return "${value.sum()}:${value.sum(p31 = seed)}:${value.sum(p30 = seed, p33 = 6)}"
}

fun <T : GenericDefaults<String>> boundedDefault(value: T): String = value.choose()

fun heritageDefaults(seed: Int): String {
    val value = GenericChild("value")
    val direct = StringDefaults()
    return "${value.choose()}:${direct.choose()}:${boundedDefault(direct)}"
}

fun namedEffects(seed: Int): String {
    val effects = Effects()
    val value = DefaultChild(effects, seed)
    val explicit = effects.receiver(value).calculate(right = effects.number("R", 1), left = effects.number("L", seed))
    val nullable = value.choose<String?>("provided", null)
    return "$explicit:$nullable:${effects.trace}:${`DefaultBase_calculate$default`(seed)}"
}
