@file:OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
package widgetlazy

import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun StickyHeaderList() {
    LazyColumn { stickyHeader { Text("Header") } }
}

@Composable
fun ContentTypeList() {
    LazyColumn { items(listOf("A"), contentType = { "row" }) { Text(it) } }
}

@Composable
fun StatefulList() {
    val state = rememberLazyListState()
    LazyColumn(state = state) { item { Text("A") } }
}

@Composable
fun ReverseList() {
    LazyColumn(reverseLayout = true) { item { Text("A") } }
}

@Composable
fun UnstableKeyList() {
    LazyColumn { items(listOf("A"), key = { it == "A" }) { Text(it) } }
}

@Composable
fun AnimatedItemList() {
    LazyColumn { item { Text("A", Modifier.animateItem()) } }
}

@Composable
fun LazyGrid() {
    LazyVerticalGrid(columns = GridCells.Fixed(2)) { item { Text("A") } }
}
