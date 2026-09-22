package dev.ets.widgets

/** A runtime theme-mode read retained until the target selects its configuration source. */
enum class ThemeModeSource { APPLICATION_CONFIGURATION }

data class ThemeModeRead<S>(val source: ThemeModeSource, val location: S)
