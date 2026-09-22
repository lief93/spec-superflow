package widgetlazy

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import kotlinx.coroutines.launch

@Composable
fun LazyListProfile() {
    var selected by remember { mutableStateOf("none") }
    var effectSeed by remember { mutableStateOf(2) }
    val columnState = rememberLazyListState(
        initialFirstVisibleItemIndex = 1,
        initialFirstVisibleItemScrollOffset = 6,
    )
    val rowState = rememberLazyListState(
        initialFirstVisibleItemIndex = 1,
        initialFirstVisibleItemScrollOffset = 4,
    )
    val coroutineScope = rememberCoroutineScope()
    Column {
        Button(onClick = {
            coroutineScope.launch {
                columnState.scrollToItem(effectSeed++, effectSeed++)
                columnState.animateScrollToItem(effectSeed++, effectSeed++)
            }
        }) {
            Text("Scroll")
        }
        LazyColumn(state = columnState, userScrollEnabled = false) {
            item(key = "header") {
                Text("Selected $selected at ${columnState.firstVisibleItemIndex}")
            }
            itemsIndexed(listOf("Ada", "Lin"), key = { index, item -> "$index:$item" }) { index, item ->
                Text("$index:$item", Modifier.clickable { selected = item })
            }
            items(count = 3, key = { it }) { index ->
                Text("Count $index")
            }
            items(listOf<String>(), key = { it }) { item ->
                Text(item)
            }
        }
        LazyRow(state = rowState) {
            items(arrayOf("R1", "R2"), key = { it }) { item ->
                Text(item)
            }
        }
    }
}
