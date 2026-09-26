package dev.ets

/** Typed target contract shared by framework lowerings and native UI backends. */
val etsTextStyleType: EtsNamedType = etsClassSymbol("EtsTextStyle",
    SourceSpan("EtsTextStyle.kt", 0, 0)).type as EtsNamedType

private val etsFontFamilyType = etsClassSymbol("EtsFontFamily",
    SourceSpan("EtsFontValues.kt", 0, 0)).type as EtsNamedType
private val etsLineHeightStyleType = etsClassSymbol("EtsLineHeightStyle",
    SourceSpan("EtsLineHeightStyle.kt", -1, -1)).type as EtsNamedType

val etsTextStyleFields: LinkedHashMap<String, EtsType> = linkedMapOf(
    "color" to EtsTypes.NUMBER,
    "fontSize" to EtsTypes.NUMBER,
    "fontWeight" to EtsTypes.NUMBER,
    "fontStyle" to EtsTypes.NUMBER,
    "fontFamily" to etsFontFamilyType,
    "letterSpacing" to EtsTypes.NUMBER,
    "textDecoration" to EtsNamedType("TextDecorationType"),
    "textAlign" to EtsNamedType("TextAlign"),
    "lineHeight" to EtsTypes.NUMBER,
    "lineHeightStyle" to etsLineHeightStyleType,
)

val etsTextStyleArgumentOrder: List<String> = listOf(
    "color", "fontSize", "fontStyle", "fontWeight", "fontFamily",
    "letterSpacing", "textDecoration", "textAlign", "lineHeight",
    "overflow", "maxLines", "style",
)

val etsTextStyleModifierType: EtsNamedType = etsClassSymbol("EtsTextStyleModifier",
    SourceSpan("EtsTextStyleModifier.kt", 0, 0)).type as EtsNamedType

private val etsTextStyleFactorySymbol = etsFunctionSymbol("__etsTextStyleModifier",
    etsTextStyleArgumentOrder.map { name -> when (name) {
        "style" -> etsTextStyleType
        "overflow" -> EtsNamedType("TextOverflow")
        "maxLines" -> EtsTypes.NUMBER
        else -> EtsNullableType(etsTextStyleFields.getValue(name))
    } } + EtsTypes.NUMBER, etsTextStyleModifierType,
    SourceSpan("EtsTextStyleModifier.kt", 0, 0))

fun etsTextStyleModifier(arguments: List<EtsExpression>, at: SourceSpan): EtsExpression {
    require(arguments.size == etsTextStyleArgumentOrder.size + 1) {
        "Text style modifier requires ${etsTextStyleArgumentOrder.size + 1} arguments; got ${arguments.size}"
    }
    return EtsCall(EtsReference(etsTextStyleFactorySymbol, at), arguments,
        etsTextStyleModifierType, at)
}
