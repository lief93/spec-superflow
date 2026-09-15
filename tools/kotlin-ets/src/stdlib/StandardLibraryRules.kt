@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.IrBuiltIns
import org.jetbrains.kotlin.ir.declarations.IrDeclarationOrigin
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.collectRealOverrides
import org.jetbrains.kotlin.ir.util.isNullable

class StandardLibraryRules : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        EnumRules.lower(call, language, scope)?.let { return it }
        EqualityRules.lower(call, language, scope)?.let { return it }
        IterationRules.lower(call, language, scope)?.let { return it }
        FloatingPointRules.lower(call, language, scope)?.let { return it }
        CollectionEmptinessRules.lower(call, language, scope)?.let { return it }
        LetRule.lower(call, language, scope)?.let { return it }
        val owner = call.symbol.owner
        val name = symbolName(if (owner.isFakeOverride) owner.collectRealOverrides().singleOrNull() ?: owner else owner)
        val receiver = call.dispatchReceiver ?: call.extensionReceiver
        val args = (0 until call.valueArgumentsCount).map { call.getValueArgument(it) }
        val source = language.source(call)
        fun lower(expression: IrExpression) = language.expression(expression, scope)
        fun receiverNode() = lower(checkNotNull(receiver))
        fun arg(index: Int) = lower(checkNotNull(args[index]))
        fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, source)
        fun binary(operator: String, left: EtsExpression, right: EtsExpression, result: EtsType = EtsTypes.NUMBER) =
            EtsBinary(operator, left, right, result, source)
        fun int32(value: EtsExpression) = binary("|", value, number(0))
        fun external(function: String, parameters: List<EtsType>, result: EtsType,
            arguments: List<EtsExpression>, typeArguments: List<EtsType> = emptyList()): EtsCall {
            val symbol = EtsSymbol("stdlib:" + function, function, EtsFunctionType(parameters, result), source, external = true)
            return EtsCall(EtsReference(symbol, source), arguments, result, source, typeArguments)
        }
        fun member(target: EtsExpression, method: String, parameters: List<EtsType>, result: EtsType,
            arguments: List<EtsExpression> = emptyList()) =
            EtsCall(EtsMember(target, method, EtsFunctionType(parameters, result), source), arguments, result, source)
        fun math(method: String, arguments: List<EtsExpression>): EtsCall {
            val target = EtsReference(EtsSymbol("stdlib:Math", "Math", EtsNamedType("Math"), source, external = true))
            return member(target, method, List(arguments.size) { EtsTypes.NUMBER }, EtsTypes.NUMBER, arguments)
        }
        fun signature(receiverType: String?, result: String, vararg parameters: String): Boolean =
            (if (receiverType == null) receiver == null else receiver?.type.isExactly(receiverType)) &&
                call.type.isExactly(result) && args.size == parameters.size &&
                args.zip(parameters.toList()).all { (value, type) -> value?.type.isExactly(type) }
        fun staticSignature(result: String, vararg parameters: String): Boolean {
            val owner = call.symbol.owner
            return sourceFile(owner) == null && owner.dispatchReceiverParameter == null &&
                owner.extensionReceiverParameter == null && !owner.isSuspend && !owner.isFakeOverride &&
                owner.typeParameters.isEmpty() && call.typeArgumentsCount == 0 && call.superQualifierSymbol == null &&
                owner.returnType.isExactly(result) && owner.valueParameters.size == parameters.size &&
                owner.valueParameters.zip(parameters.toList()).all { (parameter, type) ->
                    parameter.type.isExactly(type) && parameter.varargElementType == null && parameter.defaultValue == null
                } && signature(null, result, *parameters)
        }

        if (name == "kotlin.internal.ir.illegalArgumentException" && staticSignature("kotlin.Nothing", "kotlin.String")) {
            return external("__etsIllegalArgumentException", listOf(EtsTypes.STRING), EtsTypes.NEVER, listOf(arg(0)))
        }
        if (name == "kotlin.internal.ir.noWhenBranchMatchedException" && owner.origin == IrBuiltIns.BUILTIN_OPERATOR &&
            staticSignature("kotlin.Nothing")) {
            return EtsCall(EtsLambda(emptyList(), listOf(EtsThrow(namedTargetFailure("NoWhenBranchMatchedException", source), source)),
                EtsTypes.NEVER, source), emptyList(), EtsTypes.NEVER, source)
        }
        if (name == "kotlin.internal.ProgressionUtilKt.getProgressionLastElement" &&
            staticSignature("kotlin.Int", "kotlin.Int", "kotlin.Int", "kotlin.Int")) {
            return external("__etsProgressionLastElement", List(3) { EtsTypes.NUMBER }, EtsTypes.NUMBER,
                args.indices.map { arg(it) })
        }
        if (name == "kotlin.internal.ir.EQEQ" && nullEqualitySignature(call)) {
            return binary("===", arg(0), arg(1), EtsTypes.BOOLEAN)
        }

        if (signature("kotlin.Int", "kotlin.Int", "kotlin.Int")) {
            return when (name) {
                "kotlin.Int.plus" -> int32(binary("+", receiverNode(), arg(0)))
                "kotlin.Int.minus" -> int32(binary("-", receiverNode(), arg(0)))
                "kotlin.Int.times" -> math("imul", listOf(receiverNode(), arg(0)))
                "kotlin.Int.and" -> binary("&", receiverNode(), arg(0))
                "kotlin.Int.div" -> external("__etsIntDiv", listOf(EtsTypes.NUMBER, EtsTypes.NUMBER),
                    EtsTypes.NUMBER, listOf(receiverNode(), arg(0)))
                "kotlin.Int.rem" -> external("__etsIntRem", listOf(EtsTypes.NUMBER, EtsTypes.NUMBER),
                    EtsTypes.NUMBER, listOf(receiverNode(), arg(0)))
                "kotlin.Int.compareTo" -> math("sign", listOf(binary("-", receiverNode(), arg(0))))
                else -> null
            }
        }
        if (signature("kotlin.Int", "kotlin.Int")) {
            return when (name) {
                "kotlin.Int.unaryMinus" -> int32(EtsUnary("-", receiverNode(), EtsTypes.NUMBER, source))
                "kotlin.Int.unaryPlus" -> EtsUnary("+", receiverNode(), EtsTypes.NUMBER, source)
                "kotlin.Int.inc" -> int32(binary("+", receiverNode(), number(1)))
                "kotlin.Int.dec" -> int32(binary("-", receiverNode(), number(1)))
                else -> null
            }
        }
        if (signature(null, "kotlin.Boolean", "kotlin.Int", "kotlin.Int")) {
            val operator = when (name) {
                "kotlin.internal.ir.less" -> "<"
                "kotlin.internal.ir.lessOrEqual" -> "<="
                "kotlin.internal.ir.greater" -> ">"
                "kotlin.internal.ir.greaterOrEqual" -> ">="
                "kotlin.internal.ir.EQEQ" -> "==="
                else -> return null
            }
            return binary(operator, arg(0), arg(1), EtsTypes.BOOLEAN)
        }
        if (name == "kotlin.internal.ir.EQEQ" && receiver == null && args.size == 2 &&
            call.type.isExactly("kotlin.Boolean") &&
            listOf("kotlin.String", "kotlin.Boolean").any { type -> args.all { it?.type.isExactly(type) } }) {
            return binary("===", arg(0), arg(1), EtsTypes.BOOLEAN)
        }
        if (name == "kotlin.Boolean.not" && signature("kotlin.Boolean", "kotlin.Boolean")) {
            return EtsUnary("!", receiverNode(), EtsTypes.BOOLEAN, source)
        }
        if (signature("kotlin.Boolean", "kotlin.Boolean", "kotlin.Boolean")) {
            val operator = when (name) {
                "kotlin.Boolean.and" -> "&"
                "kotlin.Boolean.or" -> "|"
                "kotlin.Boolean.xor" -> "^"
                else -> return null
            }
            // Kotlin and/or evaluate both operands; target &&/|| would skip side effects.
            val left = EtsConditional(receiverNode(), number(1), number(0), EtsTypes.NUMBER, source)
            val right = EtsConditional(arg(0), number(1), number(0), EtsTypes.NUMBER, source)
            return binary("!==", binary(operator, left, right), number(0), EtsTypes.BOOLEAN)
        }
        if (name in setOf("kotlin.Int.toString", "kotlin.Boolean.toString", "kotlin.String.toString") &&
            args.isEmpty() && call.type.isExactly("kotlin.String") &&
            receiver?.type.isExactly(name.substringBeforeLast('.'))) {
            return member(receiverNode(), "toString", emptyList(), EtsTypes.STRING)
        }
        if (name == "kotlin.String.plus" && receiver?.type.isExactly("kotlin.String") &&
            call.type.isExactly("kotlin.String") && args.size == 1 &&
            listOf("kotlin.String", "kotlin.Int", "kotlin.Boolean").any { args[0]?.type.isExactly(it) }) {
            return binary("+", receiverNode(), arg(0), EtsTypes.STRING)
        }
        if (name == "kotlin.String.<get-length>" && signature("kotlin.String", "kotlin.Int")) {
            return EtsMember(receiverNode(), "length", EtsTypes.NUMBER, source)
        }
        if (name == "kotlin.text.substring" &&
            (signature("kotlin.String", "kotlin.String", "kotlin.Int") ||
                signature("kotlin.String", "kotlin.String", "kotlin.Int", "kotlin.Int"))) {
            val arguments = listOf(receiverNode()) + args.indices.map { arg(it) }
            return external(if (args.size == 1) "__etsSubstringFrom" else "__etsSubstring",
                listOf(EtsTypes.STRING) + List(args.size) { EtsTypes.NUMBER }, EtsTypes.STRING, arguments)
        }
        if (name in setOf("kotlin.text.contains", "kotlin.text.startsWith", "kotlin.text.endsWith") &&
            receiver?.type.isExactly("kotlin.String") && call.type.isExactly("kotlin.Boolean") &&
            args.size == 2 && args[0]?.type.isExactly("kotlin.String") &&
            (args[1] == null || (args[1] as? IrConst)?.value == false)) {
            val method = when (name) {
                "kotlin.text.contains" -> "includes"
                "kotlin.text.startsWith" -> "startsWith"
                else -> "endsWith"
            }
            return member(receiverNode(), method, listOf(EtsTypes.STRING), EtsTypes.BOOLEAN, listOf(arg(0)))
        }
        if (name in setOf("kotlin.collections.listOf", "kotlin.collections.mutableListOf") && receiver == null) {
            val resultClass = if (name == "kotlin.collections.listOf") "kotlin.collections.List" else "kotlin.collections.MutableList"
            if (!call.type.isExactly(resultClass) || call.typeArgumentsCount != 1) return null
            val elementType = call.getTypeArgument(0) ?: return null
            if (call.type.listElement() != elementType) return null
            val elements = when {
                args.isEmpty() -> emptyList()
                args.size != 1 -> return null
                call.symbol.owner.valueParameters[0].varargElementType != null -> {
                    val vararg = args[0] as? IrVararg ?: return null
                    if (vararg.elements.any { it !is IrExpression }) return null
                    vararg.elements.map { it as IrExpression }
                }
                args[0] != null -> listOf(checkNotNull(args[0]))
                else -> return null
            }
            return EtsArray(elements.map { lower(it) }, language.type(elementType), source)
        }
        if (name in setOf("kotlin.collections.filter", "kotlin.collections.filterNot")) {
            val element = predicateElement(call, "kotlin.collections.List") ?: return null
            val targetElement = language.type(element)
            val result = EtsNamedType("Array", listOf(targetElement))
            return external("__etsListFilter", listOf(result,
                EtsFunctionType(listOf(targetElement), EtsTypes.BOOLEAN), EtsTypes.BOOLEAN), result,
                listOf(receiverNode(), arg(0), EtsLiteral(name == "kotlin.collections.filter",
                    EtsTypes.BOOLEAN, source)), listOf(targetElement))
        }
        if (name in setOf("kotlin.collections.any", "kotlin.collections.all", "kotlin.collections.none", "kotlin.collections.count")) {
            val count = name == "kotlin.collections.count"
            val element = predicateElement(call, if (count) "kotlin.Int" else "kotlin.Boolean") ?: return null
            val targetElement = language.type(element)
            val parameters = listOf(EtsNamedType("Array", listOf(targetElement)),
                EtsFunctionType(listOf(targetElement), EtsTypes.BOOLEAN))
            val arguments = listOf(receiverNode(), arg(0))
            if (count) return external("__etsListCount", parameters, EtsTypes.NUMBER, arguments, listOf(targetElement))
            val result = external("__etsListAny", parameters + EtsTypes.BOOLEAN, EtsTypes.BOOLEAN,
                arguments + EtsLiteral(name != "kotlin.collections.all", EtsTypes.BOOLEAN, source), listOf(targetElement))
            return if (name == "kotlin.collections.any") result else EtsUnary("!", result, EtsTypes.BOOLEAN, source)
        }
        if (receiver?.type.isList()) {
            when (name) {
                "kotlin.collections.List.<get-size>", "kotlin.collections.MutableList.<get-size>" ->
                    if (args.isEmpty() && call.type.isExactly("kotlin.Int"))
                        return EtsMember(receiverNode(), "length", EtsTypes.NUMBER, source)
                "kotlin.collections.List.get", "kotlin.collections.MutableList.get" -> {
                    val element = receiver?.type.listElement() ?: return null
                    if (args.size == 1 && args[0]?.type.isExactly("kotlin.Int") && call.type == element) {
                        val targetElement = language.type(element)
                        return external("__etsListGet", listOf(EtsNamedType("Array", listOf(targetElement)), EtsTypes.NUMBER),
                            targetElement, listOf(receiverNode(), arg(0)), listOf(targetElement))
                    }
                }
                "kotlin.collections.MutableList.add" -> {
                    val element = receiver?.type.listElement() ?: return null
                    if (receiver?.type.isExactly("kotlin.collections.MutableList") && args.size == 1 &&
                        args[0] != null && call.type.isExactly("kotlin.Boolean")) {
                        val targetElement = language.type(element)
                        return external("__etsListAdd", listOf(EtsNamedType("Array", listOf(targetElement)), targetElement),
                            EtsTypes.BOOLEAN, listOf(receiverNode(), arg(0)), listOf(targetElement))
                    }
                }
                "kotlin.collections.map" -> {
                    val (input, output) = mapElements(call) ?: return null
                    val targetInput = language.type(input)
                    val targetOutput = language.type(output)
                    val result = EtsNamedType("Array", listOf(targetOutput))
                    return external("__etsListMap", listOf(EtsNamedType("Array", listOf(targetInput)),
                        EtsFunctionType(listOf(targetInput), targetOutput)), result,
                        listOf(receiverNode(), arg(0)), listOf(targetInput, targetOutput))
                }
            }
        }
        return null
    }

    fun supportLines(): List<String> = standardLibrarySupportLines()
}

