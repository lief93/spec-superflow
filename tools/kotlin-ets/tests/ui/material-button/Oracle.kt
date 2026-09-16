package materialbutton
import androidx.compose.ui.unit.LayoutDirection
fun main() {
    observations().forEach(::println)
    count = 0
    val edge = edges()
    println(edge.calculateLeftPadding(LayoutDirection.Ltr).value.toInt())
    println(edge.calculateTopPadding().value.toInt())
    println(edge.calculateRightPadding(LayoutDirection.Ltr).value.toInt())
    println(edge.calculateBottomPadding().value.toInt())
    println(count)
    println(uniform().calculateTopPadding().value.toInt())
    println(count)
}
