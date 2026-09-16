package dev.ets

import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.StandardOpenOption.CREATE_NEW
import kotlin.system.exitProcess

fun main(arguments: Array<String>) {
    val diagnostics = DiagnosticSink()
    var diagnosisOutput: File? = null
    var diagnosisAttempted = false
    fun saveDiagnosis(status: String, failure: Diagnostic? = null) {
        diagnosisOutput?.let { file ->
            if (diagnosisAttempted) return
            diagnosisAttempted = true
            Files.createDirectories(file.parentFile.toPath())
            Files.writeString(file.toPath(), degradationReportJson(status, diagnostics, failure), CREATE_NEW)
        }
    }
    try {
        val options = linkedMapOf<String, String>()
        val sources = mutableListOf<String>()
        var index = 0
        while (index < arguments.size) {
            val item = arguments[index++]
            if (item.startsWith("--")) {
                require(item in setOf("--mode", "--out", "--out-dir", "--entry", "--classpath-file", "--classpath", "--sources-file", "--image-resources", "--string-resources", "--font-resources", "--frontend-arguments-file", "--unsupported-policy")) { "Unknown option $item" }
                require(index < arguments.size) { "Missing value for $item" }
                options[item] = arguments[index++]
            } else sources.add(item)
        }
        options["--sources-file"]?.let { path -> sources.addAll(File(path).readLines().filter { it.isNotBlank() }) }
        require(sources.isNotEmpty()) { "At least one Kotlin source path is required" }
        require(("--out" in options) != ("--out-dir" in options)) { "Specify exactly one of --out or --out-dir" }
        val output = File(options["--out"] ?: options.getValue("--out-dir"))
        require(!Files.exists(output.toPath(), NOFOLLOW_LINKS)) { "Refusing to overwrite existing target: $output" }
        val mode = options["--mode"] ?: "page"
        require(mode in setOf("page", "language")) { "Mode must be page or language" }
        val policy = options["--unsupported-policy"] ?: if (mode == "page") "report" else "error"
        require(policy in setOf("report", "error")) { "Unsupported policy must be report or error" }
        require(mode == "page" || policy == "error") { "Language mode requires unsupported-policy error" }
        diagnostics.reportUiDegradation = policy == "report"
        val entry = options["--entry"]
        require(mode != "page" || entry != null) { "--entry is required for page mode" }
        if (mode == "page") {
            val report = File(output.absolutePath + ".diagnosis.json")
            require(!Files.exists(report.toPath(), NOFOLLOW_LINKS)) { "Refusing to overwrite existing diagnosis: $report" }
            diagnosisOutput = report
        }
        val classpath = options["--classpath"] ?: options["--classpath-file"]?.let { path ->
            File(path).readLines().filter { it.isNotBlank() }.joinToString(File.pathSeparator)
        } ?: requireNotNull(System.getenv("KOTLIN_ETS_STDLIB")) { "Kotlin stdlib path missing" }
        val frontendArgs = options["--frontend-arguments-file"]?.let { File(it).readLines().filter(String::isNotBlank) }.orEmpty()
        val defaultJvmTarget = if (frontendArgs.any { it == "-jvm-target" || it.startsWith("-jvm-target=") ||
            it == "-Xjdk-release" || it.startsWith("-Xjdk-release=") }) emptyList() else listOf("-jvm-target", "17")
        val compilerArgs = defaultJvmTarget + frontendArgs +
            listOf("-no-stdlib", "-no-reflect", "-classpath", classpath) + sources
        val images = options["--image-resources"]?.let { ImageResources.read(File(it).absoluteFile) } ?: ImageResources()
        val strings = options["--string-resources"]?.let { StringResources.read(File(it).absoluteFile) } ?: StringResources()
        val fonts = options["--font-resources"]?.let { FontResources.read(File(it).absoluteFile) } ?: FontResources()
        val resourceOutput = File(output.absolutePath + ".resources")
        if ("--string-resources" in options || "--font-resources" in options || "--image-resources" in options) require(!Files.exists(resourceOutput.toPath(), NOFOLLOW_LINKS)) {
            "Refusing to overwrite existing resource output: $resourceOutput"
        }
        val adapters = AdapterModules.load()
        val stdlib = StandardLibraryRules()
        val rules = listOf(stdlib, images, strings, ComposeColorValueRule(), ComposeColorSchemeRule(), ComposeProjectColorSchemeRule(), ComposeStaticAnimationRule(diagnostics), ComposeMaterialThemeValueRule(), ComposeTypographyRule(), ComposeAlignmentRule(), ComposeArrangementRule(), ComposeDimensionRule(), ComposeFontRule(fonts), ComposeTextStyleRule(), ComposeTextDecorationRule(), ComposeEmptyModifierRule(), ComposeWeightRule(), CoilImageRequestRule(), ComposeInspectionModeRule(), ComposeLocalContextRule(), ComposeShapeRule(), ComposeButtonColorsRule(), ComposePaddingValuesRule()) + adapters.rules()
        val target = withKotlinFrontend(compilerArgs, entry, prepareDeclaration = { declaration ->
            if (mode == "page") rules.forEach { it.prepareSource(declaration, diagnostics) }
        }) { frontend ->
            val module = frontend.module
            val backend = EtsBackend(diagnostics, rules, frontend.types)
            if (mode == "page") {
                backend.validateSource(module)
                val lowered = ComposeLowering(backend.language, diagnostics, adapters).lower(module,
                    requireNotNull(entry))
                val targetModule = lowered.copy(imports = (lowered.imports + adapters.imports).distinct())
                if ("--out-dir" in options) emitEtsModules(targetModule, ComposeRuntime(StandardLibraryRuntime))
                else mapOf(output.name to emitEtsProgram(targetModule, ComposeRuntime(StandardLibraryRuntime)))
            } else {
                val lowered = backend.lower(module)
                val program = lowered.copy(imports = (lowered.imports + adapters.imports).distinct())
                if ("--out-dir" in options) emitEtsModules(program, StandardLibraryRuntime)
                else mapOf(output.name to emitEtsProgram(program, StandardLibraryRuntime))
            }
        }
        Files.createDirectories(output.absoluteFile.parentFile.toPath())
        val resources = strings.artifacts()
        val resourceFiles = fonts.artifacts() + images.artifacts()
        if (resources.isNotEmpty() || resourceFiles.isNotEmpty()) {
            Files.createDirectory(resourceOutput.toPath())
            resources.forEach { (name, content) ->
                val file = resourceOutput.resolve(name)
                Files.createDirectories(file.parentFile.toPath())
                Files.writeString(file.toPath(), content, CREATE_NEW)
            }
            resourceFiles.forEach { (name, original) ->
                val file = resourceOutput.resolve(name)
                Files.createDirectories(file.parentFile.toPath())
                Files.copy(original.toPath(), file.toPath())
            }
        }
        if ("--out-dir" in options) {
            Files.createDirectory(output.toPath())
            target.forEach { (name, code) -> Files.writeString(output.resolve(name).toPath(), code, CREATE_NEW) }
        } else Files.writeString(output.toPath(), target.getValue(output.name), CREATE_NEW)
        val status = if (diagnostics.degradations.isEmpty()) "generated" else "generated_with_degradations"
        saveDiagnosis(status)
        println("{\"ok\":true,\"status\":" + quote(status) + ",\"diagnosis\":" + quote(diagnosisOutput?.path) +
            ",\"degradationCount\":" + diagnostics.degradations.size + ",\"frontend\":\"Kotlin-2.1.20-K2-FIR2IR\",\"output\":" + quote(output.path) +
            ",\"resources\":" + (if (resources.isEmpty() && resourceFiles.isEmpty()) "null" else quote(resourceOutput.path)) + "}")
    } catch (failure: InvalidTarget) {
        saveDiagnosis("blocked", Diagnostic("INVALID_TARGET", failure.message ?: "Invalid target", failure.source))
        println("{\"ok\":false,\"code\":\"INVALID_TARGET\",\"message\":" + quote(failure.message) +
            ",\"source\":" + diagnosticSourceJson(failure.source) + "}")
        exitProcess(2)
    } catch (failure: Unsupported) {
        val d = failure.diagnostic
        saveDiagnosis("blocked", d)
        println("{\"ok\":false,\"code\":" + quote(d.code) + ",\"message\":" + quote(d.message) +
            ",\"source\":" + diagnosticSourceJson(d.source) + "}")
        exitProcess(2)
    } catch (failure: Exception) {
        saveDiagnosis("blocked", Diagnostic("COMPILATION_REJECTED", failure.message ?: "Compilation rejected", SourceSpan(null, -1, -1)))
        System.err.println(failure.message)
        println("{\"ok\":false,\"code\":\"COMPILATION_REJECTED\",\"message\":" + quote(failure.message) + "}")
        exitProcess(1)
    }
}
