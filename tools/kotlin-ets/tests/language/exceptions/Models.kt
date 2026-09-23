package exceptioncases

data class Key(val id: Int)

class PageFailure(val code: Int, message: String) : RuntimeException(message)

class Error(val code: Int)

enum class Stage { First, Last }
