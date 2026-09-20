package dev.ets

internal val spanStyleSource = SourceSpan("EtsSpanStyle.kt", 0, 0)
internal val spanStyleType = etsClassSymbol("EtsSpanStyle", spanStyleSource).type as EtsNamedType
internal val spanStyleFields = linkedMapOf(
    "color" to EtsNullableType(EtsTypes.NUMBER),
    "fontWeight" to EtsNullableType(EtsTypes.NUMBER),
)

internal val annotatedSpanSource = SourceSpan("EtsAnnotatedSpan.kt", 0, 0)
internal val annotatedSpanType = etsClassSymbol("EtsAnnotatedSpan", annotatedSpanSource).type as EtsNamedType
internal val annotatedSpanFields = linkedMapOf(
    "start" to EtsTypes.NUMBER,
    "end" to EtsTypes.NUMBER,
    "text" to EtsTypes.STRING,
    "color" to EtsNullableType(EtsTypes.NUMBER),
    "fontWeight" to EtsNullableType(EtsTypes.NUMBER),
    "tag" to EtsNullableType(EtsTypes.STRING),
    "annotation" to EtsNullableType(EtsTypes.STRING),
    "display" to EtsTypes.BOOLEAN,
)

internal val annotatedStringSource = SourceSpan("EtsAnnotatedString.kt", 0, 0)
internal val annotatedStringType = etsClassSymbol("EtsAnnotatedString", annotatedStringSource).type as EtsNamedType
internal val annotatedBuilderType = etsClassSymbol("EtsAnnotatedStringBuilder", annotatedStringSource).type as EtsNamedType
internal val annotatedSpansType = EtsNamedType("Array", listOf(annotatedSpanType))

internal val annotatedGetFunction: EtsFunction = annotatedGetFunction()

internal fun annotatedStringFiles(program: EtsProgram): List<EtsFile> {
    if (!usesAnnotatedString(program)) return emptyList()
    val at = annotatedStringSource
    fun valueClass(target: EtsNamedType, properties: Map<String, EtsType>, source: SourceSpan): EtsClass {
        val receiver = EtsReference(EtsSymbol("${target.name}:this", "this", target, source, true))
        val fields = properties.map { (name, type) -> EtsField(EtsSymbol("${target.name}:field:$name", name, type, source), readonly = true) }
        val parameters = properties.map { (name, type) -> EtsParameter(EtsSymbol("${target.name}:param:$name", name, type, source)) }
        val body = fields.zip(parameters).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
            EtsMember(receiver, field.symbol.name, field.symbol.type, source, field.symbol.id), EtsReference(parameter.symbol), source)) }
        return EtsClass(target.name, fields + EtsFunction("constructor", parameters, EtsTypes.VOID, body,
            source, kind = EtsFunctionKind.CONSTRUCTOR), source, exported = true)
    }
    val style = valueClass(spanStyleType, spanStyleFields, spanStyleSource)
    val span = valueClass(annotatedSpanType, annotatedSpanFields, annotatedSpanSource)
    val annotated = valueClass(annotatedStringType, linkedMapOf("text" to EtsTypes.STRING, "spans" to annotatedSpansType), at)
    return listOf(
        EtsFile(spanStyleSource.file!!, listOf(style)),
        EtsFile(annotatedSpanSource.file!!, listOf(span)),
        EtsFile(at.file!!, listOf(annotated, annotatedBuilderClass(), annotatedGetFunction)),
    )
}

private fun annotatedGetFunction(): EtsFunction {
    val at = annotatedStringSource
    val value = EtsParameter(EtsSymbol("annotatedGet:value", "value", annotatedStringType, at))
    val start = EtsParameter(EtsSymbol("annotatedGet:start", "start", EtsTypes.NUMBER, at))
    val end = EtsParameter(EtsSymbol("annotatedGet:end", "end", EtsTypes.NUMBER, at))
    val result = EtsSymbol("annotatedGet:result", "result", annotatedSpansType, at)
    val span = EtsSymbol("annotatedGet:span", "span", annotatedSpanType, at)
    val spanRef = EtsReference(span)
    val overlap = EtsBinary("&&",
        EtsBinary("<", EtsMember(spanRef, "start", EtsTypes.NUMBER, at), EtsReference(end.symbol), EtsTypes.BOOLEAN, at),
        EtsBinary(">", EtsMember(spanRef, "end", EtsTypes.NUMBER, at), EtsReference(start.symbol), EtsTypes.BOOLEAN, at),
        EtsTypes.BOOLEAN, at)
    val tagged = EtsBinary("!==", EtsMember(spanRef, "tag", EtsNullableType(EtsTypes.STRING), at),
        EtsLiteral(null, EtsTypes.NULL, at), EtsTypes.BOOLEAN, at)
    val callback = EtsLambda(listOf(EtsParameter(span)), listOf(
        EtsIf(listOf(EtsBranch(EtsBinary("&&", tagged, overlap, EtsTypes.BOOLEAN, at), listOf(
            EtsExpressionStatement(EtsCall(EtsMember(EtsReference(result), "push",
                EtsFunctionType(listOf(annotatedSpanType), EtsTypes.NUMBER), at),
                listOf(spanRef), EtsTypes.NUMBER, at))
        ))), at)
    ), EtsTypes.VOID, at)
    val iterate = EtsCall(EtsMember(EtsMember(EtsReference(value.symbol), "spans", annotatedSpansType, at), "forEach",
        EtsFunctionType(listOf(callback.type), EtsTypes.VOID), at), listOf(callback), EtsTypes.VOID, at)
    return EtsFunction("__etsAnnotatedGetStringAnnotations", listOf(value, start, end), annotatedSpansType, listOf(
        EtsVariable(result, EtsArray(emptyList(), annotatedSpanType, at), false),
        EtsExpressionStatement(iterate),
        EtsReturn(EtsReference(result), at),
    ), at, exported = true)
}

