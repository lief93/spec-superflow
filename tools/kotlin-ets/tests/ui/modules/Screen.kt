package multimodule

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun Page(seed: Int = 2) {
    Column {
        Text(label(Model(seed)))
    }
}
