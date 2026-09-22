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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.launch

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

@Composable
fun NegativeProgrammaticLazyListIndex() {
    val state = rememberLazyListState()
    val scope = rememberCoroutineScope()
    Button(onClick = { scope.launch { state.scrollToItem(-1) } }) {
        Text("Scroll")
    }
    LazyColumn(state = state) { item { Text("A") } }
}

@Composable
fun UnsupportedLazyListLaunchShape() {
    val state = rememberLazyListState()
    val scope = rememberCoroutineScope()
    Button(onClick = { scope.launch(start = CoroutineStart.LAZY) { state.animateScrollToItem(2) } }) {
        Text("Scroll")
    }
    LazyColumn(state = state) { item { Text("A") } }
}

suspend fun MissingProgrammaticLazyListBinding(state: LazyListState) {
    state.scrollToItem(1)
}
