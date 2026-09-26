@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import dev.ets.pipeline.ComposeWidgetPipeline
import dev.ets.compose.ComposeWidgetAdapterModule
import dev.ets.compose.ComposeSourceUiCallGuardRule
import dev.ets.compose.composeHostProvidedRootDefault
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
                require(item in setOf("--mode", "--out", "--out-dir", "--entry", "--classpath-file", "--classpath", "--sources-file", "--image-resources", "--string-resources", "--font-resources", "--frontend-arguments-file", "--unsupported-policy", "--preflight-out", "--project-compiler-version")) { "Unknown option $item" }
                require(index < arguments.size) { "Missing value for $item" }
                options[item] = arguments[index++]
            } else sources.add(item)
        }
        options["--sources-file"]?.let { path -> sources.addAll(File(path).readLines().filter { it.isNotBlank() }) }
        require(sources.isNotEmpty()) { "At least one Kotlin source path is required" }
        require(("--out" in options) != ("--out-dir" in options)) { "Specify exactly one of --out or --out-dir" }
        val output = File(options["--out"] ?: options.getValue("--out-dir"))
        val preflightOutput = options["--preflight-out"]?.let(::File)
        require(!Files.exists(output.toPath(), NOFOLLOW_LINKS)) { "Refusing to overwrite existing target: $output" }
        preflightOutput?.let { file ->
            require(!Files.exists(file.toPath(), NOFOLLOW_LINKS)) {
                "Refusing to overwrite existing preflight report: $file"
            }
            val targetPath = output.absoluteFile.normalize().toPath()
            val reportPath = file.absoluteFile.normalize().toPath()
            require(reportPath != targetPath && ("--out-dir" !in options || !reportPath.startsWith(targetPath))) {
                "Preflight report must be outside the target path: $file"
            }
        }
        val mode = options["--mode"] ?: "page"
        require(mode in setOf("page", "language", "preflight")) {
            "Mode must be page, language, or preflight"
        }
        require(mode != "preflight" || "--out" in options) {
            "Preflight mode requires --out and does not support --out-dir"
        }
        val policy = options["--unsupported-policy"] ?: if (mode == "page") "report" else "error"
        require(policy in setOf("report", "error")) { "Unsupported policy must be report or error" }
        require(mode == "page" || policy == "error") { "$mode mode requires unsupported-policy error" }
        diagnostics.reportUiDegradation = policy == "report"
        val entry = options["--entry"]
        require(mode != "page" || entry != null) { "--entry is required for page mode" }
        require(mode != "preflight" || entry == null) { "Preflight mode scans the complete module and does not accept --entry" }
        require(mode != "preflight" || preflightOutput == null) {
            "Preflight mode writes its report to --out; omit --preflight-out"
        }
        if (mode == "page") {
            val report = File(output.absolutePath + ".diagnosis.json")
            require(!Files.exists(report.toPath(), NOFOLLOW_LINKS)) { "Refusing to overwrite existing diagnosis: $report" }
            diagnosisOutput = report
        }
        val classpath = options["--classpath"] ?: options["--classpath-file"]?.let { path ->
            File(path).readLines().filter { it.isNotBlank() }.joinToString(File.pathSeparator)
        } ?: requireNotNull(System.getenv("KOTLIN_ETS_STDLIB")) { "Kotlin stdlib path missing" }
        val frontendArgs = options["--frontend-arguments-file"]?.let { File(it).readLines().filter(String::isNotBlank) }.orEmpty()
        val compilerEnvironment = coreProfileCompilerEnvironment(options["--project-compiler-version"])
        val defaultJvmTarget = if (frontendArgs.any { it == "-jvm-target" || it.startsWith("-jvm-target=") ||
            it == "-Xjdk-release" || it.startsWith("-Xjdk-release=") }) emptyList() else listOf("-jvm-target", "17")
        val compilerArgs = defaultJvmTarget + frontendArgs +
            listOf("-no-stdlib", "-no-reflect", "-classpath", classpath) + sources
        val images = options["--image-resources"]?.let { ImageResources.read(File(it).absoluteFile) } ?: ImageResources()
        val strings = options["--string-resources"]?.let { StringResources.read(File(it).absoluteFile) } ?: StringResources()
        val dimensions = options["--string-resources"]?.let { DimensionResources.read(File(it).absoluteFile) } ?: DimensionResources()
        val fonts = options["--font-resources"]?.let { FontResources.read(File(it).absoluteFile) } ?: FontResources()
        val resourceOutput = File(output.absolutePath + ".resources")
        if (mode == "page" && ("--string-resources" in options || "--font-resources" in options || "--image-resources" in options)) require(!Files.exists(resourceOutput.toPath(), NOFOLLOW_LINKS)) {
            "Refusing to overwrite existing resource output: $resourceOutput"
        }
        val adapters = AdapterModules.load()
        fun retainSourceDefault(parameter: org.jetbrains.kotlin.ir.declarations.IrValueParameter): Boolean {
            val owner = parameter.parent as? org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
                ?: return true
            if (mode != "page" || symbolName(owner) != entry) return true
            val expression = parameter.defaultValue?.expression ?: return true
            return !composeHostProvidedRootDefault(expression) &&
                !adapters.consumesRootDefault(expression, parameter.type)
        }
        val stdlib = StandardLibraryRules()
        val shapes = ComposeShapeRule()
        val elevations = ComposeCardElevationRule(diagnostics)
        val compositionLocals = ComposeCompositionLocalRule(diagnostics)
        val rules = listOf(stdlib, CoroutineTimerRule(diagnostics), ComposeSourceUiCallGuardRule(diagnostics), images, strings, dimensions, ComposeColorValueRule(), ComposeColorFilterRule(), ComposeColorSchemeRule(), ComposeSurfaceColorAtElevationRule(), ComposeProjectColorSchemeRule(), ComposePlatformVersionRule(), ComposeThemeModeRule(), ComposeStaticAnimationRule(diagnostics), ComposeIndicationRule(diagnostics), ComposeMaterialThemeValueRule(), ComposeMaterialImageVectorRule(), ComposeSnackbarHostStateRule(), ComposeTypographyRule(), ComposeAlignmentRule(), ComposeContentScaleRule(), ComposeArrangementRule(), ComposePagerBehaviorRule(), ComposeDimensionRule(), ComposeDrawGeometryRule(), ComposeBrushRule(diagnostics), ComposeBorderStrokeRule(), ComposeConstraintsValueRule(), ComposeFontRule(fonts), ComposeLineHeightStyleRule(), ComposeTextStyleRule(), ComposeTextDecorationRule(), ComposeAnnotatedStringRule(), ComposeEmptyModifierRule(), ComposeWeightRule(), CoilImageRequestRule(), ComposeInspectionModeRule(), compositionLocals, ComposeLocalContextRule(), ComposeToastRule(), ComposeFocusManagerRule(), ComposeNavigationRule(), ComposeFlowRule(), shapes, elevations, ComposeCardColorsRule(), ComposeButtonColorsRule(), ComposePaddingValuesRule(), ComposeTextInputValueRule()) + adapters.rules()
        var preflight: CoreProfileReport? = null
        val target = withKotlinFrontend(compilerArgs, entry, runEtsLowerings = mode != "preflight", prepareModule = { module ->
            if (mode == "page") {
                rules.forEach { it.prepareModule(module, diagnostics) }
            }
        }, prepareDeclaration = { declaration ->
            if (mode == "page") rules.forEach { it.prepareSource(declaration, diagnostics) }
        }, externalSourceType = { type -> mode == "page" && adapters.providesSourceType(type) },
            externalSourceCall = { function -> mode == "page" && adapters.replacesSourceCall(function) },
            targetOwnsSourceArgument = { call, index ->
                mode == "page" && rules.any { it.ownsSourceArgumentDependency(call, index) }
            },
            retainSourceDefault = ::retainSourceDefault,
            retainUnreferencedFileInitializer = { property ->
                mode != "page" || hasSourceFileInitializerEffects(property)
            }) { frontend ->
            val module = frontend.module
            val backend = EtsBackend(diagnostics, rules, frontend.types)
            preflight = coreProfilePreflight(module, backend.language, diagnostics, compilerEnvironment)
            fun publishPreflight() = preflightOutput?.let { file ->
                Files.createDirectories(file.absoluteFile.parentFile.toPath())
                Files.writeString(file.toPath(), coreProfileJson(requireNotNull(preflight)), CREATE_NEW)
            }
            try {
                val generated = when (mode) {
                    "page" -> {
                        val widgetRules = adapters.modules.filterIsInstance<ComposeWidgetAdapterModule>()
                            .map { it.createWidgetRule() }
                        val lowered = ComposeWidgetPipeline(backend, StandardLibraryRuntime, widgetRules,
                            packageEntryComponent = true)
                            .lower(module, requireNotNull(entry))
                        val targetModule = lowered.copy(imports = (lowered.imports + adapters.imports).distinct())
                        diagnostics.verifyNoSilentFallback(targetModule)
                        preflight = requireNotNull(preflight).reconcileGeneratedTarget(targetModule,
                            diagnostics.degradations.map { it.diagnostic })
                        if ("--out-dir" in options) emitEtsModules(targetModule, ComposeRuntime(StandardLibraryRuntime))
                        else mapOf(output.name to emitEtsProgram(targetModule, ComposeRuntime(StandardLibraryRuntime)))
                    }
                    "language" -> {
                        val lowered = backend.lower(module)
                        val program = lowered.copy(imports = (lowered.imports + adapters.imports).distinct())
                        diagnostics.verifyNoSilentFallback(program)
                        preflight = requireNotNull(preflight).reconcileGeneratedTarget(program,
                            diagnostics.degradations.map { it.diagnostic })
                        if ("--out-dir" in options) emitEtsModules(program, StandardLibraryRuntime)
                        else mapOf(output.name to emitEtsProgram(program, StandardLibraryRuntime))
                    }
                    else -> mapOf(output.name to coreProfileJson(requireNotNull(preflight)))
                }
                publishPreflight()
                generated
            } catch (failure: Unsupported) {
                preflight = requireNotNull(preflight).record(failure.diagnostic)
                publishPreflight()
                throw failure
            } catch (failure: InvalidTarget) {
                preflight = requireNotNull(preflight).record(Diagnostic("INVALID_TARGET",
                    failure.message ?: "Invalid target", failure.source))
                publishPreflight()
                throw failure
            }
        }
        Files.createDirectories(output.absoluteFile.parentFile.toPath())
        val resources = strings.artifacts()
        val resourceFiles = fonts.artifacts() + images.artifacts()
        if (mode == "page" && (resources.isNotEmpty() || resourceFiles.isNotEmpty())) {
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
        val status = when {
            mode == "preflight" -> "profiled"
            diagnostics.degradations.isEmpty() -> "generated"
            else -> "generated_with_degradations"
        }
        saveDiagnosis(status)
        println("{\"ok\":true,\"status\":" + quote(status) + ",\"diagnosis\":" + quote(diagnosisOutput?.path) +
            ",\"degradationCount\":" + diagnostics.degradations.size + ",\"frontend\":\"Kotlin-2.1.20-K2-FIR2IR\",\"output\":" + quote(output.path) +
            ",\"preflight\":" + quote(preflightOutput?.path) + ",\"preflightCallCount\":" + requireNotNull(preflight).calls.size +
            ",\"resources\":" + (if (mode != "page" || resources.isEmpty() && resourceFiles.isEmpty()) "null" else quote(resourceOutput.path)) + "}")
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
