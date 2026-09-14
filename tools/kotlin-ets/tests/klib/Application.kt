package klibconsumer

import kliblibrary.adjusted
import kliblibrary.buttonLabel

fun scenario(seed: Int): String = "${buttonLabel(seed)}:${adjusted(seed)}"