private fun annotatedBuilderClass(): EtsClass {
    val at = annotatedStringSource
    val receiver = EtsReference(EtsSymbol("annotatedBuilder:this", "this", annotatedBuilderType, at, true))
    fun field(name: String, type: EtsType) = EtsField(EtsSymbol("annotatedBuilder:field:$name", name, type, at), visibility = EtsVisibility.PRIVATE)
    val text = field("text", EtsTypes.STRING)
    val spans = field("spans", annotatedSpansType)
    val stack = field("stack", annotatedSpansType)
    fun member(field: EtsField) = EtsMember(receiver, field.symbol.name, field.symbol.type, at, field.symbol.id)
    fun n(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun str(value: String) = EtsLiteral(value, EtsTypes.STRING, at)
    fun nil() = EtsLiteral(null, EtsTypes.NULL, at)
    val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, listOf(
        EtsExpressionStatement(EtsAssignment(member(text), str(""), at)),
        EtsExpressionStatement(EtsAssignment(member(spans), EtsArray(emptyList(), annotatedSpanType, at), at)),
        EtsExpressionStatement(EtsAssignment(member(stack), EtsArray(emptyList(), annotatedSpanType, at), at)),
    ), at, kind = EtsFunctionKind.CONSTRUCTOR)
    val value = EtsParameter(EtsSymbol("annotatedBuilder:append", "value", EtsTypes.STRING, at))
    val start = EtsSymbol("annotatedBuilder:appendStart", "start", EtsTypes.NUMBER, at)
    val append = EtsFunction("append", listOf(value), EtsTypes.VOID, listOf(
        EtsVariable(start, EtsMember(member(text), "length", EtsTypes.NUMBER, at), false),
        EtsExpressionStatement(EtsAssignment(member(text), EtsBinary("+", member(text), EtsReference(value.symbol), EtsTypes.STRING, at), at)),
        EtsIf(listOf(EtsBranch(
            EtsBinary("===", EtsMember(member(stack), "length", EtsTypes.NUMBER, at), n(0), EtsTypes.BOOLEAN, at),
            listOf(EtsExpressionStatement(EtsCall(EtsMember(member(spans), "push",
                EtsFunctionType(listOf(annotatedSpanType), EtsTypes.NUMBER), at), listOf(
                    EtsNew(annotatedSpanType, listOf(
                        EtsReference(start), EtsMember(member(text), "length", EtsTypes.NUMBER, at),
                        EtsReference(value.symbol), nil(), nil(), nil(), nil(), EtsLiteral(true, EtsTypes.BOOLEAN, at),
                    ), at)), EtsTypes.NUMBER, at))),
        )), at),
    ), at, kind = EtsFunctionKind.METHOD)
    val style = EtsParameter(EtsSymbol("annotatedBuilder:style", "style", spanStyleType, at))
    fun push(kind: String, extra: Map<String, EtsExpression>): EtsFunction {
        val start = EtsMember(member(text), "length", EtsTypes.NUMBER, at)
        val fields = linkedMapOf(
            "start" to start,
            "end" to start,
            "text" to str(kind),
            "color" to (extra["color"] ?: nil()),
            "fontWeight" to (extra["fontWeight"] ?: nil()),
            "tag" to (extra["tag"] ?: nil()),
            "annotation" to (extra["annotation"] ?: nil()),
            "display" to EtsLiteral(kind == "style", EtsTypes.BOOLEAN, at),
        )
        val created = EtsNew(annotatedSpanType, annotatedSpanFields.keys.map { fields.getValue(it) }, at)
        return EtsFunction(if (kind == "style") "pushStyle" else "pushStringAnnotation",
            if (kind == "style") listOf(style) else listOf(
                EtsParameter(EtsSymbol("annotatedBuilder:tag", "tag", EtsTypes.STRING, at)),
                EtsParameter(EtsSymbol("annotatedBuilder:annotation", "annotation", EtsTypes.STRING, at))),
            EtsTypes.NUMBER, listOf(
                EtsExpressionStatement(EtsCall(EtsMember(member(stack), "push",
                    EtsFunctionType(listOf(annotatedSpanType), EtsTypes.NUMBER), at), listOf(created), EtsTypes.NUMBER, at)),
                EtsReturn(EtsBinary("-", EtsMember(member(stack), "length", EtsTypes.NUMBER, at), n(1), EtsTypes.NUMBER, at), at),
            ), at, kind = EtsFunctionKind.METHOD)
    }
    val pushStyle = push("style", mapOf(
        "color" to EtsMember(EtsReference(style.symbol), "color", EtsNullableType(EtsTypes.NUMBER), at),
        "fontWeight" to EtsMember(EtsReference(style.symbol), "fontWeight", EtsNullableType(EtsTypes.NUMBER), at),
    ))
    val pushAnnotation = push("annotation", mapOf(
        "tag" to EtsReference(EtsSymbol("annotatedBuilder:tag", "tag", EtsTypes.STRING, at)),
        "annotation" to EtsReference(EtsSymbol("annotatedBuilder:annotation", "annotation", EtsTypes.STRING, at)),
    ))
    val popped = EtsSymbol("annotatedBuilder:popped", "popped", EtsNullableType(annotatedSpanType), at)
    val range = EtsSymbol("annotatedBuilder:range", "range", annotatedSpanType, at)
    val current = EtsCast(EtsReference(popped), annotatedSpanType, at)
    val pop = EtsFunction("pop", emptyList(), EtsTypes.VOID, listOf(
        EtsVariable(popped, EtsCall(EtsMember(member(stack), "pop",
            EtsFunctionType(emptyList(), EtsNullableType(annotatedSpanType)), at), emptyList(),
            EtsNullableType(annotatedSpanType), at), false),
        EtsIf(listOf(EtsBranch(
            EtsBinary("!==", EtsReference(popped), nil(), EtsTypes.BOOLEAN, at),
            listOf(
                EtsVariable(range, EtsNew(annotatedSpanType, listOf(
                    EtsMember(current, "start", EtsTypes.NUMBER, at),
                    EtsMember(member(text), "length", EtsTypes.NUMBER, at),
                    EtsCall(EtsMember(member(text), "substring",
                        EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.STRING), at),
                        listOf(EtsMember(current, "start", EtsTypes.NUMBER, at),
                            EtsMember(member(text), "length", EtsTypes.NUMBER, at)), EtsTypes.STRING, at),
                    EtsMember(current, "color", EtsNullableType(EtsTypes.NUMBER), at),
                    EtsMember(current, "fontWeight", EtsNullableType(EtsTypes.NUMBER), at),
                    EtsMember(current, "tag", EtsNullableType(EtsTypes.STRING), at),
                    EtsMember(current, "annotation", EtsNullableType(EtsTypes.STRING), at),
                    EtsBinary("===", EtsMember(current, "tag", EtsNullableType(EtsTypes.STRING), at),
                        nil(), EtsTypes.BOOLEAN, at),
                ), at), false),
                EtsExpressionStatement(EtsCall(EtsMember(member(spans), "push",
                    EtsFunctionType(listOf(annotatedSpanType), EtsTypes.NUMBER), at),
                    listOf(EtsReference(range)), EtsTypes.NUMBER, at)),
            ))), at),
    ), at, kind = EtsFunctionKind.METHOD)
    val toString = EtsFunction("toAnnotatedString", emptyList(), annotatedStringType, listOf(
        EtsLoop("annotatedFlush", EtsBinary(">", EtsMember(member(stack), "length", EtsTypes.NUMBER, at), n(0), EtsTypes.BOOLEAN, at),
            listOf(EtsExpressionStatement(EtsCall(EtsMember(receiver, "pop", EtsFunctionType(emptyList(), EtsTypes.VOID), at),
                emptyList(), EtsTypes.VOID, at))), false, at),
        EtsReturn(EtsNew(annotatedStringType, listOf(member(text), member(spans)), at), at),
    ), at, kind = EtsFunctionKind.METHOD)
    return EtsClass(annotatedBuilderType.name, listOf(text, spans, stack, constructor, append, pushStyle, pushAnnotation, pop, toString),
        at, exported = true)
}

internal fun usesAnnotatedString(program: EtsProgram): Boolean {
    val ids = setOf(spanStyleType.symbolId, annotatedSpanType.symbolId, annotatedStringType.symbolId, annotatedBuilderType.symbolId)
    var used = false
    fun type(value: EtsType) {
        when (value) {
            is EtsNamedType -> { if (value.symbolId in ids) used = true; value.arguments.forEach(::type) }
            is EtsNullableType -> type(value.inner)
            is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result) }
            is EtsRecordType -> value.fields.values.forEach(::type)
            is EtsTupleType -> value.elements.forEach(::type)
            is EtsCapturedType -> { type(value.readType); type(value.writeType) }
            is EtsTypeParameterType -> Unit
        }
    }
    program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
        if (node is EtsExpression) type(node.type)
        when (node) {
            is EtsFunction -> type(node.symbol.type)
            is EtsField -> type(node.symbol.type)
            is EtsGlobal -> type(node.symbol.type)
            is EtsVariable -> type(node.symbol.type)
            else -> Unit
        }
    } } }
    return used
}
