interface Root<C> { fun <T> select(context: C, value: T): T }
interface Left : Root<Int>
interface Right : Root<String>
interface Diamond : Left, Right
