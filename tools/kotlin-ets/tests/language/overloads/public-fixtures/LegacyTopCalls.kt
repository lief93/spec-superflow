package languagefixture

// Explicit consumer of the unchanged historical top-level overload fixture.
fun legacyTopCase(seed: Int): String = "${choose(seed)}/${choose("legacy")}"
