package dev.ets

import java.util.ServiceLoader
import java.util.ServiceConfigurationError
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrConstructorCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.expressions.IrFunctionAccessExpression
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue
import org.jetbrains.kotlin.ir.expressions.IrGetField
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.render

/** A build-time SPI provider, not another source parser or code generator. */
interface AdapterModule {
    val id: String
    val sourceCalls: Set<String> get() = emptySet()
    val projectCalls: List<AdapterProjectCall> get() = emptyList()
    val projectInputs: List<AdapterProjectInput> get() = projectCalls
    val sourceTypes: Set<String> get() = emptySet()
    val sourceFields: Set<String> get() = emptySet()
    val targetCalls: List<AdapterTargetCall> get() = emptyList()
    val targetValues: List<AdapterTargetValue> get() = emptyList()
    val imports: List<EtsImport> get() = emptyList()
    fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule
}

data class AdapterTargetCall(val id: String, val name: String, val signature: EtsFunctionType)
data class AdapterTargetValue(val id: String, val name: String, val type: EtsType)

/** Complete source declaration shape; overload selection never relies on a call name alone. */
data class AdapterCallIdentity(
    val symbol: String,
    val typeParameters: Int,
    val dispatchReceiver: String? = null,
    val extensionReceiver: String? = null,
    val parameters: List<String>,
    val returnType: String,
    val suspend: Boolean = false,
)

/** A concrete source result and its target representation for one project input. */
enum class AdapterInputKind {
    TOKEN, COLOR, FONT, DIMENSION, STRING_RESOURCE, IMAGE_RESOURCE, BUSINESS_COMPONENT, TARGET_DEPENDENCY,
}

enum class AdapterInputConsumption { VALUE, STATEMENT, UI }

data class AdapterTargetParameter(val sourceName: String, val targetType: EtsType, val optional: Boolean = false)
data class AdapterContentSlot(val sourceName: String, val required: Boolean = true)

data class AdapterProjectInput(
    val source: AdapterCallIdentity,
    val resolvedSourceReturnType: String,
    val targetReturnType: EtsType,
    val explicitArguments: Int = 0,
    val requiredScope: String? = null,
    val kind: AdapterInputKind = AdapterInputKind.TARGET_DEPENDENCY,
    val consumption: AdapterInputConsumption = AdapterInputConsumption.VALUE,
    val parameters: List<AdapterTargetParameter> = emptyList(),
    val contentSlot: AdapterContentSlot? = null,
    val targetId: String? = null,
)

typealias AdapterProjectCall = AdapterProjectInput

interface AdapterUiServices {
    fun content(expression: IrExpression, scope: Scope): List<EtsStatement>
    fun decorate(modifier: IrExpression?, scope: Scope, element: EtsUiElement,
        boundaries: Set<String> = emptySet()): List<EtsStatement>
}

