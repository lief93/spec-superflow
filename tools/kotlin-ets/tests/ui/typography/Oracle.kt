package typography
fun main() {
    val t = defaults()
    listOf(t.displayLarge, t.displayMedium, t.displaySmall, t.headlineLarge, t.headlineMedium,
        t.headlineSmall, t.titleLarge, t.titleMedium, t.titleSmall, t.bodyLarge, t.bodyMedium,
        t.bodySmall, t.labelLarge, t.labelMedium, t.labelSmall).forEach {
        println(it.fontSize.value); println(it.lineHeight.value)
        println(it.fontWeight!!.weight); println(it.letterSpacing.value)
    }
    println(selected(customized()).fontSize.value)
}
