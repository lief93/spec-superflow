interface Left
interface Right
interface Many { fun <T> select(value: T): T where T : Left, T : Right }
