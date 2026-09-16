package staticanimation

import androidx.compose.animation.core.Animatable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp

@Composable fun StaticDots() {
    val circles = listOf(remember { Animatable(0f) }, remember { Animatable(0f) }, remember { Animatable(0f) })
    val values = circles.map { it.value }
    val distance = with(LocalDensity.current) { 20.dp.toPx() }
    circles.forEachIndexed { index, animation ->
        LaunchedEffect(animation) { animation.animateTo(index.toFloat()) }
    }
    Row {
        values.forEach { value ->
            Box(Modifier.size(24.dp).graphicsLayer { translationY = -value * distance }
                .background(Color.Red, CircleShape))
        }
    }
}

@Composable fun Page() {
    Column {
        Text("Before")
        StaticDots()
        Text("After")
    }
}

@Composable fun InitialValue() {
    val animation = remember { Animatable(0.5f) }
    Text(if (animation.value == 0.5f) "Initial half" else "Wrong initial value")
}

@Composable fun RequiredValue() {
    val animation = remember { Animatable(0f) }
    Text(if (animation.velocity > 0f) "Moving" else "Stopped")
}

@Composable fun MixedLoop() {
    val circles = listOf(remember { Animatable(0f) })
    circles.forEach { animation ->
        LaunchedEffect(animation) { animation.animateTo(1f) }
        Text("Retained")
    }
}
