package pagerwrap

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun Page() {
    val pagerState = rememberPagerState { 2 }
    Column {
        HorizontalPager(
            state = pagerState,
            modifier = Modifier.wrapContentHeight(),
        ) { page ->
            Column(Modifier.fillMaxSize()) {
                Text("Page $page")
            }
        }
        Text("After pager")
    }
}
