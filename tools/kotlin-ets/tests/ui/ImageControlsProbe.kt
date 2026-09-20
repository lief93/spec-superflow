package ui.test

import dev.ets.*
import java.io.File

fun main(args: Array<String>) {
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1], args[2])) { module ->
        val diagnostics = DiagnosticSink()
        val backend = EtsBackend(diagnostics, listOf(StandardLibraryRules(), ImageResources(mapOf(
            "imagecontrols.R.drawable.banner" to "test_banner", "imagecontrols.R.drawable.second" to "test_second"))))
        ComposeLowering(backend.language, diagnostics).lower(module, "imagecontrols.ImageControls")
    }
    EtsValidator().validate(program)
    val nodes = mutableListOf<EtsNode>()
    program.files.flatMap { it.declarations }.forEach { walkEts(it, nodes::add) }
    val images = nodes.filterIsInstance<EtsUiElement>().filter { (it.call.callee as? EtsReference)?.symbol?.name == "Image" }
    check(images.size == 3)
    fun EtsUiElement.attr(name: String) = attributes.single { (it.callee as? EtsReference)?.symbol?.name == name }.arguments.single()
    check(images.map { (it.attr("objectFit") as EtsMember).name }.toSet() == setOf("Contain", "Cover"))
    check(images.single { it.attributes.any { attr -> (attr.callee as? EtsReference)?.symbol?.name == "opacity" } }
        .attr("opacity").let { it is EtsLiteral && it.value == 0.5f })
    check(images.any { image -> image.attributes.any { (it.callee as? EtsReference)?.symbol?.name == "accessibilityLevel" } })
    check(images.any { it.call.arguments.single() is EtsReference && (it.call.arguments.single() as EtsReference).symbol.name == "painter" })
    check(nodes.filterIsInstance<EtsConditional>().any { it.type == ImageResources.RESOURCE })
    check(nodes.filterIsInstance<EtsFunction>().single { it.name == "Picture" }.parameters.map { it.symbol.name } == listOf("painter", "description"))
    val runtime = ComposeRuntime(StandardLibraryRuntime).declarations(program).joinToString("\n")
    File(args[3], "ImageControls.ets").writeText(runtime + "\n" + EtsPrinter().program(program))
    File(args[3], "runtime.ts").writeText(runtime)
    println("PASS resource conditions, Painter parameters and independent Image/Icon through typed target")
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1], args[2])) { module ->
        val diagnostics = DiagnosticSink()
        val invalid = CallRule { call, language, _ ->
            if (symbolName(call.symbol.owner) == "androidx.compose.ui.res.painterResource") {
                val source = language.source(call)
                val signature = EtsFunctionType(emptyList(), EtsTypes.VOID)
                EtsCall(EtsReference(EtsSymbol("test:wrongPainter", "wrongPainter", signature, source, true)), emptyList(), EtsTypes.VOID, source)
            } else null
        }
        val backend = EtsBackend(diagnostics, listOf(invalid, ImageResources()))
        val failure = runCatching { ComposeLowering(backend.language, diagnostics).lower(module, "imagecontrols.ImageControls") }.exceptionOrNull()
        check(failure is Unsupported && "Invalid call adapter result" in failure.message.orEmpty())
        println("PASS generic call-result checker rejects void for mapped Painter/Resource")
    }
    val registry = File(args[3], "registry").apply { mkdirs() }
    File(registry, "media").mkdirs()
    val properties = File(registry, "image-resources.properties")
    properties.writeText("imagecontrols.R.drawable.banner=test_banner\n")
    check(runCatching { ImageResources.read(properties) }.isFailure)
    File(registry, "media/test_banner.svg").writeText("<svg xmlns=\"http://www.w3.org/2000/svg\"/>")
    ImageResources.read(properties)
    properties.appendText("imagecontrols.R.drawable.banner=test_other\n")
    check(runCatching { ImageResources.read(properties) }.exceptionOrNull()?.message?.contains("Duplicate") == true)
    println("PASS resource registry rejects missing media and duplicate bindings")
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[4], args[2])) { module ->
        val cases = mapOf("MissingResource" to "Unmapped image resource", "NumericId" to "resolved R symbol",
            "DefaultIconTint" to "LocalContentColor", "UnsupportedScale" to "Unsupported ContentScale",
            "UnsupportedFilter" to "default SrcIn blend", "UnsupportedAlignment" to "argument: alignment",
            "NullableDescription" to "Nullable image description", "EffectfulSize" to "stable dimensions",
            "FileUrl" to "HTTP(S)", "CredentialUrl" to "credentials", "DynamicModel" to "dynamic models",
            "LoadingCallback" to "argument: onLoading")
        for ((entry, reason) in cases) {
            val diagnostics = DiagnosticSink()
            val backend = EtsBackend(diagnostics, listOf(StandardLibraryRules(), ImageResources(mapOf("imagecontrols.R.drawable.banner" to "test_banner"))))
            val failure = runCatching { ComposeLowering(backend.language, diagnostics).lower(module, "imagecontrols.$entry") }.exceptionOrNull()
            check(failure is Unsupported && reason in failure.message.orEmpty()) { "$entry: $failure" }
            check(failure.diagnostic.source.let { it.file == args[4] && it.start >= 0 && it.end > it.start })
        }
        println("PASS twelve source-linked negative cases; no missing-resource placeholders or discarded arguments")
    }
}
