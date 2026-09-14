// Explicit consumer of the unchanged historical generic member overload fixture.
fun legacyMemberCase(seed: Int): String {
    val receiver = Overloads()
    return "${receiver.select(seed)}/${receiver.select("legacy")}/" +
        "${receiver.select(seed, true)}/${receiver.select("legacy", false)}"
}
