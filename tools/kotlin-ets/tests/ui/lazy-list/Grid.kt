package lazylist

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp

@Composable
fun FixedGrid() {
    LazyVerticalGrid(columns = GridCells.Fixed(2)) {
        item { Text("Header") }
        items(listOf("A", "B"), key = { it }) { label -> Text(label) }
    }
}

@Composable
fun AdaptiveGrid() {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(150.dp),
        contentPadding = PaddingValues(4.dp),
        userScrollEnabled = false,
    ) {
        items(listOf("A"), key = { it.length }) { label -> Text(label) }
    }
}

@Composable
fun UnsupportedGridArrangement() {
    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) { item { Text("A") } }
}
