package collision.calls

import collision.left.shared as leftShared
import collision.right.shared as rightShared

fun packageCase(value: Int): Int = leftShared(value) + rightShared(value)
