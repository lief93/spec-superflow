package kliblibrary

import klibhelper.echo
import klibhelper.offset
import klibhelper.bias

fun adjusted(seed: Int): Int = echo(bias(offset(seed), 5)) * 3
fun buttonLabel(page: Int): String = if (page < 3) "Next" else "Explore"
