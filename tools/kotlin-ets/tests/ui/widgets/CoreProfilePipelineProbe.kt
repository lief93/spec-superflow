package dev.ets.widgettest

import dev.ets.*
import dev.ets.pipeline.ComposeWidgetPipeline
import java.io.File

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    val imageResources = ImageResources(
        mapOf("widgetsfixture.R.drawable.logo" to "widget_logo"),
        mapOf("widgetsfixture.R.drawable.logo" to File(args[2])),
        mapOf("widgetsfixture.R.drawable.logo" to 0x7f010001),
    )
    val text = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(3)) { module ->
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules(), imageResources))
        ComposeWidgetPipeline(backend, StandardLibraryRuntime).compile(module, "widgetsfixture.CoreProfile")
    }
    check("@Builder" in text)
    check("export function CoreProfile(" in text)
    for (control in listOf("Column", "Row", "Stack", "Text", "Image", "Button", "TextInput")) {
        check("$control(" in text) { "Missing native $control" }
    }
    check("Text(\"Open\")" in text)
    check("\$r(\"app.media.widget_logo\")" in text)
    File(output, "CoreProfile.ets").writeText(text)
    println("PASS official Compose Core Profile -> neutral Widget -> validated and printed typed ETS")
}
