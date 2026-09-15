package dev.ets

import java.util.ServiceLoader
import java.util.ServiceConfigurationError
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrConstructorCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

/** A build-time SPI provider, not another source parser or code generator. */
interface AdapterModule {
    val id: String
    val sourceCalls: Set<String>
    val sourceTypes: Set<String> get() = emptySet()
    val targetCalls: List<AdapterTargetCall> get() = emptyList()
    val imports: List<EtsImport> get() = emptyList()
    fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule
}

data class AdapterTargetCall(val id: String, val name: String, val signature: EtsFunctionType)

interface AdapterUiServices {
    fun content(expression: IrExpression, scope: Scope): List<EtsStatement>
    fun decorate(modifier: IrExpression?, scope: Scope, element: EtsUiElement,
        boundaries: Set<String> = emptySet()): List<EtsStatement>
}

class AdapterTargetApi internal constructor(private val signatures: Map<String, AdapterTargetCall>) {
    fun call(id: String, arguments: List<EtsExpression>, source: SourceSpan,
        receiver: EtsExpression? = null): EtsCall {
        val declaration = signatures[id] ?: throw Unsupported(Diagnostic("UNSUPPORTED", "Unknown adapter target API: $id", source))
        val signature = declaration.signature
        if (arguments.size != signature.parameters.size)
            throw Unsupported(Diagnostic("UNSUPPORTED", "Adapter target API $id requires ${signature.parameters.size} arguments", source))
        // The shared validator checks argument types, including source-class inheritance.
        val callee = if (receiver == null) EtsReference(EtsSymbol(id, declaration.name, signature, source, external = true))
            else EtsMember(receiver, declaration.name, signature, source)
        return EtsCall(callee, arguments, signature.result, source)
    }
}

class AdapterModules(modules: List<AdapterModule> = emptyList()) {
    private val ordered = modules.sortedBy { it.id }
    private val target: AdapterTargetApi
    private val used = linkedSetOf<String>()
    val imports: List<EtsImport> get() = ordered.filter { it.id in used }.flatMap { it.imports }.distinct()

    init {
        val ids = mutableSetOf<String>()
        val calls = mutableMapOf<String, String>()
        val types = mutableMapOf<String, String>()
        val targets = linkedMapOf<String, AdapterTargetCall>()
        val bindings = mutableMapOf<String, EtsImport>()
        for (module in ordered) {
            require(module.id.isNotBlank() && ids.add(module.id)) { "Duplicate or blank adapter module ID: ${module.id}" }
            require(module.sourceCalls.isNotEmpty() || module.sourceTypes.isNotEmpty()) { "Adapter module ${module.id} claims no source API" }
            fun claim(values: Set<String>, owners: MutableMap<String, String>, kind: String) {
                values.sorted().forEach { value ->
                    require(value.isNotBlank()) { "Blank $kind claim in adapter ${module.id}" }
                    val previous = owners.putIfAbsent(value, module.id)
                    require(previous == null) { "Conflicting $kind claim $value: $previous and ${module.id}" }
                }
            }
            claim(module.sourceCalls, calls, "source call")
            claim(module.sourceTypes, types, "source type")
            module.targetCalls.forEach { declaration ->
                require(declaration.id.isNotBlank() && declaration.name.isNotBlank()) { "Blank target API in adapter ${module.id}" }
                require(declaration.signature.typeParameters.isEmpty()) { "Adapter target API must have an instantiated signature: ${declaration.id}" }
                require(targets.putIfAbsent(declaration.id, declaration) == null) { "Duplicate adapter target API ID: ${declaration.id}" }
            }
            module.imports.forEach { value ->
                val name = value.alias ?: value.name
                val previous = bindings.putIfAbsent(name, value)
                require(previous == null || previous == value) { "Conflicting adapter import binding: $name" }
            }
        }
        target = AdapterTargetApi(targets)
    }

    fun rules(ui: AdapterUiServices? = null): List<CallRule> = ordered.map { module ->
        val delegate = module.create(target, ui)
        object : CallRule {
            private fun claimed(call: IrCall) = symbolName(call.symbol.owner) in module.sourceCalls
            private fun <T> track(value: T?): T? = value.also { if (it != null) used.add(module.id) }

            override fun mapType(type: IrType, language: Language): EtsType? =
                if (ui == null && type.classOrNull?.owner?.let(::symbolName) in module.sourceTypes)
                    track(delegate.mapType(type, language)) else null

            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
                if (ui == null && claimed(call)) track(delegate.lower(call, language, scope)) else null

            override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? =
                if (ui == null && symbolName(call.symbol.owner) in module.sourceCalls)
                    track(delegate.lowerConstructor(call, language, scope)) else null

            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? =
                if (ui == null && claimed(call)) track(delegate.lowerStatement(call, language, scope)) else null

            override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? =
                if (ui != null && claimed(call)) track(delegate.lowerUi(call, language, scope)) else null
        }
    }

    companion object {
        fun load(): AdapterModules = try {
            AdapterModules(ServiceLoader.load(AdapterModule::class.java).toList())
        } catch (failure: ServiceConfigurationError) {
            throw IllegalArgumentException("Cannot load adapter module: ${failure.message}", failure)
        }
    }
}
