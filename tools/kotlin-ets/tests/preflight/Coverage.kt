package preflightfixture

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable
fun CoveragePage() {
    Column(modifier = Modifier.size(8.dp)) {
        Text(stringResource(1))
    }
}
