package widgetpager

import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun PagerProfile() {
    val pager = rememberPagerState(initialPage = 1) { 4 }
    val selected = remember { mutableStateOf(-1) }
    Column(Modifier.width(360.dp)) {
        HorizontalPager(state = pager, userScrollEnabled = true,
            modifier = Modifier.fillMaxWidth()) { page ->
            if (page < 3) Text("A") else Text("B")
        }
        Text("Indicator ${pager.currentPage + 1}/4")
        if (pager.currentPage == 3) {
            Button(onClick = { selected.value = pager.currentPage }) { Text("Finish") }
        } else {
            Button(onClick = { selected.value = pager.currentPage }) { Text("Next") }
        }
        Text("Selected ${selected.value}")
    }
}

@Composable
fun FivePageProfile() {
    val pager = rememberPagerState(initialPage = 4) { 5 }
    HorizontalPager(state = pager, userScrollEnabled = false) { page ->
        Text("Page $page")
    }
}
