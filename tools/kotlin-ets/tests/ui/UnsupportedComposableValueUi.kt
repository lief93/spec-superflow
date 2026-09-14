package negative

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun VisibleSideEffect() { Text("Side effect") }

@Composable
fun getRawString(key: String): String {
    VisibleSideEffect()
    return key
}

@Composable
fun UnknownPage() { Text(getRawString("value")) }
