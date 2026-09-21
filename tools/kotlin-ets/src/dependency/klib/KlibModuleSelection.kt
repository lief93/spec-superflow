package dev.ets.dependency.klib

import java.io.File

/**
 * Explicit KLIB selection. The official resolver still receives every library path,
 * including those that must remain dependencies-only. Identity is a canonical path,
 * never a JS output name or function FQName.
 */
data class KlibModuleSelection(
    val main: File,
    val translated: List<File>,
    val libraries: List<File>,
) {
    init {
        require(main.isFile) { "Main KLIB is missing: $main" }
        require(translated.isNotEmpty()) { "At least one translated KLIB is required" }
        require(libraries.isNotEmpty()) { "KLIB libraries are required; stdlib must be supplied explicitly" }
        val all = (listOf(main) + translated + libraries).map { it.canonicalFile }
        require(all.none { it.extension != "klib" && !it.isDirectory }) {
            "KLIB selection contains a non-klib path"
        }
        val translatedPaths = translated.map { it.canonicalPath }.toSet()
        require(main.canonicalPath in translatedPaths) { "Main KLIB must be included in the translated set" }
        require(translatedPaths.size == translated.size) { "Translated KLIB paths must be unique" }
        val libraryPaths = libraries.map { it.canonicalPath }.toSet()
        require(libraryPaths.size == libraries.size) { "Library KLIB paths must be unique" }
        require(translatedPaths.intersect(libraryPaths).isEmpty()) {
            "A KLIB cannot be both translated and a dependency-only library"
        }
    }

    fun resolverPaths(): List<String> =
        (listOf(main) + translated + libraries).map { it.canonicalPath }.distinct()

    fun translatedCanonicalPaths(): Set<String> = translated.map { it.canonicalPath }.toSet()
}