// Only the official literal-null fast path; this does not implement equals dispatch.
private fun nullEqualitySignature(call: IrCall): Boolean {
    val owner = call.symbol.owner
    if (owner.origin != IrBuiltIns.BUILTIN_OPERATOR || sourceFile(owner) != null ||
        owner.isSuspend || owner.isFakeOverride || owner.typeParameters.isNotEmpty() || call.typeArgumentsCount != 0 ||
        owner.dispatchReceiverParameter != null || owner.extensionReceiverParameter != null ||
        call.dispatchReceiver != null || call.extensionReceiver != null || call.superQualifierSymbol != null ||
        owner.valueParameters.size != 2 || call.valueArgumentsCount != 2 ||
        owner.returnType.invariantArguments("kotlin.Boolean") != emptyList<IrType>() ||
        call.type.invariantArguments("kotlin.Boolean") != emptyList<IrType>()) return false
    if (owner.valueParameters.any { parameter ->
        !parameter.type.isNullableAny() || (parameter.type as? IrSimpleType)?.arguments?.isEmpty() != true ||
            parameter.varargElementType != null || parameter.defaultValue != null
    }) return false
    val arguments = listOf(call.getValueArgument(0), call.getValueArgument(1))
    return arguments.all { it != null && it.type is IrSimpleType } && arguments.any {
        it is IrConst && it.kind == IrConstKind.Null && it.value == null && it.type.isNullableNothing() &&
            (it.type as IrSimpleType).arguments.isEmpty()
    }
}

