package dev.ets

private val renderStyleSource = SourceSpan("EtsTextStyleModifier.kt", 0, 0)
private val textAttributeType = EtsNamedType("TextAttribute", external = true)
private val modifierContract = attributeModifierContract()
internal val textAttributeModifierType = (modifierContract.symbol.type as EtsNamedType).copy(arguments = listOf(textAttributeType), external = true)
internal val textStyleModifierType = etsClassSymbol("EtsTextStyleModifier", renderStyleSource).type as EtsNamedType
internal val textStyleArgumentOrder = listOf("color", "fontSize", "fontStyle", "fontWeight", "fontFamily",
    "letterSpacing", "textDecoration", "textAlign", "lineHeight", "overflow", "maxLines", "style")
private val styleFactory = textStyleFactory()

internal fun textStyleModifier(arguments: List<EtsExpression>, at: SourceSpan): EtsExpression =
    EtsCall(EtsReference(styleFactory.symbol, at), arguments, textStyleModifierType, at)

internal fun textStyleRenderingFiles(program: EtsProgram): List<EtsFile> {
    var used = false
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsReference && node.symbol.id == styleFactory.symbol.id) used = true
    } } }
    return if (used) listOf(EtsFile(renderStyleSource.file!!, listOf(styleModifierClass(), styleFactory))) else emptyList()
}

internal fun textStyleNativeContracts(program: EtsProgram): List<EtsClass> =
    if (textStyleRenderingFiles(program).isNotEmpty()) listOf(modifierContract) else emptyList()

private fun attributeModifierContract(): EtsClass {
    val at = SourceSpan("ArkUiTextContract", 0, 0)
    val parameter = EtsTypeParameter("arkui:AttributeModifier:T", "T")
    val type = EtsTypeParameterType(parameter.id, parameter.name)
    val apply = EtsFunction("applyNormalAttribute", listOf(EtsParameter(EtsSymbol("arkui:modifier:instance", "instance", type, at))),
        EtsTypes.VOID, emptyList(), at, kind = EtsFunctionKind.METHOD, abstract = true)
    return EtsClass("AttributeModifier", listOf(apply), at, typeParameters = listOf(parameter), kind = EtsClassKind.INTERFACE)
}

private fun textStyleFactory(): EtsFunction {
    val at = renderStyleSource
    val parameters = textStyleArgumentOrder.map { name ->
        val type = when (name) {
            "style" -> textStyleType
            "overflow" -> EtsNamedType("TextOverflow")
            "maxLines" -> EtsTypes.NUMBER
            else -> EtsNullableType(textStyleFields.getValue(name))
        }
        EtsParameter(EtsSymbol("styleFactory:$name", name, type, at))
    } + EtsParameter(EtsSymbol("styleFactory:fallbackColor", "fallbackColor", EtsTypes.NUMBER, at))
    fun ref(name: String) = EtsReference(parameters.single { it.symbol.name == name }.symbol)
    val overrides = EtsNew(textStyleType, textStyleFields.keys.map { name ->
        if (name in textStyleArgumentOrder) ref(name) else EtsLiteral(null, EtsTypes.NULL, at)
    }, at)
    val instance = EtsNew(textStyleModifierType, listOf(ref("style"), overrides, ref("fallbackColor"), ref("overflow"), ref("maxLines")), at)
    return EtsFunction("__etsTextStyleModifier", parameters, textStyleModifierType, listOf(EtsReturn(instance, at)), at, exported = true)
}