class AdapterTargetApi internal constructor(
    private val signatures: Map<String, AdapterTargetCall>,
    private val values: Map<String, AdapterTargetValue> = emptyMap(),
) {
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

    fun value(id: String, type: EtsType, source: SourceSpan): EtsReference {
        val declaration = values[id]
            ?: throw Unsupported(Diagnostic("UNSUPPORTED", "Unknown adapter target value: $id", source))
        if (!adapterTargetTypeMatches(declaration.type, type)) throw Unsupported(Diagnostic(
            "PROJECT_ADAPTER_RETURN_TYPE",
            "Adapter target value $id has type ${declaration.type}, requested $type", source))
        return EtsReference(EtsSymbol(id, declaration.name, type, source, external = true))
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
        val fields = mutableMapOf<String, String>()
        val targets = linkedMapOf<String, AdapterTargetCall>()
        val targetValues = linkedMapOf<String, AdapterTargetValue>()
        val projectInputs = linkedMapOf<AdapterProjectInputKey, String>()
        val projectSymbols = mutableMapOf<String, String>()
        val projectIdentities = mutableMapOf<AdapterCallIdentity, String>()
        val bindings = mutableMapOf<String, EtsImport>()
        for (module in ordered) {
            require(module.id.isNotBlank() && ids.add(module.id)) { "Duplicate or blank adapter module ID: ${module.id}" }
            require(module.sourceCalls.isNotEmpty() || module.projectInputs.isNotEmpty() ||
                module.sourceTypes.isNotEmpty() || module.sourceFields.isNotEmpty()) {
                "Adapter module ${module.id} claims no source API"
            }
            fun claim(values: Set<String>, owners: MutableMap<String, String>, kind: String) {
                values.sorted().forEach { value ->
                    require(value.isNotBlank()) { "Blank $kind claim in adapter ${module.id}" }
                    val previous = owners.putIfAbsent(value, module.id)
                    require(previous == null) { "Conflicting $kind claim $value: $previous and ${module.id}" }
                }
            }
            module.sourceCalls.forEach { value ->
                require(value !in projectSymbols) {
                    "Conflicting source/project call claim $value: ${projectSymbols[value]} and ${module.id}"
                }
            }
            claim(module.sourceCalls, calls, "source call")
            claim(module.sourceTypes, types, "source type")
            claim(module.sourceFields, fields, "source field")
            module.projectInputs.forEach { binding ->
                val identity = binding.source
                require(identity.symbol.isNotBlank() && identity.typeParameters >= 0 &&
                    identity.parameters.none(String::isBlank) && identity.returnType.isNotBlank() &&
                    identity.dispatchReceiver?.isNotBlank() != false &&
                    identity.extensionReceiver?.isNotBlank() != false) {
                    "Invalid project call identity in adapter ${module.id}: $identity"
                }
                require(binding.resolvedSourceReturnType.isNotBlank() && binding.explicitArguments >= 0 &&
                    binding.requiredScope?.isNotBlank() != false) {
                    "Invalid project call binding in adapter ${module.id}: $binding"
                }
                require(binding.parameters.map { it.sourceName }.all(String::isNotBlank) &&
                    binding.parameters.map { it.sourceName }.toSet().size == binding.parameters.size &&
                    binding.parameters.none { it.targetType == EtsTypes.VOID } &&
                    binding.contentSlot?.sourceName?.isNotBlank() != false &&
                    binding.contentSlot?.sourceName !in binding.parameters.map { it.sourceName }) {
                    "Invalid project input parameters in adapter ${module.id}: $binding"
                }
                binding.targetId?.let { targetId ->
                    val targetCall = module.targetCalls.singleOrNull { it.id == targetId }
                    val targetValue = module.targetValues.singleOrNull { it.id == targetId }
                    require((targetCall == null) != (targetValue == null)) {
                        "Unknown or ambiguous project input target $targetId in adapter ${module.id}"
                    }
                    if (targetCall != null) require(targetCall.signature.parameters.size == binding.parameters.size &&
                        targetCall.signature.parameters.zip(binding.parameters).all { (actual, expected) ->
                            adapterTargetTypeMatches(expected.targetType, actual)
                        } && adapterTargetTypeMatches(binding.targetReturnType, targetCall.signature.result)) {
                        "Project input target call signature mismatch for $targetId in adapter ${module.id}"
                    }
                    if (targetValue != null) require(binding.parameters.isEmpty() && binding.contentSlot == null &&
                        adapterTargetTypeMatches(binding.targetReturnType, targetValue.type)) {
                        "Project input target value type mismatch for $targetId in adapter ${module.id}"
                    }
                }
                require(binding.parameters.isEmpty() && binding.contentSlot == null || binding.explicitArguments == 0) {
                    "Typed project input parameters cannot use legacy explicitArguments in adapter ${module.id}: $binding"
                }
                require(when (binding.consumption) {
                    AdapterInputConsumption.VALUE -> binding.targetReturnType != EtsTypes.VOID && binding.contentSlot == null
                    AdapterInputConsumption.STATEMENT -> binding.targetReturnType == EtsTypes.VOID && binding.contentSlot == null
                    AdapterInputConsumption.UI -> binding.targetReturnType == EtsTypes.VOID
                }) { "Invalid project input consumption in adapter ${module.id}: $binding" }
                require(binding.kind != AdapterInputKind.BUSINESS_COMPONENT ||
                    binding.consumption == AdapterInputConsumption.UI) {
                    "Business component project input requires UI consumption in adapter ${module.id}: $binding"
                }
                val key = AdapterProjectInputKey(identity, binding.resolvedSourceReturnType,
                    binding.targetReturnType, binding.consumption)
                require(identity.symbol !in calls) {
                    "Conflicting source/project call claim ${identity.symbol}: ${calls[identity.symbol]} and ${module.id}"
                }
                projectSymbols.putIfAbsent(identity.symbol, module.id)
                val identityOwner = projectIdentities.putIfAbsent(identity, module.id)
                require(identityOwner == null || identityOwner == module.id) {
                    "Conflicting project call identity ${identity.symbol}: $identityOwner and ${module.id}"
                }
                val ambiguous = projectInputs.keys.firstOrNull { previous ->
                    previous.source == identity && previous.resolvedSourceReturnType == binding.resolvedSourceReturnType &&
                        previous.consumption == binding.consumption &&
                        (adapterTargetTypeMatches(previous.targetReturnType, binding.targetReturnType) ||
                            adapterTargetTypeMatches(binding.targetReturnType, previous.targetReturnType))
                }
                require(ambiguous == null) {
                    "Ambiguous project input ${identity.symbol} returning ${binding.resolvedSourceReturnType}: " +
                        "${projectInputs[ambiguous]} and ${module.id}"
                }
                val previous = projectInputs.putIfAbsent(key, module.id)
                require(previous == null) {
                    "Conflicting project call ${identity.symbol} returning ${binding.resolvedSourceReturnType}: " +
                        "$previous and ${module.id}"
                }
            }
            module.targetCalls.forEach { declaration ->
                require(declaration.id.isNotBlank() && declaration.name.isNotBlank()) { "Blank target API in adapter ${module.id}" }
                require(declaration.signature.typeParameters.isEmpty()) { "Adapter target API must have an instantiated signature: ${declaration.id}" }
                require(declaration.id !in targetValues && targets.putIfAbsent(declaration.id, declaration) == null) {
                    "Duplicate adapter target API ID: ${declaration.id}"
                }
            }
            module.targetValues.forEach { declaration ->
                require(declaration.id.isNotBlank() && declaration.name.isNotBlank()) {
                    "Blank target value in adapter ${module.id}"
                }
                require(declaration.id !in targets && targetValues.putIfAbsent(declaration.id, declaration) == null) {
                    "Duplicate adapter target API ID: ${declaration.id}"
                }
            }
            module.imports.forEach { value ->
                val name = value.alias ?: value.name
                val previous = bindings.putIfAbsent(name, value)
                require(previous == null || previous == value) { "Conflicting adapter import binding: $name" }
            }
        }
        target = AdapterTargetApi(targets, targetValues)
    }

    fun rules(ui: AdapterUiServices? = null): List<CallRule> = ordered.map { module ->
        val delegate = module.create(target, ui)
        object : CallRule {
            override fun targetFiles(program: EtsProgram): List<EtsFile> =
                if (ui == null && module.id in used) delegate.targetFiles(program) else emptyList()

            override fun targetImports(program: EtsProgram): List<EtsImport> =
                if (ui == null && module.id in used) delegate.targetImports(program) else emptyList()

            override fun targetContracts(program: EtsProgram): List<EtsClass> =
                if (ui == null && module.id in used) delegate.targetContracts(program) else emptyList()

            private fun claimed(call: IrCall) = symbolName(call.symbol.owner) in module.sourceCalls
            private fun identity(call: IrCall): AdapterCallIdentity {
                val owner = call.symbol.owner
                return AdapterCallIdentity(symbolName(owner), owner.typeParameters.size,
                    owner.dispatchReceiverParameter?.type?.render(), owner.extensionReceiverParameter?.type?.render(),
                    owner.valueParameters.map { it.type.render() }, owner.returnType.render(), owner.isSuspend)
            }
            private fun reusableSourceBody(call: IrFunctionAccessExpression): Boolean {
                val owner = call.symbol.owner
                return sourceFile(owner) != null && !owner.isExternal && owner.body != null
            }
            private fun <T> track(value: T?): T? = value.also { if (it != null) used.add(module.id) }

            private fun projectBinding(call: IrCall, language: Language, scope: Scope,
                consumption: AdapterInputConsumption): Pair<AdapterProjectInput, EtsType>? {
                val sourceIdentity = identity(call)
                val candidates = module.projectInputs.filter { it.source == sourceIdentity }
                if (candidates.isEmpty()) return null
                val resolved = call.type.render()
                val resolvedCandidates = candidates.filter { it.resolvedSourceReturnType == resolved }
                if (resolvedCandidates.isEmpty()) projectFailure(call, language, "PROJECT_ADAPTER_MISSING",
                    "Project adapter ${module.id} has no concrete binding for resolved return $resolved")
                val targetType = language.type(call.type)
                val consumptionCandidates = resolvedCandidates.filter { it.consumption == consumption }
                val binding = consumptionCandidates.singleOrNull {
                    adapterTargetTypeMatches(it.targetReturnType, targetType)
                } ?: projectFailure(call, language, "PROJECT_ADAPTER_RETURN_TYPE",
                    "Project adapter ${module.id} has no ${consumption.name.lowercase()} binding for " +
                        "resolved target return $targetType")
                validateArguments(binding, call, language, scope)
                binding.requiredScope?.let { required ->
                    if (required !in scope.ambientValues) projectFailure(call, language,
                        "PROJECT_ADAPTER_SCOPE", "Project adapter ${module.id} requires target scope $required")
                }
                return binding to targetType
            }

            private fun validateArguments(binding: AdapterProjectInput, call: IrCall,
                language: Language, scope: Scope) {
                if (binding.parameters.isEmpty() && binding.contentSlot == null) {
                    val explicit = (0 until call.valueArgumentsCount).count { call.getValueArgument(it) != null }
                    if (explicit != binding.explicitArguments) projectFailure(call, language,
                        "PROJECT_ADAPTER_ARGUMENTS", "Project adapter ${module.id} requires " +
                            "${binding.explicitArguments} explicit arguments, resolved $explicit")
                    return
                }
                val sourceParameters = call.symbol.owner.valueParameters.associateBy { it.name.asString() }
                val allowed = binding.parameters.mapTo(linkedSetOf()) { it.sourceName }
                binding.contentSlot?.let { allowed += it.sourceName }
                call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
                    if (call.getValueArgument(index) != null && parameter.name.asString() !in allowed)
                        projectFailure(call, language, "PROJECT_ADAPTER_ARGUMENTS",
                            "Project adapter ${module.id} has no target parameter for ${parameter.name}")
                }
                binding.parameters.forEach { parameter ->
                    val index = call.symbol.owner.valueParameters.indexOf(sourceParameters[parameter.sourceName]
                        ?: projectFailure(call, language, "PROJECT_ADAPTER_ARGUMENTS",
                            "Project adapter ${module.id} source parameter is missing: ${parameter.sourceName}"))
                    val value = call.getValueArgument(index)
                    if (value == null) {
                        if (!parameter.optional) projectFailure(call, language, "PROJECT_ADAPTER_ARGUMENTS",
                            "Project adapter ${module.id} requires argument ${parameter.sourceName}")
                    } else {
                        val actual = language.type(value.type)
                        if (!adapterTargetTypeMatches(parameter.targetType, actual)) projectFailure(call, language,
                            "PROJECT_ADAPTER_ARGUMENTS", "Project adapter ${module.id} argument ${parameter.sourceName} " +
                                "requires ${parameter.targetType}, resolved $actual")
                    }
                }
                binding.contentSlot?.let { slot ->
                    val index = call.symbol.owner.valueParameters.indexOf(sourceParameters[slot.sourceName]
                        ?: projectFailure(call, language, "PROJECT_ADAPTER_ARGUMENTS",
                            "Project adapter ${module.id} content slot is missing: ${slot.sourceName}"))
                    val value = call.getValueArgument(index)
                    if (value == null) {
                        if (slot.required) projectFailure(call, language, "PROJECT_ADAPTER_ARGUMENTS",
                            "Project adapter ${module.id} requires content slot ${slot.sourceName}")
                    } else {
                        val function = lambda(value, scope)
                        if (function == null || function.valueParameters.isNotEmpty() || !function.returnType.isUnit())
                            projectFailure(call, language, "PROJECT_ADAPTER_ARGUMENTS",
                                "Project adapter ${module.id} content slot ${slot.sourceName} requires () -> Unit")
                    }
                }
            }

            private fun lowerProject(call: IrCall, language: Language, scope: Scope): EtsExpression? {
                val (binding, targetType) = projectBinding(call, language, scope, AdapterInputConsumption.VALUE)
                    ?: return null
                val value = delegate.lower(call, language, scope)
                    ?: projectFailure(call, language, "PROJECT_ADAPTER_MISSING",
                        "Project adapter ${module.id} declared the call but supplied no target value")
                if (value.type == EtsTypes.VOID) projectFailure(call, language, "PROJECT_ADAPTER_VOID_RESULT",
                    "Project adapter ${module.id} returned void for value call ${binding.source.symbol}")
                if (!adapterTargetTypeMatches(targetType, value.type)) projectFailure(call, language,
                    "PROJECT_ADAPTER_RETURN_TYPE", "Project adapter ${module.id} returned ${value.type}, expected $targetType")
                used.add(module.id)
                return value
            }

            private fun lowerProjectStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                projectBinding(call, language, scope, AdapterInputConsumption.STATEMENT) ?: return null
                val statements = delegate.lowerStatement(call, language, scope)
                    ?: delegate.lower(call, language, scope)?.let { value ->
                        if (value.type != EtsTypes.VOID) projectFailure(call, language,
                            "PROJECT_ADAPTER_RETURN_TYPE", "Project adapter ${module.id} returned ${value.type}, expected void")
                        listOf(EtsExpressionStatement(value))
                    } ?: projectFailure(call, language, "PROJECT_ADAPTER_MISSING",
                        "Project adapter ${module.id} declared the call but supplied no target statement")
                if (statements.isEmpty()) projectFailure(call, language, "PROJECT_ADAPTER_MISSING",
                    "Project adapter ${module.id} supplied an empty target statement result")
                used.add(module.id)
                return statements
            }

            private fun lowerProjectUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                projectBinding(call, language, scope, AdapterInputConsumption.UI) ?: return null
                val statements = delegate.lowerUi(call, language, scope)
                    ?: projectFailure(call, language, "PROJECT_ADAPTER_MISSING",
                        "Project adapter ${module.id} declared the component but supplied no target UI")
                if (statements.isEmpty()) projectFailure(call, language, "PROJECT_ADAPTER_MISSING",
                    "Project adapter ${module.id} supplied an empty target UI result")
                used.add(module.id)
                return statements
            }

            override fun mapType(type: IrType, language: Language): EtsType? =
                if (ui == null && type.classOrNull?.owner?.let(::symbolName) in module.sourceTypes)
                    track(delegate.mapType(type, language)) else null

            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
                if (ui == null && !reusableSourceBody(call))
                    lowerProject(call, language, scope) ?: if (claimed(call))
                        track(delegate.lower(call, language, scope)) else null else null

            override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? =
                if (ui == null && symbolName(call.symbol.owner) in module.sourceCalls && !reusableSourceBody(call))
                    track(delegate.lowerConstructor(call, language, scope)) else null

            override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? =
                if (ui == null && symbolName(value.symbol.owner) in module.sourceTypes)
                    track(delegate.lowerObject(value, language, scope)) else null

            override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? =
                if (ui == null && symbolName(value.symbol.owner) in module.sourceFields)
                    track(delegate.lowerField(value, language, scope)) else null

            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? =
                if (ui == null && !reusableSourceBody(call))
                    lowerProjectStatement(call, language, scope) ?: if (claimed(call))
                        track(delegate.lowerStatement(call, language, scope)) else null else null

            override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? =
                if (ui != null && !reusableSourceBody(call))
                    lowerProjectUi(call, language, scope) ?: if (claimed(call))
                        track(delegate.lowerUi(call, language, scope)) else null
                else if (ui != null && claimed(call)) track(delegate.lowerUi(call, language, scope)) else null
        }
    }

    fun manifest(): AdapterManifest = adapterManifest(ordered)

    fun manifestJson(): String = manifest().json()

    companion object {
        fun load(): AdapterModules = try {
            AdapterModules(ServiceLoader.load(AdapterModule::class.java).toList())
        } catch (failure: ServiceConfigurationError) {
            throw IllegalArgumentException("Cannot load adapter module: ${failure.message}", failure)
        }
    }
}

