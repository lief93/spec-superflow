package dev.ets

import java.io.File
import java.io.IOException

internal fun quote(value: String?): String = value?.let {
    buildString {
        append('"')
        for (character in it) when (character) {
            '\\' -> append("\\\\")
            '"' -> append("\\\"")
            else -> if (character < ' ') append("\\u" + character.code.toString(16).padStart(4, '0'))
                else append(character)
        }
        append('"')
    }
} ?: "null"

internal fun diagnosticSourceJson(source: SourceSpan): String {
    // PSI offsets count UTF-16 code units after line-separator normalization.
    val text = source.file?.let { path ->
        try {
            File(path).readText().removePrefix("\uFEFF").replace("\r\n", "\n").replace('\r', '\n')
        } catch (_: IOException) {
            null
        } catch (_: SecurityException) {
            null
        }
    }
    fun position(offset: Int): Pair<Int, Int>? {
        if (text == null || source.start < 0 || source.end < source.start || source.end > text.length) return null
        var line = 1
        var column = 1
        for (index in 0 until offset) {
            if (text[index] == '\n') { line++; column = 1 } else column++
        }
        return line to column
    }
    val start = position(source.start)
    val end = position(source.end)
    return "{\"file\":" + quote(source.file) + ",\"start\":" + source.start + ",\"end\":" + source.end +
        ",\"line\":" + start?.first + ",\"column\":" + start?.second +
        ",\"endLine\":" + end?.first + ",\"endColumn\":" + end?.second + "}"
}
