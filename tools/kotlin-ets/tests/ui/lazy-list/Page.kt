package lazylist

import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun Page() {
    val state = rememberLazyListState()
    LazyColumn(state = state) {
        item { Text("Header") }
        itemsIndexed(listOf("A", "B")) { _, label -> Text(label) }
    }
}

@Composable
fun DefaultState() {
    LazyColumn {
        item { Text("Only") }
    }
}

@Composable
fun Disabled() {
    LazyColumn(userScrollEnabled = false) {
        item { Text("Still") }
    }
}

@Composable
fun Observed() {
    val state = rememberLazyListState()
    LazyColumn(state = state) {
        item { Text(state.firstVisibleItemIndex.toString()) }
    }
}

@Composable
fun Nonzero() {
    LazyColumn(state = rememberLazyListState(1)) {
        item { Text("Offset") }
    }
}

@Composable
fun Indexed() {
    LazyColumn {
        itemsIndexed(listOf("A")) { index, label -> Text(index.toString() + label) }
    }
}

@Composable
fun Items() {
    LazyColumn {
        items(listOf("A")) { Text(it) }
    }
}
