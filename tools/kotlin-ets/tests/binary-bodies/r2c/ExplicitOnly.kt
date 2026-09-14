package defaultconsumer

import defaultbinary.defaultSelect

fun explicitOnly(seed: Int): Int = seed.defaultSelect(selected = seed + 10, mark = {})
