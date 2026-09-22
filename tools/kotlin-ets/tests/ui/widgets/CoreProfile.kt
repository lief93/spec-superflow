package widgetsfixture

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.painterResource

@Composable
fun CoreProfile(
    title: String,
    input: String,
    enabled: Boolean,
    onAction: () -> Unit,
    onInput: (String) -> Unit,
) {
    Column {
        Row {
            Text(title)
            Image(painterResource(R.drawable.logo), "Logo")
        }
        Box {
            Button(onClick = onAction, enabled = enabled) {
                Text("Open")
            }
        }
        TextField(value = input, onValueChange = onInput, enabled = enabled)
    }
}
