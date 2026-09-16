package degradation

import android.os.Build
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.unit.dp

@Composable fun Page() {
    Column {
        Text("Before", softWrap = false, modifier = Modifier.width(160.dp).blur(2.dp).padding(8.dp))
        CircularProgressIndicator()
        SideEffect { System.getProperty("ignored-effect") }
        Text("After")
    }
}

@Composable fun RequiredValue() {
    Text("Before", modifier = Modifier.blur(2.dp))
    Text(Build.VERSION.SDK_INT.toString())
}

@Composable fun Clean() { Text("Clean") }

@Composable fun ClaimedFailure() { Text("Before", onTextLayout = {}) }
