package themeprojection

import android.app.Activity
import android.os.Build
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.material3.Button
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView

fun androidPalette(): ColorScheme = error("Android-only fallback must not be linked")

private val StaticLightPalette = lightColorScheme(primary = androidx.compose.ui.graphics.Color(0xFF123456))
private val StaticDarkPalette = darkColorScheme(primary = androidx.compose.ui.graphics.Color(0xFF654321))

@Composable
fun AppAppearance(dark: Boolean, content: @Composable () -> Unit) {
    val colors = if (supportsDynamicTheming()) {
        val context = LocalContext.current
        if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
    } else androidPalette()
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect { (view.context as Activity).window.statusBarColor = 0 }
    }
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable fun Page() {
    val page = remember { mutableStateOf(0) }
    AppAppearance(false) {
        Column {
            Text("Preserved content", color = MaterialTheme.colorScheme.primary)
            if (page.value == 0) Text("First") else Text("Next")
            Button(onClick = { page.value = page.value + 1 }) { Text("Advance") }
        }
    }
}

@Composable fun SharedValue() {
    val sdk = Build.VERSION.SDK_INT
    val colors = if (sdk >= 31) dynamicLightColorScheme(LocalContext.current) else lightColorScheme()
    MaterialTheme(colorScheme = colors) { Text("Content") }
    Text(sdk.toString())
}

@Composable fun StaticFallback(dark: Boolean, content: @Composable () -> Unit) {
    val colors = when {
        supportsDynamicTheming() -> dynamicLightColorScheme(LocalContext.current)
        dark -> StaticDarkPalette
        else -> StaticLightPalette
    }
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable fun StaticFallbackPage() {
    StaticFallback(false) { Text("Static source palette", color = MaterialTheme.colorScheme.primary) }
}

@Composable fun RequiredCondition() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) Text("A") else Text("B")
}

@Composable fun BelowCondition() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) Text("Legacy") else Text("Fallback")
}

private var conditionChecks = 0
private fun effectfulCondition(): Boolean { conditionChecks += 1; return conditionChecks > 0 }

@Composable fun CombinedCondition() {
    if (effectfulCondition() && supportsDynamicTheming()) Text("A") else Text("B")
}

@Composable fun RequiredNoFallback() {
    if (supportsDynamicTheming()) Text("A")
}

@Composable fun ValueFallback() { Text(platformFallbackLabel()) }

@Composable fun Clean() { MaterialTheme { Text("Clean") } }

fun updateBusinessState(): Unit = Unit
@Composable fun BusinessEffect() {
    val colors = if (Build.VERSION.SDK_INT >= 31) dynamicLightColorScheme(LocalContext.current) else lightColorScheme()
    val view = LocalView.current
    SideEffect {
        (view.context as Activity).window.statusBarColor = 0
        updateBusinessState()
    }
    MaterialTheme(colorScheme = colors) { Text("Keep business state") }
}
