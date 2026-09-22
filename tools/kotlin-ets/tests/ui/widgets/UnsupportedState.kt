package widgetsstate

import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.pager.PagerState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable

@Composable
fun SaveableState() {
    val count = rememberSaveable { mutableStateOf(0) }
    Text(count.value.toString())
}

@Composable
fun DerivedState() {
    val count by remember { derivedStateOf { 1 } }
    Text(count.toString())
}

@Composable
fun UnsupportedStateType() {
    val amount = remember { mutableStateOf(1.5) }
    Text(amount.value.toString())
}

@Composable
fun IndirectStateInitializer(seed: Int) {
    val count = remember { mutableStateOf(seed) }
    Text(count.value.toString())
}

@Composable
fun SharedLazyListState(state: LazyListState) {
    Text(state.firstVisibleItemIndex.toString())
}

@Composable
fun SharedPagerState(state: PagerState) {
    Text(state.currentPage.toString())
}

@Composable
fun SharedScrollState(state: ScrollState) {
    Text(state.value.toString())
}
