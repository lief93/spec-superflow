package dev.ets

internal fun degradationReportJson(status: String, sink: DiagnosticSink, blocking: Diagnostic? = null): String {
    fun diagnostic(value: Diagnostic): String = "\"code\":" + quote(value.code) +
        ",\"message\":" + quote(value.message) + ",\"source\":" + diagnosticSourceJson(value.source)
    val entries = sink.degradations.joinToString(",\n") { value ->
        "{" + diagnostic(value.diagnostic) + ",\"capability\":" + quote(value.capability) +
            ",\"action\":" + quote(value.action) + ",\"impact\":" + quote(value.impact) + "}"
    }
    return "{\"schemaVersion\":1,\"status\":" + quote(status) +
        ",\"equivalenceVerified\":false,\"degradationCount\":" + sink.degradations.size +
        ",\"degradations\":[\n" + entries + "\n],\"blockingFailure\":" +
        (blocking?.let { "{" + diagnostic(it) + "}" } ?: "null") + "}\n"
}