private fun styleModifierClass(): EtsClass {
    val at = renderStyleSource
    fun nativeEnum(type: String, name: String): EtsExpression {
        val target = EtsNamedType(type)
        return EtsMember(EtsReference(EtsSymbol("arkui:$type", type, target, at, true)), name, target, at)
    }
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun nil() = EtsLiteral(null, EtsTypes.NULL, at)
    val parameters = listOf(EtsParameter(EtsSymbol("renderStyle:style", "style", textStyleType, at)),
        EtsParameter(EtsSymbol("renderStyle:overrides", "overrides", textStyleType, at)),
        EtsParameter(EtsSymbol("renderStyle:fallbackColor", "fallbackColor", EtsTypes.NUMBER, at)),
        EtsParameter(EtsSymbol("renderStyle:overflow", "overflow", EtsNamedType("TextOverflow"), at)),
        EtsParameter(EtsSymbol("renderStyle:maxLines", "maxLines", EtsTypes.NUMBER, at)))
    val receiver = EtsReference(EtsSymbol("renderStyle:this", "this", textStyleModifierType, at, true))
    val defaults = mapOf("color" to EtsReference(parameters[2].symbol), "fontSize" to number(14),
        "fontWeight" to number(400), "fontStyle" to number(0), "letterSpacing" to number(0), "textAlign" to nativeEnum("TextAlign", "Start"),
        "textDecoration" to nativeEnum("TextDecorationType", "None"))
    val fields = textStyleFields.map { (name, type) -> EtsField(EtsSymbol("renderStyle:field:$name", name,
        if (name in defaults) type else EtsNullableType(type), at), readonly = true) } + listOf(
        EtsField(EtsSymbol("renderStyle:field:overflow", "overflow", EtsNamedType("TextOverflow"), at), readonly = true),
        EtsField(EtsSymbol("renderStyle:field:maxLines", "maxLines", EtsTypes.NUMBER, at), readonly = true))
    fun field(name: String): EtsMember = fields.single { it.symbol.name == name }.let {
        EtsMember(receiver, name, it.symbol.type, at, it.symbol.id)
    }
    val body = textStyleFields.map { (name, type) ->
        val nullable = EtsNullableType(type)
        val supplied = EtsMember(EtsReference(parameters[1].symbol), name, nullable, at)
        val base = EtsMember(EtsReference(parameters[0].symbol), name, nullable, at)
        val merged = EtsBinary("??", supplied, base, nullable, at)
        val value = defaults[name]?.let { EtsBinary("??", merged, it, type, at) } ?: merged
        EtsExpressionStatement(EtsAssignment(field(name), value, at))
    } + listOf(EtsExpressionStatement(EtsAssignment(field("overflow"), EtsReference(parameters[3].symbol), at)),
        EtsExpressionStatement(EtsAssignment(field("maxLines"), EtsReference(parameters[4].symbol), at)))
    val instance = EtsSymbol("renderStyle:instance", "instance", textAttributeType, at)
    fun apply(name: String, value: EtsExpression): EtsStatement = EtsExpressionStatement(EtsCall(
        EtsMember(EtsReference(instance), name, EtsFunctionType(listOf(value.type), instance.type), at), listOf(value), instance.type, at))
    val nativeStyle = EtsConditional(EtsBinary("===", field("fontStyle"), number(0), EtsTypes.BOOLEAN, at),
        nativeEnum("FontStyle", "Normal"), nativeEnum("FontStyle", "Italic"), EtsNamedType("FontStyle"), at)
    val lineHeightStyle = EtsCast(field("lineHeightStyle"), lineHeightStyleType, at)
    val supportedLineHeightStyle = EtsBinary("&&", EtsBinary("&&",
        EtsBinary("===", EtsMember(lineHeightStyle, "alignment", lineHeightAlignmentType, at),
            lineHeightAlignment("Center", at), EtsTypes.BOOLEAN, at),
        EtsBinary("===", EtsMember(lineHeightStyle, "trim", lineHeightTrimType, at),
            lineHeightTrim("None", at), EtsTypes.BOOLEAN, at), EtsTypes.BOOLEAN, at),
        EtsBinary("===", EtsMember(lineHeightStyle, "mode", lineHeightModeType, at),
            lineHeightMode("Fixed", at), EtsTypes.BOOLEAN, at), EtsTypes.BOOLEAN, at)
    val applyHalfLeading = EtsIf(listOf(EtsBranch(EtsBinary("||",
        EtsBinary("===", field("lineHeightStyle"), nil(), EtsTypes.BOOLEAN, at),
        supportedLineHeightStyle, EtsTypes.BOOLEAN, at), listOf(apply("halfLeading",
        EtsLiteral(true, EtsTypes.BOOLEAN, at))))), at)
    val overflowType = EtsRecordType("TextOverflowOptions", mapOf("overflow" to EtsNamedType("TextOverflow")))
    val applyBody = listOf(apply("fontColor", field("color")), apply("fontSize", field("fontSize")),
        apply("decoration", EtsObject(linkedMapOf("type" to field("textDecoration"), "color" to field("color")),
            EtsRecordType("DecorationStyleInterface", linkedMapOf("type" to textDecorationType, "color" to EtsTypes.NUMBER)), at)),
        apply("fontWeight", field("fontWeight")), apply("fontStyle", nativeStyle), apply("letterSpacing", field("letterSpacing")),
        apply("textAlign", field("textAlign")), applyHalfLeading,
        apply("maxLines", field("maxLines")), apply("textOverflow", EtsObject(mapOf("overflow" to field("overflow")), overflowType, at)),
        apply("lineHeight", EtsBinary("??", field("lineHeight"), number(0), EtsTypes.NUMBER, at)),
        EtsIf(listOf(EtsBranch(EtsBinary("!==", field("fontFamily"), nil(), EtsTypes.BOOLEAN, at),
            listOf(apply("fontFamily", nativeFontFamily(EtsCast(field("fontFamily"), fontFamilyType, at), field("fontWeight"), field("fontStyle"), at)))),
            EtsBranch(null, listOf(apply("fontFamily", EtsLiteral("HarmonyOS Sans", EtsTypes.STRING, at))))), at))
    return EtsClass(textStyleModifierType.name, fields + listOf(
        EtsFunction("constructor", parameters, EtsTypes.VOID, body, at, kind = EtsFunctionKind.CONSTRUCTOR),
        EtsFunction("applyNormalAttribute", listOf(EtsParameter(instance)), EtsTypes.VOID, applyBody, at, kind = EtsFunctionKind.METHOD)),
        at, exported = true, interfaces = listOf(textAttributeModifierType))
}
