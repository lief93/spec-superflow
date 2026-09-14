package temporaries

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp

class Reading(val immutable: String, var mutable: String, var changes: Int) {
    fun mutate(): Int {
        mutable = "Changed"
        changes = changes + 1
        return 20
    }

    fun effectText(): String {
        changes = changes + 1
        return mutable
    }
}

@Composable
fun CompilerTemporaries() {
    val value = Reading("Fixed", "Before", 0)
    Column {
        Text(value.immutable, fontSize = 20.sp, color = Color.Black)
        Text(value.mutable, fontSize = value.mutate().sp, color = Color.Black)
        Text(value.effectText(), fontSize = 20.sp, color = Color.Black)
    }
}
