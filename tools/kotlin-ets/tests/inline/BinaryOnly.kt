package inlinefixture

import inlinelibrary.libraryTransform

fun binaryCall(): Int = libraryTransform(2) { first, second -> first + second }
