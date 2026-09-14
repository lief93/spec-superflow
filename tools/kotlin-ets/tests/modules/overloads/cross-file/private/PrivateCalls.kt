package privateoverloads

fun privateCase(seed: Int): String =
    "${leftPrivateCase(seed)}|${rightPrivateCase(seed)}|${mixed(seed.toDouble())}|${mixed(true)}|${unrelatedPrivateCase(seed)}"
