package surfaceelevation

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.surfaceColorAtElevation
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

private var evaluationTrace = ""

fun elevated(surface: Color, surfaceTint: Color, elevation: Dp): Color =
    lightColorScheme(surface = surface, surfaceTint = surfaceTint).surfaceColorAtElevation(elevation)

fun resetEvaluationTrace() {
    evaluationTrace = ""
}

private fun tracedScheme(): ColorScheme {
    evaluationTrace += "receiver"
    return lightColorScheme(surface = Color(0x80402010), surfaceTint = Color(0xC0E08040))
}

private fun tracedElevation(): Dp {
    evaluationTrace += ":elevation"
    return 2.dp
}

fun orderedColor(): Color = tracedScheme().surfaceColorAtElevation(tracedElevation())

fun currentEvaluationTrace(): String = evaluationTrace
