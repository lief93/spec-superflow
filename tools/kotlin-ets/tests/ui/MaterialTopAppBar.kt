@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package materialtopappbar

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp

@Composable
private fun MenuIcon(imageVector: ImageVector) {
    Icon(imageVector = imageVector, contentDescription = "Open navigation")
}

@Composable
fun MaterialTopAppBar(onMenu: () -> Unit = {}) {
    val menu = Icons.Filled.Menu
    TopAppBar(
        title = { Text("Statistics") },
        navigationIcon = {
            IconButton(onClick = onMenu) {
                MenuIcon(menu)
            }
        },
        actions = { Text("Action") },
        modifier = Modifier.fillMaxWidth(),
        expandedHeight = 72.dp,
    )
}

@Composable
fun UnsupportedMaterialIcon() {
    Icon(imageVector = Icons.Filled.Delete, contentDescription = "Delete")
}

@Composable
fun UnsupportedTopAppBarColors() {
    TopAppBar(
        title = { Text("Unsupported") },
        colors = TopAppBarDefaults.topAppBarColors(),
    )
}
