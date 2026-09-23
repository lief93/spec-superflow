package dev.ets

data class AdapterManifest(val schemaVersion: Int, val modules: List<AdapterModuleManifest>) {
    fun json(): String = encodeJson(linkedMapOf(
        "schemaVersion" to schemaVersion,
        "modules" to modules.map(AdapterModuleManifest::jsonValue),
    )) + "\n"
}

data class AdapterModuleManifest(
    val id: String,
    val inputs: List<AdapterInputManifest>,
    val targetCalls: List<AdapterTargetCallManifest>,
    val targetValues: List<AdapterTargetValueManifest>,
    val imports: List<AdapterImportManifest>,
) {
    internal fun jsonValue() = linkedMapOf(
        "id" to id,
        "inputs" to inputs.map(AdapterInputManifest::jsonValue),
        "targetCalls" to targetCalls.map(AdapterTargetCallManifest::jsonValue),
        "targetValues" to targetValues.map(AdapterTargetValueManifest::jsonValue),
        "imports" to imports.map(AdapterImportManifest::jsonValue),
    )
}

data class AdapterInputManifest(
    val kind: String,
    val consumption: String,
    val source: AdapterSourceManifest,
    val resolvedSourceReturnType: String,
    val targetParameters: List<AdapterTargetParameterManifest>,
    val explicitArguments: Int,
    val targetReturnType: String,
    val targetId: String?,
    val contentSlot: AdapterContentSlotManifest?,
    val requiredScope: String?,
) {
    internal fun jsonValue() = linkedMapOf(
        "kind" to kind,
        "consumption" to consumption,
        "source" to source.jsonValue(),
        "resolvedSourceReturnType" to resolvedSourceReturnType,
        "targetParameters" to targetParameters.map(AdapterTargetParameterManifest::jsonValue),
        "explicitArguments" to explicitArguments,
        "targetReturnType" to targetReturnType,
        "targetId" to targetId,
        "contentSlot" to contentSlot?.jsonValue(),
        "requiredScope" to requiredScope,
    )
}

data class AdapterSourceManifest(
    val symbol: String,
    val typeParameters: Int,
    val dispatchReceiver: String?,
    val extensionReceiver: String?,
    val parameters: List<String>,
    val returnType: String,
    val suspend: Boolean,
) {
    internal fun jsonValue() = linkedMapOf(
        "symbol" to symbol,
        "typeParameters" to typeParameters,
        "dispatchReceiver" to dispatchReceiver,
        "extensionReceiver" to extensionReceiver,
        "parameters" to parameters,
        "returnType" to returnType,
        "suspend" to suspend,
    )
}

data class AdapterTargetParameterManifest(val sourceName: String, val targetType: String, val optional: Boolean) {
    internal fun jsonValue() = linkedMapOf(
        "sourceName" to sourceName,
        "targetType" to targetType,
        "optional" to optional,
    )
}

data class AdapterContentSlotManifest(val sourceName: String, val required: Boolean) {
    internal fun jsonValue() = linkedMapOf("sourceName" to sourceName, "required" to required)
}

data class AdapterTargetCallManifest(
    val id: String,
    val name: String,
    val parameters: List<String>,
    val returnType: String,
) {
    internal fun jsonValue() = linkedMapOf(
        "id" to id,
        "name" to name,
        "parameters" to parameters,
        "returnType" to returnType,
    )
}

data class AdapterTargetValueManifest(val id: String, val name: String, val type: String) {
    internal fun jsonValue() = linkedMapOf("id" to id, "name" to name, "type" to type)
}

data class AdapterImportManifest(val module: String, val name: String, val alias: String?, val default: Boolean) {
    internal fun jsonValue() = linkedMapOf(
        "module" to module,
        "name" to name,
        "alias" to alias,
        "default" to default,
    )
}

internal fun adapterManifest(modules: List<AdapterModule>) = AdapterManifest(1, modules.map { module ->
    AdapterModuleManifest(
        module.id,
        module.projectInputs.map { input ->
            AdapterInputManifest(
                input.kind.name.lowercase(),
                input.consumption.name.lowercase(),
                input.source.let { source -> AdapterSourceManifest(source.symbol, source.typeParameters,
                    source.dispatchReceiver, source.extensionReceiver, source.parameters, source.returnType, source.suspend) },
                input.resolvedSourceReturnType,
                input.parameters.map { AdapterTargetParameterManifest(it.sourceName,
                    adapterManifestType(it.targetType), it.optional) },
                input.explicitArguments,
                adapterManifestType(input.targetReturnType),
                input.targetId,
                input.contentSlot?.let { AdapterContentSlotManifest(it.sourceName, it.required) },
                input.requiredScope,
            )
        },
        module.targetCalls.map { target -> AdapterTargetCallManifest(target.id, target.name,
            target.signature.parameters.map(::adapterManifestType), adapterManifestType(target.signature.result)) },
        module.targetValues.map { target -> AdapterTargetValueManifest(target.id, target.name,
            adapterManifestType(target.type)) },
        module.imports.map { AdapterImportManifest(it.module, it.name, it.alias, it.default) },
    )
})

private fun adapterManifestType(type: EtsType): String = when (type) {
    is EtsCapturedType -> "captured<${adapterManifestType(type.readType)},${adapterManifestType(type.writeType)}>"
    is EtsNamedType -> type.name + (type.symbolId?.let { "#$it" } ?: "") +
        if (type.arguments.isEmpty()) "" else type.arguments.joinToString(",", "<", ">", transform = ::adapterManifestType)
    is EtsRecordType -> type.fields.entries.joinToString(",", "${type.name}{", "}") {
        "${it.key}:${adapterManifestType(it.value)}"
    }
    is EtsTypeParameterType -> "${type.name}#${type.id}"
    is EtsFunctionType -> type.parameters.joinToString(",", "(", ")->${adapterManifestType(type.result)}",
        transform = ::adapterManifestType)
    is EtsNullableType -> "${adapterManifestType(type.inner)}?"
    is EtsTupleType -> type.elements.joinToString(",", "[", "]", transform = ::adapterManifestType)
}

private fun encodeJson(value: Any?, indent: Int = 0): String = when (value) {
    null -> "null"
    is String -> buildString {
        append('"')
        value.forEach { character -> when (character) {
            '"' -> append("\\\"")
            '\\' -> append("\\\\")
            '\b' -> append("\\b")
            '\u000c' -> append("\\f")
            '\n' -> append("\\n")
            '\r' -> append("\\r")
            '\t' -> append("\\t")
            else -> if (character.code < 0x20) append("\\u%04x".format(character.code)) else append(character)
        } }
        append('"')
    }
    is Number, is Boolean -> value.toString()
    is List<*> -> if (value.isEmpty()) "[]" else value.joinToString(",\n",
        "[\n", "\n${" ".repeat(indent)}]") { " ".repeat(indent + 2) + encodeJson(it, indent + 2) }
    is Map<*, *> -> if (value.isEmpty()) "{}" else value.entries.joinToString(",\n",
        "{\n", "\n${" ".repeat(indent)}}") { (key, item) ->
        " ".repeat(indent + 2) + encodeJson(key as String) + ": " + encodeJson(item, indent + 2)
    }
    else -> error("Unsupported adapter manifest JSON value: ${value.javaClass.name}")
}
