package kliblibrary

import klibhelper.echo
import klibhelper.offset

fun adjusted(seed: Int): Int = echo(offset(seed)) * 3
fun buttonLabel(page: Int): String = if (page < 3) "Next" else "Explore"
