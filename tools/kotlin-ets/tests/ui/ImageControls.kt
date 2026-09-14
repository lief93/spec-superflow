package imagecontrols

import androidx.compose.runtime.Composable
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage

@Composable
fun ImageControls(alternate: Boolean = false) {
    Column {
        Picture(painterResource(if (alternate) R.drawable.second else R.drawable.banner), "Banner")
        Icon(painterResource(R.drawable.banner), null, Modifier.size(24.dp), tint = Color.Red)
        AsyncImage("https://example.invalid/banner.png", "Remote", Modifier.size(80.dp))
    }
}

@Composable
fun Picture(painter: Painter, description: String) {
    Image(painter, description, Modifier.size(80.dp), contentScale = ContentScale.Crop, alpha = 0.5f)
}
