package basiccontrols

import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Switch
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun NullCheckbox() { Checkbox(checked = true, onCheckedChange = null) }

@Composable
fun NullSwitch() { Switch(checked = true, onCheckedChange = null) }

@Composable
fun StyledCheckbox() { Checkbox(false, {}, colors = CheckboxDefaults.colors()) }

@Composable
fun SlottedSwitch() { Switch(false, {}, thumbContent = { BasicText("Icon") }) }

@Composable
fun StyledBasicText() { BasicText("Custom", style = TextStyle(fontSize = 20.sp)) }

@Composable
fun AnnotatedBasicText() { BasicText(AnnotatedString("Rich")) }

fun computeThickness(): Int = 2

@Composable
fun EffectfulThickness() { HorizontalDivider(thickness = computeThickness().dp) }
