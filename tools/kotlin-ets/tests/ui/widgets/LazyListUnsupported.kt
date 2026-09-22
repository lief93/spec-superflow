@file:OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
package widgetlazy

import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.material3.Text
import androidx.compose.material3.Button
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
fun InlineLazyListState() {
    LazyColumn(state = rememberLazyListState()) { item { Text("A") } }
}

@Composable
fun DynamicLazyListState(initial: Int = 1) {
    val state = rememberLazyListState(initialFirstVisibleItemIndex = initial)
    LazyColumn(state = state) { item { Text("A") } }
}

@Composable
fun NegativeLazyListOffset() {
    val state = rememberLazyListState(initialFirstVisibleItemScrollOffset = -1)
    LazyColumn(state = state) { item { Text("A") } }
}

@Composable
fun ObservedLazyListState(state: LazyListState) {
    LazyColumn(state = state) { item { Text("A") } }
}

@Composable
fun UnsupportedLazyListOffsetRead() {
    val state = rememberLazyListState()
    LazyColumn(state = state) { item { Text("${state.firstVisibleItemScrollOffset}") } }
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

private fun launchLazyScroll(block: suspend () -> Unit) = Unit

@Composable
fun ProgrammaticLazyListScroll() {
    val state = rememberLazyListState()
    Button(onClick = { launchLazyScroll { state.animateScrollToItem(2, 3) } }) {
        Text("Scroll")
    }
    LazyColumn(state = state) { item { Text("A") } }
}