private data class AdapterProjectInputKey(
    val source: AdapterCallIdentity,
    val resolvedSourceReturnType: String,
    val targetReturnType: EtsType,
    val consumption: AdapterInputConsumption,
)

private fun projectFailure(call: IrCall, language: Language, code: String, message: String): Nothing =
    throw Unsupported(Diagnostic(code, message, language.source(call)))

private fun adapterTargetTypeMatches(expected: EtsType, actual: EtsType): Boolean = when (expected) {
    is EtsCapturedType -> actual is EtsCapturedType &&
        adapterTargetTypeMatches(expected.readType, actual.readType) &&
        adapterTargetTypeMatches(expected.writeType, actual.writeType)
    is EtsNamedType -> actual is EtsNamedType && expected.name == actual.name &&
        (expected.symbolId == null || expected.symbolId == actual.symbolId) &&
        expected.arguments.size == actual.arguments.size &&
        expected.arguments.zip(actual.arguments).all { (left, right) -> adapterTargetTypeMatches(left, right) }
    is EtsRecordType -> actual is EtsRecordType && expected.name == actual.name && expected.fields.keys == actual.fields.keys &&
        expected.fields.all { (name, type) -> adapterTargetTypeMatches(type, actual.fields.getValue(name)) }
    is EtsTypeParameterType -> actual is EtsTypeParameterType && expected.name == actual.name &&
        (expected.id.isBlank() || expected.id == actual.id)
    is EtsFunctionType -> actual is EtsFunctionType && expected.parameters.size == actual.parameters.size &&
        expected.parameters.zip(actual.parameters).all { (left, right) -> adapterTargetTypeMatches(left, right) } &&
        adapterTargetTypeMatches(expected.result, actual.result)
    is EtsNullableType -> actual is EtsNullableType && adapterTargetTypeMatches(expected.inner, actual.inner)
    is EtsTupleType -> actual is EtsTupleType && expected.elements.size == actual.elements.size &&
        expected.elements.zip(actual.elements).all { (left, right) -> adapterTargetTypeMatches(left, right) }
}
