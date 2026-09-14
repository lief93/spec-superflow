package negative

import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.runtime.Composable

@Composable
fun UnknownPage(pages: Int = 4) {
    val pager = rememberPagerState { pages }
}
