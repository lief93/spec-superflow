package exceptioncases

fun observations(): List<String> {
    trace = ""
    val normal = value(0)
    val argument = value(1)
    val state = value(2)
    val values = "$normal:$argument:$state:$trace"
    trace = ""
    val a = early(0)
    val b = early(1)
    val c = early(2)
    val earlyValues = "$a:$b:$c:$trace"
    trace = ""
    val looping = loop()
    val loops = "$looping:$trace"
    trace = ""
    val nested = rethrow()
    val nesting = "$nested:$trace"
    val overridden = try { overrideThrow() } catch (failure: IllegalStateException) { 9 }
    val missing = try { nullValue()!!.length } catch (failure: NullPointerException) { 2 }
    val cast = try { (anyValue() as Key).id } catch (failure: ClassCastException) { 3 }
    val arithmetic = try { divide(0) } catch (failure: ArithmeticException) { 4 }
    val bounds = try { listOf(1)[3] } catch (failure: IndexOutOfBoundsException) { 5 }
    val model = mapOf(Key(1) to "yes")
    val combined = try { model[Key(2)]!!.length } catch (failure: RuntimeException) { -1 } finally { mark("m") }
    val message = try { throw IllegalStateException("message") } catch (failure: Exception) { failure.message ?: "none" }
    val custom = try { sourceFailure().toString() } catch (failure: PageFailure) { "${failure.code}:${failure.message}" }
    val parent = try { sourceFailure() } catch (failure: RuntimeException) { 8 }
    val first = try { readUnavailable() } catch (failure: ExceptionInInitializerError) { 1 }
    val repeated = try { readUnavailable() } catch (failure: NoClassDefFoundError) { 2 }
    val lookup = try { Stage.valueOf("missing").ordinal } catch (failure: IllegalArgumentException) { 3 }
    val iterator = mutableSetOf(Key(1)).iterator()
    iterator.next()
    val exhausted = try { iterator.next().id } catch (failure: NoSuchElementException) { 4 }
    return listOf(values, earlyValues, loops, nesting, "$overridden:$missing:$cast:$arithmetic:$bounds",
        "$combined:$message:$trace", "$custom:$parent", "$first:$repeated:$attempts:$lookup:$exhausted")
}
