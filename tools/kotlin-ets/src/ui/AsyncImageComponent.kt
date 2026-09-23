package dev.ets

private val asyncImageSource = SourceSpan("EtsAsyncImage.kt", 0, 0)
internal val asyncImageSymbol = etsClassSymbol("EtsAsyncImage", asyncImageSource)

internal fun asyncImageFiles(program: EtsProgram): List<EtsFile> {
    var used = false
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
        if (it is EtsReference && it.symbol.id == asyncImageSymbol.id) used = true
    } } }
    return if (used) listOf(EtsFile(asyncImageSource.file!!, listOf(asyncImageComponent()))) else emptyList()
}

/** The native Image owns IO/decoding; this component owns request and crossfade state. */
private fun asyncImageComponent(): EtsClass {
    val at = asyncImageSource
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun bool(value: Boolean) = EtsLiteral(value, EtsTypes.BOOLEAN, at)
    fun text(value: String) = EtsLiteral(value, EtsTypes.STRING, at)
    fun nil() = EtsLiteral(null, EtsTypes.NULL, at)
    fun enum(type: String, name: String): EtsExpression {
        val target = EtsNamedType(type)
        return EtsMember(EtsReference(EtsSymbol("arkui:$type", type, target, at, true)), name, target, at)
    }
    fun binary(op: String, left: EtsExpression, right: EtsExpression, type: EtsType = EtsTypes.BOOLEAN) = EtsBinary(op, left, right, type, at)
    fun parameter(name: String, type: EtsType) = EtsParameter(EtsSymbol("asyncImage:param:$name", name, type, at))
    fun native(name: String, args: List<EtsExpression>, result: EtsType = EtsTypes.VOID) = EtsCall(
        EtsReference(EtsSymbol("arkui:$name", name, EtsFunctionType(args.map { it.type }, result), at, true)), args, result, at)
    fun field(name: String, type: EtsType, initial: EtsExpression, state: Boolean = false, prop: Boolean = false, watch: String? = null) =
        EtsField(EtsSymbol("asyncImage:field:$name", name, type, at), initial, state = state, prop = prop, watch = watch)
    val fields = listOf(
        field("request", imageRequestType, EtsNew(imageRequestType, listOf(nil(), number(0), nil()), at), prop = true, watch = "requestChanged"),
        field("placeholder", EtsNullableType(ImageResources.RESOURCE), nil(), prop = true),
        field("error", EtsNullableType(ImageResources.RESOURCE), nil(), prop = true),
        field("fit", EtsNamedType("ImageFit"), enum("ImageFit", "Contain"), prop = true),
        field("url", EtsNullableType(EtsTypes.STRING), nil()),
        field("duration", EtsTypes.NUMBER, number(0)),
        field("svg", EtsTypes.BOOLEAN, bool(false)),
        field("generation", EtsTypes.NUMBER, number(0)),
        field("active", EtsTypes.BOOLEAN, bool(false)),
        field("completed", EtsTypes.BOOLEAN, bool(false)),
        field("tokens", EtsNamedType("Array", listOf(EtsTypes.NUMBER)), EtsArray(emptyList(), EtsTypes.NUMBER, at), state = true),
        field("progress", EtsTypes.NUMBER, number(0), state = true),
        field("showPlaceholder", EtsTypes.BOOLEAN, bool(false), state = true),
        field("showError", EtsTypes.BOOLEAN, bool(false), state = true),
    )
    val self = EtsReference(EtsSymbol("asyncImage:this", "this", asyncImageSymbol.type, at, true))
    fun ref(name: String) = fields.single { it.symbol.name == name }.let { EtsMember(self, name, it.symbol.type, at, it.symbol.id) }
    fun request(name: String, type: EtsType) = EtsMember(ref("request"), name, type, at)
    fun assign(name: String, value: EtsExpression) = EtsExpressionStatement(EtsAssignment(ref(name), value, at))
    fun invoke(name: String, arguments: List<EtsExpression> = emptyList()) = EtsExpressionStatement(EtsCall(
        EtsMember(self, name, EtsFunctionType(arguments.map { it.type }, EtsTypes.VOID), at), arguments, EtsTypes.VOID, at))
    fun guard(condition: EtsExpression) = EtsIf(listOf(EtsBranch(condition, listOf(EtsReturn(null, at)))), at)
    fun callback(body: List<EtsStatement>) = EtsLambda(emptyList(), body, EtsTypes.VOID, at)
    fun method(name: String, parameters: List<EtsParameter> = emptyList(), body: List<EtsStatement>) =
        EtsFunction(name, parameters, EtsTypes.VOID, body, at, kind = EtsFunctionKind.METHOD)
    val data = request("requestData", EtsNullableType(EtsTypes.STRING))
    val duration = request("crossfadeMillis", EtsTypes.NUMBER)
    val svg = binary("!==", request("decoder", EtsNullableType(svgDecoderType)), nil())
    val increment = assign("generation", binary("+", ref("generation"), number(1), EtsTypes.NUMBER))
    val changed = method("requestChanged", body = listOf(
        guard(binary("&&", binary("&&", binary("===", ref("url"), data), binary("===", ref("duration"), duration)), binary("===", ref("svg"), svg))),
        increment, assign("url", data), assign("duration", duration), assign("svg", svg),
        assign("completed", bool(false)), assign("progress", number(0)), assign("showPlaceholder", binary("!==", data, nil())),
        assign("showError", bool(false)),
        assign("tokens", EtsConditional(binary("===", data, nil()), EtsArray(emptyList(), EtsTypes.NUMBER, at),
            EtsArray(listOf(ref("generation")), EtsTypes.NUMBER, at), EtsNamedType("Array", listOf(EtsTypes.NUMBER)), at)),
    ))
    val token = parameter("token", EtsTypes.NUMBER)
    val tokenRef = EtsReference(token.symbol)
    val stale = binary("||", EtsUnary("!", ref("active"), EtsTypes.BOOLEAN, at), binary("!==", tokenRef, ref("generation")))
    val finish = method("finish", listOf(token), listOf(guard(stale), assign("showPlaceholder", bool(false))))
    val animation = EtsObject(linkedMapOf("duration" to ref("duration"), "curve" to enum("Curve", "Linear"),
        "onFinish" to callback(listOf(invoke("finish", listOf(tokenRef))))), EtsRecordType("AnimateParam", linkedMapOf(
            "duration" to EtsTypes.NUMBER, "curve" to EtsNamedType("Curve"), "onFinish" to EtsFunctionType(emptyList(), EtsTypes.VOID))), at)
    val loaded = method("loaded", listOf(token), listOf(
        guard(binary("||", stale, ref("completed"))), assign("completed", bool(true)),
        EtsIf(listOf(EtsBranch(binary(">", ref("duration"), number(0)), listOf(EtsExpressionStatement(native("animateTo", listOf(
            animation, callback(listOf(assign("progress", number(1))))))))),
            EtsBranch(null, listOf(assign("progress", number(1)), assign("showPlaceholder", bool(false))))), at),
    ))
    val failed = method("failed", listOf(token), listOf(guard(stale), assign("completed", bool(true)),
        assign("progress", number(0)), assign("showPlaceholder", bool(false)),
        assign("showError", binary("!==", ref("error"), nil()))))
    fun image(source: EtsExpression, opacity: EtsExpression, attributes: List<EtsCall> = emptyList()) = EtsUiElement(native("Image", listOf(source)),
        attributes = listOf(native("width", listOf(text("100%"))), native("height", listOf(text("100%"))),
            native("objectFit", listOf(ref("fit"))), native("opacity", listOf(opacity)),
            native("accessibilityLevel", listOf(text("no")))) + attributes)
    val placeholder = EtsIf(listOf(EtsBranch(binary("&&", ref("showPlaceholder"), binary("!==", ref("placeholder"), nil())),
        listOf(image(EtsCast(ref("placeholder"), ImageResources.RESOURCE, at), binary("-", number(1), ref("progress"), EtsTypes.NUMBER))))), at)
    val error = EtsIf(listOf(EtsBranch(binary("&&", ref("showError"), binary("!==", ref("error"), nil())),
        listOf(image(EtsCast(ref("error"), ImageResources.RESOURCE, at), number(1))))), at)
    // Recreate the loading Image for each request; callbacks retain that request's token.
    val images = EtsUiForEach(ref("tokens"), token, listOf(image(EtsCast(ref("url"), EtsTypes.STRING, at), ref("progress"), listOf(
        native("onComplete", listOf(callback(listOf(invoke("loaded", listOf(tokenRef)))))),
        native("onError", listOf(callback(listOf(invoke("failed", listOf(tokenRef))))))
    ))), at)
    val build = EtsFunction("build", emptyList(), EtsTypes.VOID,
        listOf(EtsUiElement(native("Stack", emptyList()), listOf(placeholder, images, error), listOf(
            native("width", listOf(text("100%"))), native("height", listOf(text("100%")))))), at,
        kind = EtsFunctionKind.METHOD, build = true)
    return EtsClass(asyncImageSymbol.name, fields + listOf(
        method("aboutToAppear", body = listOf(assign("active", bool(true)), invoke("requestChanged"))),
        method("aboutToDisappear", body = listOf(assign("active", bool(false)), increment)),
        changed, loaded, failed, finish, build), at, exported = true, component = true)
}
