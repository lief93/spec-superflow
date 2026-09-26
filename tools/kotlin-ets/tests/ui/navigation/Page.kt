package navigation

import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.navigation.NavController

object RegisterScreenRoute {
    fun sourceOnlyImplementation(): String = System.getProperty("os.name")
}

@Composable
fun NavigationPage(navController: NavController) {
    val label = remember { "Register" }
    Button(onClick = { navController.navigate(RegisterScreenRoute) }) {
        Text(label)
    }
}