private fun IrType?.isExactly(name: String): Boolean =
    this is IrSimpleType && !isNullable() && classOrNull?.owner?.fqNameWhenAvailable?.asString() == name

private fun IrType?.isList(): Boolean =
    isExactly("kotlin.collections.List") || isExactly("kotlin.collections.MutableList") || isExactly("kotlin.enums.EnumEntries")

private fun IrType?.listElement(): IrType? =
    if (isList()) ((this as IrSimpleType).arguments.singleOrNull() as? IrTypeProjection)?.type else null

// Match the official Iterable<T>.map declaration, retaining the bounded List receiver path.
private fun mapElements(call: IrCall): Pair<IrType, IrType>? {
    val owner = call.symbol.owner
    if (owner.origin != IrDeclarationOrigin.IR_EXTERNAL_DECLARATION_STUB ||
        sourceFile(owner) != null || !owner.isInline || owner.isSuspend || owner.isFakeOverride ||
        owner.dispatchReceiverParameter != null || call.dispatchReceiver != null ||
        call.superQualifierSymbol != null || owner.typeParameters.size != 2 ||
        owner.typeParameters.any { it.isReified } || owner.valueParameters.size != 1 ||
        call.typeArgumentsCount != 2 || call.valueArgumentsCount != 1) return null
    val declaredInput = owner.extensionReceiverParameter?.type
        .invariantArguments("kotlin.collections.Iterable")?.singleOrNull() ?: return null
    val declaredOutput = owner.returnType.invariantArguments("kotlin.collections.List")?.singleOrNull() ?: return null
    for ((type, parameter) in listOf(declaredInput, declaredOutput).zip(owner.typeParameters)) {
        val simple = type as? IrSimpleType ?: return null
        if (simple.classifier != parameter.symbol || simple.arguments.isNotEmpty() ||
            simple.nullability != SimpleTypeNullability.NOT_SPECIFIED) return null
    }
    val parameter = owner.valueParameters.single()
    if (parameter.varargElementType != null || parameter.defaultValue != null ||
        parameter.type.invariantArguments("kotlin.Function1") != listOf(declaredInput, declaredOutput)) return null
    val input = call.getTypeArgument(0) ?: return null
    val output = call.getTypeArgument(1) ?: return null
    if (call.extensionReceiver?.type.invariantArguments("kotlin.collections.List", "kotlin.collections.MutableList") != listOf(input) ||
        call.type.invariantArguments("kotlin.collections.List") != listOf(output) ||
        call.getValueArgument(0)?.type.invariantArguments("kotlin.Function1") != listOf(input, output)) return null
    return input to output
}

