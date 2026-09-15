package imageids
import androidx.compose.runtime.Composable
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp

fun retained(id: Int): Int = id
@Composable
fun icon(id: Int) = painterResource(id)
@Composable
fun chosen(): androidx.compose.ui.graphics.painter.Painter {
    var id = R.drawable.logo
    id = R.drawable.second
    return painterResource(id)
}
private var reads: Int = 0
fun nextId(): Int { reads += 1; return R.drawable.logo }
fun readCount(): Int = reads
@Composable
fun effectful(): androidx.compose.ui.graphics.painter.Painter {
    val id = nextId()
    return painterResource(id)
}
@Composable
fun Page() {
    Column {
        Image(icon(retained(R.drawable.logo)), null, Modifier.size(32.dp))
        Image(chosen(), null, Modifier.size(32.dp))
        Image(effectful(), null, Modifier.size(32.dp))
        Text(readCount().toString())
    }
}
