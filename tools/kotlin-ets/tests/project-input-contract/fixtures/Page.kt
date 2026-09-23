package demo.projectinputconsumer

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import demo.projectinputs.ProjectCard

@Composable
fun ProjectInputPage(show: Boolean = true) {
    ProjectCard("Project inputs") {
        if (show) Text("visible") else Text("hidden")
        repeat(2) { Text("item") }
    }
}