// Check the resolved declaration as well as the instantiated call before lowering any children.
private fun predicateElement(call: IrCall, resultClass: String): IrType? {
    val owner = call.symbol.owner
    if (owner.origin != IrDeclarationOrigin.IR_EXTERNAL_DECLARATION_STUB ||
        sourceFile(owner) != null || !owner.isInline || owner.isSuspend || owner.isFakeOverride ||
        owner.dispatchReceiverParameter != null || call.dispatchReceiver != null ||
        call.superQualifierSymbol != null || owner.typeParameters.size != 1 ||
        owner.typeParameters.single().isReified || owner.valueParameters.size != 1 ||
        call.typeArgumentsCount != 1 || call.valueArgumentsCount != 1) return null
    val declaredElement = owner.extensionReceiverParameter?.type
        .invariantArguments("kotlin.collections.Iterable")?.singleOrNull() ?: return null
    val declaredSimple = declaredElement as? IrSimpleType ?: return null
    if (declaredSimple.classifier != owner.typeParameters.single().symbol ||
        declaredSimple.nullability == SimpleTypeNullability.MARKED_NULLABLE) return null
    val declaredResultArguments = if (resultClass == "kotlin.collections.List") listOf(declaredElement) else emptyList()
    if (owner.returnType.invariantArguments(resultClass) != declaredResultArguments) return null
    val parameter = owner.valueParameters.single()
    val declaredPredicate = parameter.type.invariantArguments("kotlin.Function1") ?: return null
    if (parameter.varargElementType != null || parameter.defaultValue != null ||
        declaredPredicate.size != 2 || declaredPredicate[0] != declaredElement ||
        !declaredPredicate[1].isExactly("kotlin.Boolean")) return null
    val element = call.getTypeArgument(0) ?: return null
    val receiver = call.extensionReceiver ?: return null
    val resultArguments = if (resultClass == "kotlin.collections.List") listOf(element) else emptyList()
    if (receiver.type.invariantArguments("kotlin.collections.List", "kotlin.collections.MutableList",
            "kotlin.collections.Iterable") != listOf(element) ||
        call.type.invariantArguments(resultClass) != resultArguments) return null
    val predicate = call.getValueArgument(0)?.type.invariantArguments("kotlin.Function1") ?: return null
    if (predicate.size != 2 || predicate[0] != element || !predicate[1].isExactly("kotlin.Boolean")) return null
    return element
}

private fun IrType?.invariantArguments(vararg classifiers: String): List<IrType>? {
    if (this !is IrSimpleType || classifiers.none { isExactly(it) }) return null
    return arguments.map {
        val projection = it as? IrTypeProjection ?: return null
        if (projection.variance != org.jetbrains.kotlin.types.Variance.INVARIANT) return null
        projection.type
    }
}
