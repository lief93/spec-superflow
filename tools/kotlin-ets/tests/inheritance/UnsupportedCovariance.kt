open class Result
class NarrowResult : Result()
open class ResultFactory { open fun create(): Result = Result() }
class NarrowFactory : ResultFactory() { override fun create(): NarrowResult = NarrowResult() }
