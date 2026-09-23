package demo.projectinputconsumer

import demo.projectinputs.*

fun tokenInput(): ProjectToken = projectInput("enabled")
fun colorInput(): ProjectColor = projectInput("brand")
fun fontInput(): ProjectFont = projectInput("headline")
fun dimensionInput(): ProjectDimension = projectInput("spacing")
fun stringInput(): ProjectString = projectInput("welcome")
fun imageInput(): ProjectImage = projectInput("logo")
fun dependencyInput(): String = targetDependency("clock")
