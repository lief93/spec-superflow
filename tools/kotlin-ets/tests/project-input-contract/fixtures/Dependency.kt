package demo.projectinputs

import androidx.compose.runtime.Composable

class ProjectToken
class ProjectColor
class ProjectFont
class ProjectDimension
class ProjectString
class ProjectImage
class MissingInput

fun <T : Any> projectInput(key: String): T = error(key)
fun targetDependency(name: String): String = error(name)
fun wrongParameter(value: String): String = error(value)
fun wrongReturn(): ProjectColor = error("wrong return")
fun voidValue(): ProjectString = error("void value")

@Composable
fun ProjectCard(title: String, content: @Composable () -> Unit) {
    error(title)
}
