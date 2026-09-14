@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.util.IdentityHashMap
import org.jetbrains.kotlin.backend.common.lower.BOUND_RECEIVER_PARAMETER
import org.jetbrains.kotlin.backend.common.lower.BOUND_VALUE_PARAMETER
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.backend.jvm.JvmLoweredDeclarationOrigin
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrTypeParameterSymbol
import org.jetbrains.kotlin.ir.symbols.IrFieldSymbol
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.util.isNullable
import org.jetbrains.kotlin.ir.util.superTypes
import org.jetbrains.kotlin.ir.visitors.*

class LanguageLowering(val diagnostics: DiagnosticSink, rules: List<CallRule>) : Language {
    override val callRules: List<CallRule> = rules
    private var nextTemporary = 0
    private val temporaryNames = IdentityHashMap<IrValueSymbol, String>()
    private val symbols = IdentityHashMap<IrValueSymbol, EtsSymbol>()
    private val overloadNaming = OverloadNaming()
    private val classNaming = ClassNaming(overloadNaming)
    private val capturedFields = IdentityHashMap<IrFieldSymbol, EtsSymbol>()
    private val outerFields = IdentityHashMap<IrFieldSymbol, EtsSymbol>()
    private val capturedParameters = IdentityHashMap<IrValueSymbol, String>()
    private var nextSymbol = 0
    private val loopNames = IdentityHashMap<IrLoop, String>()
    private val activeLoops = mutableListOf<IrLoop>()
    private val returnTargets = mutableListOf<IrFunction>()
    private val sourceNames = mutableSetOf<String>()
    private var expressionDepth = 0
    private var currentElement: IrElement? = null
    private data class NativeInitialization(val owner: IrClass, val base: IrClass?, val baseType: EtsNamedType?)
    private var nativeInitialization: NativeInitialization? = null

    override fun source(element: IrElement): SourceSpan {
        val source = sourceSpan(element, diagnostics)
        if (source.start >= 0 && source.end >= source.start) return source
        val declaration = when (element) {
            is IrGetField -> element.symbol.owner
            is IrSetField -> element.symbol.owner
            is IrGetValue -> element.symbol.owner
            else -> element
        }
        val owner = when (declaration) {
            is IrField -> declaration.parent as? IrClass
            is IrValueParameter -> (declaration.parent as? IrConstructor)?.parent as? IrClass
            else -> null
        }
        val binding = owner?.let(::sourceInnerClassBinding)
        return if (binding != null && (declaration === binding.field || declaration === binding.parameter)) binding.source else source
    }

    override fun type(type: IrType): EtsType {
        callRules.firstNotNullOfOrNull { it.mapType(type.makeNotNull(), this) }?.let { mapped ->
            return if (type.isNullable()) EtsNullableType(mapped) else mapped
        }
        val simple = type as? IrSimpleType ?: unsupportedType(type)
        val owner = simple.classifier.owner
        if (owner is IrTypeParameter) {
            val parameter = typeParameterType(owner)
            if (simple.nullability == SimpleTypeNullability.DEFINITELY_NOT_NULL) unsupportedType(type)
            return if (simple.nullability == SimpleTypeNullability.MARKED_NULLABLE) EtsNullableType(parameter) else parameter
        }
        val name = (owner as? IrClass)?.fqNameWhenAvailable?.asString()
        val arguments = simple.arguments.map {
            val projection = it as? IrTypeProjection ?: unsupportedType(type)
            if (projection.variance != org.jetbrains.kotlin.types.Variance.INVARIANT) unsupportedType(type)
            projection.type
        }
        val mapped = when (name) {
            "kotlin.Unit" -> EtsTypes.VOID
            "kotlin.Nothing" -> EtsTypes.NEVER
            "kotlin.Boolean" -> EtsTypes.BOOLEAN
            "kotlin.String", "kotlin.Char" -> EtsTypes.STRING
            "kotlin.Byte", "kotlin.Short", "kotlin.Int", "kotlin.Float", "kotlin.Double" -> EtsTypes.NUMBER
            "kotlin.Any" -> EtsTypes.OBJECT
            "kotlin.collections.Iterator", "kotlin.collections.MutableIterator" ->
                EtsNamedType("__etsIterator", listOf(type(arguments.singleOrNull() ?: unsupportedType(type))),
                    "stdlib:__etsIterator", external = true)
            "kotlin.collections.IntIterator" ->
                EtsNamedType("__etsIterator", listOf(EtsTypes.NUMBER), "stdlib:__etsIterator", external = true)
            "kotlin.ranges.IntRange", "kotlin.ranges.IntProgression" ->
                EtsNamedType("__etsIntProgression", symbolId = "stdlib:__etsIntProgression", external = true)
            "kotlin.Array", "kotlin.collections.List", "kotlin.collections.MutableList",
            "kotlin.collections.Collection", "kotlin.collections.Iterable" ->
                EtsNamedType("Array", listOf(type(arguments.singleOrNull() ?: unsupportedType(type))))
            "kotlin.IntArray", "kotlin.FloatArray", "kotlin.DoubleArray", "kotlin.ByteArray",
            "kotlin.ShortArray" -> EtsNamedType("Array", listOf(EtsTypes.NUMBER))
            "kotlin.BooleanArray" -> EtsNamedType("Array", listOf(EtsTypes.BOOLEAN))
            else -> when {
                name?.startsWith("kotlin.Function") == true && arguments.isNotEmpty() -> {
                    EtsFunctionType(arguments.dropLast(1).map { type(it) }, type(arguments.last()))
                }
                owner is IrClass && sourceFile(owner) != null -> classType(owner, arguments.map { type(it) })
                else -> unsupportedType(type)
            }
        }
        return if (type.isNullable()) EtsNullableType(mapped) else mapped
    }

    private fun unsupportedType(type: IrType): Nothing {
        currentElement?.let { diagnostics.unsupported(it, "Unsupported language type: ${type.render()}") }
        val owner = (type as? IrSimpleType)?.classifier?.owner
        if (owner is IrElement) diagnostics.unsupported(owner, "Unsupported language type: ${type.render()}")
        error("Unsupported language type: ${type.render()}")
    }

    override fun expression(expression: IrExpression, scope: Scope): EtsExpression = withElement(expression) { when (expression) {
        is IrConst -> constant(expression)
        is IrGetValue -> scope.bindings[expression.symbol]
            ?: scope.aliases[expression.symbol]?.let { expression(it, scope) }
            ?: diagnostics.unsupported(expression, "Unbound value: ${expression.symbol.owner.name}")
        is IrSetValue -> {
            val target = scope.bindings[expression.symbol]
                ?: diagnostics.unsupported(expression, "Unbound assignment: ${expression.symbol.owner.name}")
            discard(EtsAssignment(target, expression(expression.value, scope), source(expression)), expression)
        }
        is IrCall -> call(expression, scope)
        is IrConstructorCall -> {
            val owner = expression.symbol.owner.parent as IrClass
            if (sourceFile(owner) == null) diagnostics.unsupported(expression, "Unsupported external constructor: ${symbolName(owner)}")
            EtsNew(type(expression.type) as? EtsNamedType ?: unsupportedType(expression.type),
                arguments(expression, scope), source(expression))
        }
        is IrGetField -> {
            if (sourceFile(expression.symbol.owner) == null) diagnostics.unsupported(expression, "Unsupported external field")
            val captured = when {
                hasCaptureOrigin(expression.symbol.owner) -> capturedFieldSymbol(expression.symbol.owner)
                expression.symbol.owner.origin === IrDeclarationOrigin.FIELD_FOR_OUTER_THIS -> outerFieldSymbol(expression.symbol.owner)
                else -> null
            }
            EtsMember(expression.receiver?.let { expression(it, scope) } ?: thisReference(expression.symbol.owner.parent as IrClass, expression),
                captured?.name ?: fieldName(expression.symbol.owner), type(expression.type), source(expression), captured?.id)
        }
        is IrSetField -> {
            if (sourceFile(expression.symbol.owner) == null) diagnostics.unsupported(expression, "Unsupported external field assignment")
            if (hasCaptureOrigin(expression.symbol.owner))
                diagnostics.unsupported(expression, "Captured field writes require the official constructor prefix")
            if (expression.symbol.owner.origin === IrDeclarationOrigin.FIELD_FOR_OUTER_THIS) {
                val owner = expression.symbol.owner.parent as? IrClass
                    ?: diagnostics.unsupported(expression, "Outer field requires a registered class owner")
                val binding = innerBinding(owner)
                    ?: diagnostics.unsupported(owner, "Outer field requires a registered inner class")
                rejectInner(binding, expression, "Outer field writes require the registered constructor prefix")
            }
            val target = EtsMember(expression.receiver?.let { expression(it, scope) } ?: thisReference(expression.symbol.owner.parent as IrClass, expression),
                fieldName(expression.symbol.owner), type(expression.symbol.owner.type), source(expression))
            discard(EtsAssignment(target, expression(expression.value, scope), source(expression)), expression)
        }
        is IrTypeOperatorCall -> typeOperator(expression, scope)
        is IrWhen -> whenExpression(expression, scope)
        is IrContainerExpression -> blockExpression(expression, scope)
        is IrFunctionExpression -> functionExpression(expression.function, scope)
        is IrStringConcatenation -> expression.arguments.fold<IrExpression, EtsExpression>(
            EtsLiteral("", EtsTypes.STRING, source(expression))) { result, value ->
                EtsBinary("+", result, stringOperand(value, scope), EtsTypes.STRING, source(expression))
            }
        is IrReturn -> diagnostics.unsupported(expression, "Return requires a statement position")
        is IrGetObjectValue -> {
            val owner = expression.symbol.owner
            when {
                owner.fqNameWhenAvailable?.asString() == "kotlin.Unit" -> discard(EtsUndefined(source(expression)), expression)
                sourceFile(owner) != null && !owner.isExternal && owner.kind == org.jetbrains.kotlin.descriptors.ClassKind.OBJECT ->
                    EtsCall(EtsMember(classReference(owner, expression), "__etsGetInstance",
                        EtsFunctionType(emptyList(), classType(owner)), source(expression)),
                        emptyList(), classType(owner), source(expression))
                else -> diagnostics.unsupported(expression, "Unsupported object value: ${symbolName(owner)}")
            }
        }
        else -> diagnostics.unsupported(expression, "Unsupported language expression: ${expression.javaClass.simpleName}")
    } }

    private fun stringOperand(value: IrExpression, scope: Scope): EtsExpression {
        val owner = value.type.classOrNull?.owner
        val name = owner?.fqNameWhenAvailable?.asString()
        if (name in setOf("kotlin.String", "kotlin.Char", "kotlin.Boolean", "kotlin.Byte", "kotlin.Short", "kotlin.Int") ||
            (value is IrConst && value.value == null)) return expression(value, scope)
        val override = owner?.declarations?.filterIsInstance<IrSimpleFunction>()?.singleOrNull {
            it.name.asString() == "toString" && !it.isFakeOverride && !it.isExternal &&
                it.valueParameters.isEmpty() && it.extensionReceiverParameter == null && it.body != null && it.returnType.isString()
        }
        if (owner != null && sourceFile(owner) != null && override != null) {
            val rendered = expression(value, scope)
            fun invoke(receiver: EtsExpression) = EtsCall(EtsMember(receiver, identifier(override),
                EtsFunctionType(emptyList(), EtsTypes.STRING), source(value)), emptyList(), EtsTypes.STRING, source(value))
            if (!value.type.isNullable()) return invoke(rendered)
            val temporary = synthetic(freshName("__etsString", scope), rendered.type, value)
            val reference = EtsReference(temporary)
            return iife(listOf(EtsVariable(temporary, rendered, false), EtsReturn(EtsConditional(
                EtsBinary("===", reference, EtsLiteral(null, EtsTypes.NULL, source(value)), EtsTypes.BOOLEAN, source(value)),
                EtsLiteral("null", EtsTypes.STRING, source(value)),
                invoke(EtsCast(reference, type(value.type.makeNotNull()), source(value))), EtsTypes.STRING, source(value)), source(value))),
                EtsTypes.STRING, value)
        }
        diagnostics.unsupported(value, "Unsupported string concatenation operand: ${value.type.render()}")
    }

    private fun adaptedStatement(call: IrCall, scope: Scope): List<EtsStatement>? =
        when (val result = adaptCall(call, this, scope, CallContext.STATEMENT)) {
            null -> null
            is CallResult.Statements -> result.statements
            is CallResult.Value -> listOf(expressionStatement(result.expression))
            is CallResult.Ui -> error("UI result in statement context")
        }

    private fun call(call: IrCall, scope: Scope, adapt: Boolean = true): EtsExpression {
        if (call.superQualifierSymbol != null) diagnostics.unsupported(call, "Explicit super member calls are not supported")
        if (adapt) {
            adaptCall(call, this, scope, CallContext.VALUE)?.let {
                check(it is CallResult.Value) { "Non-value result in value context" }
                return it.expression
            }
        }
        val resolved = call.symbol.owner
        val owner = if (resolved.isFakeOverride) resolved.collectRealOverrides().singleOrNull()
            ?: diagnostics.unsupported(call, "Ambiguous inherited declaration: ${symbolName(resolved)}") else resolved
        val parent = owner.parent
        val receiver = call.dispatchReceiver
        if (owner.name.asString() == "invoke" && parent is IrClass &&
            parent.fqNameWhenAvailable?.asString()?.startsWith("kotlin.Function") == true && receiver != null) {
            return EtsCall(expression(receiver, scope), arguments(call, scope), type(call.type), source(call))
        }
        if (sourceFile(owner) == null || owner.isExternal) {
            diagnostics.unsupported(call, "Unsupported external call: ${symbolName(owner)}")
        }
        if (parent is IrClass && parent.isData && owner.origin == IrDeclarationOrigin.GENERATED_DATA_CLASS_MEMBER &&
            owner.name.asString() in setOf("equals", "hashCode")) {
            diagnostics.unsupported(call, "Data class ${owner.name} is outside the first language slice")
        }
        val property = owner.correspondingPropertySymbol?.owner
        val substitutions = if (owner.dispatchReceiverParameter == null) emptyMap()
            else receiverSubstitution(parent as? IrClass, receiver)
        if (property != null) {
            val propertyType = etsSubstitute(type(property.backingField?.type ?: property.getter!!.returnType), substitutions)
            val access = receiver?.let { EtsMember(expression(it, scope), identifier(property), propertyType, source(call)) }
                ?: diagnostics.unsupported(call, "Top-level stored properties are outside the first language slice")
            return if (property.setter?.symbol == owner.symbol)
                discard(EtsAssignment(access, arguments(call, scope).single(), source(call)), call) else access
        }
        val signature = etsSubstitute(EtsFunctionType(
            (listOfNotNull(owner.extensionReceiverParameter) + owner.valueParameters).map { type(it.type) },
            type(owner.returnType), typeParameters(owner)), substitutions) as EtsFunctionType
        val symbol = functionSymbol(owner)
        val callee = when {
            receiver != null -> EtsMember(expression(receiver, scope), symbol.name, signature, source(call), symbol.id)
            parent is IrClass -> EtsMember(classReference(parent, call), symbol.name, signature, source(call), symbol.id)
            else -> EtsReference(symbol.copy(type = signature), source(call))
        }
        val typeArguments = owner.typeParameters.indices.map { index ->
            type(call.getTypeArgument(index) ?: diagnostics.unsupported(call, "Missing resolved generic type argument"))
        }
        return EtsCall(callee, arguments(call, scope), type(call.type), source(call), typeArguments)
    }

    private fun arguments(call: IrFunctionAccessExpression, scope: Scope): List<EtsExpression> {
        val owner = call.symbol.owner
        val values = owner.valueParameters.mapIndexed { index, parameter ->
            call.getValueArgument(index)?.let { expression(it, scope) }
                ?: if (parameter.defaultValue != null) EtsUndefined(source(call))
                else if (parameter.varargElementType != null) EtsArray(emptyList(), type(parameter.varargElementType!!), source(call))
                else diagnostics.unsupported(call, "Missing argument for ${parameter.name} in ${symbolName(owner)}")
        }.toMutableList()
        call.extensionReceiver?.let { values.add(0, expression(it, scope)) }
        return values
    }

    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> {
        reserveNames(body)
        return when (body) {
            is IrBlockBody -> body.statements.flatMap { statement(it, scope) }
            is IrExpressionBody -> listOf(EtsReturn(expression(body.expression, scope), source(body)))
            else -> diagnostics.unsupported(body, "Unsupported language body: ${body.javaClass.simpleName}")
        }
    }

    private fun statement(value: IrStatement, scope: Scope): List<EtsStatement> = withElement(value) { when (value) {
        is IrDelegatingConstructorCall, is IrInstanceInitializerCall -> constructorStatement(value, scope)
        is IrVariable -> {
            val initializer = value.initializer?.let { expression(it, scope) }
            val name = bind(value, scope)
            value.initializer?.let { scope.aliases[value.symbol] = it }
            listOf(EtsVariable(name, initializer, value.isVar || initializer == null))
        }
        is IrReturn -> {
            if (expressionDepth > 0) diagnostics.unsupported(value, "Return crosses an expression boundary")
            if (returnTargets.lastOrNull()?.symbol?.let { it != value.returnTargetSymbol } == true) {
                diagnostics.unsupported(value, "Non-local return is outside the first language slice")
            }
            if (value.value.type.isUnit()) statement(value.value, scope) + EtsReturn(null, source(value))
            else listOf(EtsReturn(expression(value.value, scope), source(value)))
        }
        is IrWhileLoop -> loop(value, scope, false)
        is IrDoWhileLoop -> loop(value, scope, true)
        is IrBreak -> jump(value.loop, value, "break")
        is IrContinue -> jump(value.loop, value, "continue")
        is IrWhen -> whenStatement(value, scope)
        is IrComposite -> value.statements.flatMap { statement(it, scope) }
        is IrContainerExpression -> {
            val nested = scope.fork()
            val contents = value.statements.flatMap { statement(it, nested) }
            if (contents.isEmpty()) emptyList() else listOf(EtsBlock(contents, source(value)))
        }
        is IrSimpleFunction -> diagnostics.unsupported(value,
            "Local function declarations are not supported by the ETS target (arkts-no-nested-funcs)")
        is IrThrow -> listOf(EtsThrow(expression(value.value, scope), source(value)))
        is IrTypeOperatorCall -> if (value.operator == IrTypeOperator.IMPLICIT_COERCION_TO_UNIT)
            statement(value.argument, scope) else listOf(expressionStatement(expression(value, scope)))
        is IrGetObjectValue -> if (value.type.isUnit()) emptyList() else listOf(expressionStatement(expression(value, scope)))
        is IrCall -> adaptedStatement(value, scope) ?: listOf(expressionStatement(call(value, scope, adapt = false)))
        is IrExpression -> listOf(expressionStatement(expression(value, scope)))
        else -> diagnostics.unsupported(value, "Unsupported language statement: ${value.javaClass.simpleName}")
    } }

    private tailrec fun expressionStatement(value: EtsExpression): EtsExpressionStatement {
        val lambda = (value as? EtsCall)?.callee as? EtsLambda
        val effect = lambda?.body?.singleOrNull() as? EtsExpressionStatement
        // Discard wrappers carry no scope or return boundary of their own.
        if (value is EtsCall && value.arguments.isEmpty() && lambda != null &&
            lambda.parameters.isEmpty() && lambda.returnType == EtsTypes.VOID && effect != null) {
            return expressionStatement(effect.expression)
        }
        return EtsExpressionStatement(value)
    }

    private fun jump(loop: IrLoop, element: IrElement, keyword: String): List<EtsStatement> {
        if (loop !in activeLoops) diagnostics.unsupported(element, "Loop jump crosses an expression or function boundary")
        return listOf(EtsJump(loopNames.getValue(loop), keyword == "continue", source(element)))
    }

    private fun loop(loop: IrLoop, scope: Scope, doWhile: Boolean): List<EtsStatement> {
        val label = loopNames.getOrPut(loop) { "__etsLoop${loopNames.size}" }
        activeLoops.add(loop)
        try {
            val bodyScope = scope.fork()
            val body = loop.body?.let { statement(it, bodyScope) } ?: emptyList()
            val conditionScope = scope.fork()
            val snapshots = linkedMapOf<EtsSymbol, EtsSymbol>()
            if (doWhile) loop.condition.acceptVoid(object : IrElementVisitorVoid {
                override fun visitFunction(declaration: IrFunction) = Unit
                override fun visitElement(element: IrElement) {
                    if (element is IrGetValue && element.symbol !in scope.bindings && element.symbol !in scope.aliases &&
                        element.symbol !in conditionScope.bindings) {
                        val variable = element.symbol.owner as? IrVariable
                        val local = bodyScope.bindings[element.symbol] as? EtsReference
                        if (variable == null || variable.isVar || variable.origin != IrDeclarationOrigin.FOR_LOOP_VARIABLE ||
                            local == null || body.none { it is EtsVariable && it.symbol == local.symbol }) {
                            diagnostics.unsupported(element, "Unsupported loop-condition reference to a body-local binding")
                        }
                        val snapshot = synthetic(freshName("__etsLoopValue", bodyScope), local.type, variable)
                        snapshots[local.symbol] = snapshot
                        conditionScope.bindings[element.symbol] = EtsReference(snapshot)
                    }
                    element.acceptChildrenVoid(this)
                }
            })
            // ETS do-while conditions cannot see body-scoped consts. Keep those consts
            // per iteration for closures; only the condition reads a value snapshot.
            val loweredBody = body.flatMap { statement ->
                val snapshot = (statement as? EtsVariable)?.symbol?.let(snapshots::get)
                if (snapshot == null) listOf(statement) else listOf(statement,
                    EtsExpressionStatement(EtsAssignment(EtsReference(snapshot),
                        EtsReference((statement as EtsVariable).symbol), statement.source)))
            }
            val condition = expression(loop.condition, conditionScope)
            return snapshots.values.map { EtsVariable(it, null, true) } +
                EtsLoop(label, condition, loweredBody, doWhile, source(loop))
        } finally { activeLoops.removeAt(activeLoops.lastIndex) }
    }

    private fun whenStatement(value: IrWhen, scope: Scope): List<EtsStatement> = listOf(EtsIf(value.branches.map { branch ->
        EtsBranch(if (branch is IrElseBranch) null else expression(branch.condition, scope), statement(branch.result, scope.fork()))
    }, source(value)))

    private fun whenExpression(value: IrWhen, scope: Scope): EtsExpression {
        if (value.type.isUnit()) return expressionScope { iife(whenStatement(value, scope), EtsTypes.VOID, value) }
        var tail: EtsExpression = iife(listOf(failure("No when branch matched", value)), EtsTypes.NEVER, value)
        for (branch in value.branches.asReversed()) {
            val result = expression(branch.result, scope.fork())
            tail = if (branch is IrElseBranch) result else EtsConditional(expression(branch.condition, scope), result, tail, type(value.type), source(value))
        }
        return tail
    }

    private fun blockExpression(block: IrContainerExpression, scope: Scope): EtsExpression = expressionScope {
        reserveNames(block)
        val nested = scope.fork()
        val lines = mutableListOf<EtsStatement>()
        block.statements.forEachIndexed { index, child ->
            if (index == block.statements.lastIndex && child is IrExpression && !block.type.isUnit()) {
                lines.add(EtsReturn(expression(child, nested), source(child)))
            } else lines.addAll(statement(child, nested))
        }
        iife(lines, type(block.type), block)
    }

    private fun <T> expressionScope(action: () -> T): T {
        val loops = activeLoops.toList()
        activeLoops.clear()
        expressionDepth++
        try { return action() } finally {
            expressionDepth--
            activeLoops.addAll(loops)
        }
    }

    private fun iife(lines: List<EtsStatement>, resultType: EtsType, element: IrElement): EtsExpression =
        EtsCall(EtsLambda(emptyList(), lines, resultType, source(element)), emptyList(), resultType, source(element))

    private fun discard(value: EtsExpression, element: IrElement): EtsExpression =
        etsDiscard(value, source(element))

    private fun failure(message: String, element: IrElement): EtsThrow = EtsThrow(
        EtsNew(EtsNamedType("Error"), listOf(EtsLiteral(message, EtsTypes.STRING, source(element))), source(element)), source(element))

    private fun typeOperator(value: IrTypeOperatorCall, scope: Scope): EtsExpression {
        if (value.operator == IrTypeOperator.IMPLICIT_COERCION_TO_UNIT && value.argument is IrCall) {
            adaptedStatement(value.argument as IrCall, scope)?.let {
                return iife(it, EtsTypes.VOID, value)
            }
            return discard(call(value.argument as IrCall, scope, adapt = false), value)
        }
        val operand = expression(value.argument, scope)
        return when (value.operator) {
            IrTypeOperator.IMPLICIT_CAST, IrTypeOperator.IMPLICIT_NOTNULL -> EtsCast(operand, type(value.typeOperand), source(value))
            IrTypeOperator.IMPLICIT_COERCION_TO_UNIT -> discard(operand, value)
            IrTypeOperator.INSTANCEOF, IrTypeOperator.NOT_INSTANCEOF, IrTypeOperator.SAFE_CAST, IrTypeOperator.CAST -> {
                val temporary = synthetic(freshName("__etsCast", scope), operand.type, value)
                val reference = EtsReference(temporary)
                fun binary(operator: String, left: EtsExpression, right: EtsExpression) =
                    EtsBinary(operator, left, right, EtsTypes.BOOLEAN, source(value))
                val nullValue = EtsLiteral(null, EtsTypes.NULL, source(value))
                fun scalar(name: String) = binary("===", EtsUnary("typeof", reference, EtsTypes.STRING, source(value)),
                    EtsLiteral(name, EtsTypes.STRING, source(value)))
                val target = value.typeOperand.classOrNull?.owner
                if (target?.kind == ClassKind.INTERFACE) {
                    diagnostics.unsupported(value, "Runtime interface discrimination is not supported")
                }
                val targetName = target?.fqNameWhenAvailable?.asString()
                val check = when (targetName) {
                    "kotlin.String" -> scalar("string")
                    "kotlin.Boolean" -> scalar("boolean")
                    "kotlin.Int", "kotlin.Short", "kotlin.Byte", "kotlin.Char", "kotlin.Float", "kotlin.Double" ->
                        diagnostics.unsupported(value, "Runtime boxed scalar discrimination is outside the first language slice")
                    "kotlin.Any" -> binary("&&", binary("!==", reference, nullValue), binary("!==", reference, EtsUndefined(source(value))))
                    else -> if (target != null && sourceFile(target) != null) binary("instanceof", reference, classReference(target, value))
                        else diagnostics.unsupported(value, "Unsupported runtime type check: ${value.typeOperand.render()}")
                }
                val condition = if (value.typeOperand.isNullable()) binary("||", binary("===", reference, nullValue), check) else check
                val cast = EtsCast(reference, type(value.typeOperand), source(value))
                val result = when (value.operator) {
                    IrTypeOperator.INSTANCEOF -> listOf(EtsReturn(condition, source(value)))
                    IrTypeOperator.NOT_INSTANCEOF -> listOf(EtsReturn(EtsUnary("!", condition, EtsTypes.BOOLEAN, source(value)), source(value)))
                    IrTypeOperator.SAFE_CAST -> listOf(EtsReturn(EtsConditional(condition, cast, nullValue, type(value.type), source(value)), source(value)))
                    else -> listOf(EtsIf(listOf(EtsBranch(EtsUnary("!", condition, EtsTypes.BOOLEAN, source(value)),
                        listOf(failure("ClassCastException", value)))), source(value)), EtsReturn(cast, source(value)))
                }
                iife(listOf(EtsVariable(temporary, operand, false)) + result, type(value.type), value)
            }
            else -> diagnostics.unsupported(value, "Unsupported type operator: ${value.operator}")
        }
    }

    override fun function(function: IrSimpleFunction, scope: Scope): EtsFunction = withFile(function) {
        reserveNames(function)
        val property = function.correspondingPropertySymbol?.owner
        val originalName = property?.let { identifier(it) } ?: identifier(function)
        val emittedName = if (property == null) overloadNaming.name(function) else originalName
        val sourceName = originalName.takeUnless { it == emittedName }
        if (function.isSuspend) {
            diagnostics.unsupported(function, "Suspend source methods are outside the first language slice")
        }
        val nested = scope.fork()
        function.dispatchReceiverParameter?.let { nested.bindings[it.symbol] = thisReference(function.parent as IrClass, function) }
        val parameters = parameters(function, nested)
        val genericParameters = typeParameters(function)
        val parentClass = function.parent as? IrClass
        val overrides = function.overriddenSymbols.flatMap { it.owner.collectRealOverrides() }
            .filter { sourceFile(it) != null }.distinct()
        if (parentClass != null && function.dispatchReceiverParameter != null && hasInheritance(parentClass)) {
            if (function.extensionReceiverParameter != null ||
                function.valueParameters.any { it.defaultValue != null }) {
                diagnostics.unsupported(function, "Extension and default-argument inherited methods are not supported")
            }
            if (overrides.any { overridden ->
                    if (overridden.typeParameters.size != function.typeParameters.size) return@any true
                    val owner = overridden.parent as? IrClass
                        ?: diagnostics.unsupported(function, "Inherited method requires a class declaration")
                    val substitution = ownerSubstitution(owner, parentClass.defaultType, function)
                    val methodParameters = makeTypeParameterSubstitutionMap(overridden, function)
                    // Class edges are instantiated first; only the paired method symbols are then rebound.
                    fun instantiated(type: IrType): IrType = substitution.substitute(type).substitute(methodParameters)
                    instantiated(overridden.returnType) != function.returnType ||
                        overridden.valueParameters.map { instantiated(it.type) } != function.valueParameters.map { it.type } ||
                        overridden.typeParameters.zip(function.typeParameters).any { (original, current) ->
                            original.superTypes.map(::instantiated) != current.superTypes
                        }
                }) {
                diagnostics.unsupported(function, "Inherited signatures must match exactly; covariance is not supported")
            }
        }
        // Interface properties are target field contracts, not abstract methods.
        val overrideIds = overrides.filter { property == null || (it.parent as? IrClass)?.kind != ClassKind.INTERFACE }
            .map { functionSymbol(it).id }.distinct()
        val kind = when {
            property?.getter == function -> EtsFunctionKind.GETTER
            property?.setter == function -> EtsFunctionKind.SETTER
            function.parent is IrClass -> EtsFunctionKind.METHOD
            else -> EtsFunctionKind.FUNCTION
        }
        if (parentClass?.kind == ClassKind.INTERFACE && function.body != null) {
            diagnostics.unsupported(function, "Default interface method bodies are not supported")
        }
        if (function.modality == Modality.ABSTRACT && parentClass != null) {
            if (function.body != null) diagnostics.unsupported(function, "Abstract method cannot have a body")
            return@withFile EtsFunction(emittedName, parameters, type(function.returnType), emptyList(),
                source(function), kind = kind, typeParameters = genericParameters,
                abstract = true, visibility = memberVisibility(function.visibility), overrides = overrideIds, sourceName = sourceName)
        }
        val body = function.body ?: diagnostics.unsupported(function, "Function has no source body: ${symbolName(function)}")
        val previousDepth = expressionDepth
        expressionDepth = 0
        returnTargets.add(function)
        try {
            val lines = statements(body, nested)
            EtsFunction(emittedName, parameters,
                type(function.returnType), lines, source(function), kind,
                static = function.parent is IrClass && function.dispatchReceiverParameter == null,
                visibility = if (parentClass == null) EtsVisibility.PUBLIC else memberVisibility(function.visibility),
                typeParameters = genericParameters, overrides = overrideIds, sourceName = sourceName)
        } finally {
            returnTargets.removeAt(returnTargets.lastIndex)
            expressionDepth = previousDepth
        }
    }

    private fun functionExpression(function: IrFunction, scope: Scope): EtsExpression {
        reserveNames(function)
        val nested = scope.fork()
        val parameters = parameters(function, nested)
        val body = function.body ?: diagnostics.unsupported(function, "Lambda has no body")
        val savedLoops = activeLoops.toList()
        activeLoops.clear()
        val previousDepth = expressionDepth
        expressionDepth = 0
        returnTargets.add(function)
        try {
            val statements = statements(body, nested)
            return EtsLambda(parameters, statements, type(function.returnType), source(function))
        } finally {
            returnTargets.removeAt(returnTargets.lastIndex)
            activeLoops.addAll(savedLoops)
            expressionDepth = previousDepth
        }
    }

    private fun parameters(function: IrFunction, scope: Scope): List<EtsParameter> {
        prepareCapturedParameters(function)
        val parameters = listOfNotNull(function.extensionReceiverParameter) + function.valueParameters
        parameters.forEach { bind(it, scope) }
        return parameters.map { parameter -> withElement(parameter) {
            EtsParameter((scope.bindings.getValue(parameter.symbol) as EtsReference).symbol,
                parameter.defaultValue?.expression?.let { expression(it, scope) })
        } }
    }

    override fun clazz(declaration: IrClass): EtsClass = withFile(declaration) {
        reserveNames(declaration)
        val inner = innerBinding(declaration)
        val typeParameters = typeParameters(declaration)
        val singleton = declaration.kind == org.jetbrains.kotlin.descriptors.ClassKind.OBJECT
        val isInterface = declaration.kind == ClassKind.INTERFACE
        if (!singleton && declaration.kind !in setOf(ClassKind.CLASS, ClassKind.INTERFACE)) {
            diagnostics.unsupported(declaration, "Only simple source classes are supported")
        }
        val parents = declaration.superTypes.filterNot { it.classOrNull?.owner?.fqNameWhenAvailable?.asString() == "kotlin.Any" }
        val parentClasses = parents.map { parent ->
            val klass = parent.classOrNull?.owner ?: unsupportedType(parent)
            if (sourceFile(klass) == null) {
                diagnostics.unsupported(declaration, "Only source class and interface heritage is supported")
            }
            type(parent)
            klass
        }
        val base = parentClasses.filter { it.kind != ClassKind.INTERFACE }.singleOrNull()
        if (parentClasses.count { it.kind != ClassKind.INTERFACE } > 1 ||
            (isInterface && base != null) || (singleton && parents.isNotEmpty())) {
            diagnostics.unsupported(declaration, "Unsupported class inheritance shape")
        }
        val baseType = parents.singleOrNull { it.classOrNull?.owner == base }?.let { type(it) as EtsNamedType }
        val interfaces = parents.filter { it.classOrNull?.owner?.kind == ClassKind.INTERFACE }.map { type(it) as EtsNamedType }
        if (hasInheritance(declaration)) validateInheritedMembers(declaration)
        if (isInterface) {
            declaration.declarations.firstOrNull { it !is IrSimpleFunction && it !is IrProperty }?.let {
                diagnostics.unsupported(it, "Only method and property signatures are supported in interfaces")
            }
            val signatures = declaration.declarations.filterNot { (it as? IrOverridableDeclaration<*>)?.isFakeOverride == true }
                .map { member -> when (member) {
                    is IrSimpleFunction -> function(member, Scope())
                    is IrProperty -> {
                        if (member.backingField != null || member.isDelegated ||
                            listOfNotNull(member.getter, member.setter).any { it.body != null || it.extensionReceiverParameter != null }) {
                            diagnostics.unsupported(member, "Interface property requires abstract non-extension accessors")
                        }
                        EtsField(synthetic(identifier(member), type(member.getter!!.returnType), member), readonly = !member.isVar)
                    }
                    else -> diagnostics.unsupported(member, "Unsupported interface declaration")
                } }
            return@withFile EtsClass(classNaming.name(declaration), signatures, source(declaration),
                kind = EtsClassKind.INTERFACE, interfaces = interfaces, typeParameters = typeParameters,
                sourceName = identifier(declaration).takeUnless { it == classNaming.name(declaration) })
        }
        val constructors = declaration.declarations.filterIsInstance<IrConstructor>()
        if (constructors.size != 1 || !isEtsNativeConstructor(constructors.single())) {
            diagnostics.unsupported(declaration, "A source class must have one native allocating constructor")
        }
        val constructor = constructors.single()
        val captures = declaration.declarations.filterIsInstance<IrField>().filter(::hasCaptureOrigin)
        captures.forEach(::capturedFieldSymbol)
        declaration.declarations.firstOrNull {
            it !is IrConstructor && it !is IrProperty && it !is IrSimpleFunction && it !is IrAnonymousInitializer &&
                it !in captures && it !== inner?.field
        }?.let {
            if (inner != null) rejectInner(inner, it, "Unsupported inner class declaration")
            diagnostics.unsupported(it, "Unsupported nested source class declaration")
        }
        val scope = Scope()
        declaration.thisReceiver?.let { scope.bindings[it.symbol] = thisReference(declaration, declaration) }
        val parameterText = parameters(constructor, scope)
        val fields = declaration.declarations.filterIsInstance<IrProperty>().filterNot { it.isFakeOverride }
        for (field in fields) {
            if (field.isDelegated || field.getter?.extensionReceiverParameter != null) {
                diagnostics.unsupported(field, "Delegated and extension properties are not supported")
            }
            if (field.getter == null || (field.backingField == null && !requiresAccessor(field))) {
                diagnostics.unsupported(field, "Property has neither storage nor a computed getter")
            }
        }
        val members = mutableListOf<EtsClassMember>()
        captures.forEach { members.add(EtsField(capturedFieldSymbol(it), visibility = EtsVisibility.PRIVATE)) }
        inner?.let {
            // Flattened descendants still traverse this registered outer link.
            val sharedLink = sourceFile(declaration)?.declarations?.filterIsInstance<IrClass>()
                ?.any { child -> sourceInnerClassBinding(child)?.outer === declaration } == true
            members.add(EtsField(outerFieldSymbol(it.field), visibility = if (sharedLink) EtsVisibility.PUBLIC else EtsVisibility.PRIVATE))
        }
        if (singleton) {
            val classType = classType(declaration)
            val field = synthetic("__etsSingleton", EtsNullableType(classType), declaration)
            val nullValue = EtsLiteral(null, EtsTypes.NULL, source(declaration))
            val access = EtsMember(classReference(declaration, declaration), field.name, field.type, source(declaration))
            members.add(EtsField(field, nullValue, visibility = EtsVisibility.PRIVATE, static = true))
            members.add(EtsFunction("__etsGetInstance", emptyList(), classType, listOf(
                EtsIf(listOf(EtsBranch(EtsBinary("===", access, nullValue, EtsTypes.BOOLEAN, source(declaration)),
                    listOf(EtsExpressionStatement(EtsAssignment(access, EtsNew(classType, emptyList(), source(declaration)), source(declaration)))))), source(declaration)),
                EtsReturn(EtsCast(access, classType, source(declaration)), source(declaration))),
                source(declaration), kind = EtsFunctionKind.METHOD, static = true))
        }
        fields.forEach { property -> withElement(property) {
            property.backingField?.let { field ->
                members.add(EtsField(synthetic(fieldName(field), type(field.type), property),
                    visibility = if (requiresAccessor(property)) EtsVisibility.PRIVATE else memberVisibility(property.visibility), readonly = !property.isVar))
            }
            if (requiresAccessor(property)) {
                listOfNotNull(property.getter, property.setter).forEach { members.add(function(it, scope)) }
            }
        } }
        val constructorBody = constructor.body as? IrBlockBody
            ?: diagnostics.unsupported(constructor, "Unsupported constructor body")
        val initialization = mutableListOf<EtsStatement>()
        val capturePrefix = constructorBody.statements.takeWhile {
            it is IrSetField && it.origin === IrStatementOrigin.STATEMENT_ORIGIN_INITIALIZER_OF_FIELD_FOR_CAPTURED_VALUE
        }.filterIsInstance<IrSetField>()
        val outerWrite = inner?.let { binding ->
            val write = constructorBody.statements.firstOrNull() as? IrSetField
            if (write == null || write.symbol !== binding.field.symbol ||
                (write.receiver as? IrGetValue)?.symbol !== declaration.thisReceiver?.symbol ||
                (write.value as? IrGetValue)?.symbol !== binding.parameter.symbol ||
                constructorBody.statements.filterIsInstance<IrSetField>().count { it.symbol === binding.field.symbol } != 1 ||
                constructorBody.statements.getOrNull(1) !is IrDelegatingConstructorCall) {
                rejectInner(binding, constructor, "Inner class requires one registered outer initialization before Any delegation")
            }
            write
        }
        if (!isEtsDispatchConstructor(constructor) && (constructorBody.statements.filterIsInstance<IrDelegatingConstructorCall>().size != 1 ||
            constructorBody.statements.getOrNull(capturePrefix.size + if (outerWrite != null) 1 else 0) !is IrDelegatingConstructorCall)) {
            diagnostics.unsupported(constructor, "A native constructor requires one direct leading delegation")
        }
        if (capturePrefix.isNotEmpty() && (!captureOwner(declaration) || parents.isNotEmpty()) ||
            capturePrefix.map { it.symbol.owner }.toSet() != captures.toSet() || capturePrefix.size != captures.size ||
            constructorBody.statements.filterIsInstance<IrSetField>().count {
                it.origin === IrStatementOrigin.STATEMENT_ORIGIN_INITIALIZER_OF_FIELD_FOR_CAPTURED_VALUE
            } != capturePrefix.size) {
            diagnostics.unsupported(constructor, "Captured fields require one official initialization prefix before Any delegation")
        }
        val previousInitialization = nativeInitialization
        nativeInitialization = NativeInitialization(declaration, base, baseType)
        try { constructorBody.statements.forEach { child -> when (child) {
            outerWrite -> {
                val binding = checkNotNull(inner)
                val field = outerFieldSymbol(binding.field)
                val at = innerSource(binding, child)
                val value = scope.bindings.getValue(binding.parameter.symbol) as EtsReference
                initialization.add(EtsExpressionStatement(EtsAssignment(
                    EtsMember(thisReference(declaration, binding.field), field.name, field.type, at, field.id),
                    EtsReference(value.symbol, at), at), at))
            }
            in capturePrefix -> {
                val write = child as IrSetField
                val parameter = (write.value as? IrGetValue)?.symbol?.owner as? IrValueParameter
                if ((write.receiver as? IrGetValue)?.symbol !== declaration.thisReceiver?.symbol ||
                    parameter == null || parameter.parent !== constructor || !isCapturedParameter(parameter)) {
                    diagnostics.unsupported(write.symbol.owner, "Invalid official captured-field constructor binding")
                }
                val field = capturedFieldSymbol(write.symbol.owner)
                val value = scope.bindings.getValue(parameter.symbol) as EtsReference
                initialization.add(EtsExpressionStatement(EtsAssignment(
                    EtsMember(thisReference(declaration, write.symbol.owner), field.name, field.type, field.source, field.id),
                    EtsReference(value.symbol, field.source), field.source), field.source))
            }
            else -> initialization.addAll(statement(child, scope))
        } } } finally { nativeInitialization = previousInitialization }
        members.add(EtsFunction("constructor", parameterText, EtsTypes.VOID, initialization, source(constructor),
            kind = EtsFunctionKind.CONSTRUCTOR, visibility = if (singleton) EtsVisibility.PRIVATE else memberVisibility(constructor.visibility)))
        declaration.declarations.filterIsInstance<IrSimpleFunction>().filter { !it.isFakeOverride }.forEach { method ->
            if (declaration.isData && method.origin == IrDeclarationOrigin.GENERATED_DATA_CLASS_MEMBER &&
                method.name.asString() in setOf("equals", "hashCode")) return@forEach
            members.add(function(method, scope))
        }
        EtsClass(classNaming.name(declaration), members, source(declaration), typeParameters = typeParameters,
            baseClass = baseType, interfaces = interfaces, abstract = declaration.modality == Modality.ABSTRACT,
            sourceName = identifier(declaration).takeUnless { it == classNaming.name(declaration) })
    }

    private fun constructorStatement(value: IrStatement, scope: Scope): List<EtsStatement> {
        val context = nativeInitialization ?: diagnostics.unsupported(value, "Constructor initialization outside its native owner")
        val declaration = context.owner
        if (value is IrDelegatingConstructorCall) {
            val target = value.symbol.owner.parent as? IrClass
            if (context.base != null) {
                if (target?.symbol != context.base.symbol || !isEtsNativeConstructor(value.symbol.owner))
                    diagnostics.unsupported(value, "Unsupported constructor delegation")
                rejectInitializationThis(value, declaration)
                return listOf(EtsSuperConstructorCall(checkNotNull(context.baseType), arguments(value, scope), source(value)))
            }
            if (target?.fqNameWhenAvailable?.asString() != "kotlin.Any") diagnostics.unsupported(value, "Unsupported constructor delegation")
            return emptyList()
        }
        if (value !is IrInstanceInitializerCall || value.classSymbol !== declaration.symbol)
            diagnostics.unsupported(value, "Initializer does not belong to its native constructor")
        return declaration.declarations.flatMap { initializer -> when (initializer) {
            is IrProperty -> initializer.backingField?.initializer?.expression?.let {
                if (hasInheritance(declaration)) rejectInitializationThis(it, declaration)
                listOf(EtsExpressionStatement(EtsAssignment(
                    EtsMember(thisReference(declaration, initializer), fieldName(initializer.backingField!!), type(initializer.backingField!!.type), source(initializer)),
                    expression(it, scope), source(initializer))))
            } ?: emptyList()
            is IrAnonymousInitializer -> {
                if (hasInheritance(declaration)) rejectInitializationThis(initializer.body, declaration)
                statements(initializer.body, scope.fork())
            }
            else -> emptyList()
        } }
    }

    private fun hasInheritance(declaration: IrClass): Boolean = declaration.kind == ClassKind.INTERFACE ||
        declaration.modality != Modality.FINAL || declaration.superTypes.any {
            it.classOrNull?.owner?.fqNameWhenAvailable?.asString() != "kotlin.Any"
        }

    private fun validateInheritedMembers(declaration: IrClass) {
        val functions = declaration.declarations.filterIsInstance<IrSimpleFunction>()
        functions.groupBy { it.name }.values.firstOrNull { it.size > 1 }?.let {
            diagnostics.unsupported(declaration, "Overloaded inherited methods are not supported")
        }
        val storage = mutableMapOf<String, IrProperty>()
        val methods = mutableMapOf<String, IrSimpleFunction>()
        val visited = mutableSetOf<IrClass>()
        fun visit(klass: IrClass) {
            if (!visited.add(klass)) return
            klass.declarations.filterIsInstance<IrSimpleFunction>().filter { !it.isFakeOverride && it.correspondingPropertySymbol == null }.forEach { method ->
                val previous = methods.putIfAbsent(method.name.asString(), method)
                if (previous != null && (DescriptorVisibilities.isPrivate(method.visibility) || DescriptorVisibilities.isPrivate(previous.visibility)))
                    diagnostics.unsupported(declaration, "Private method name shadowing in an inheritance hierarchy is not supported")
            }
            klass.declarations.filterIsInstance<IrProperty>().filterNot { it.isFakeOverride }.forEach { property ->
                if (klass.kind == ClassKind.INTERFACE) return@forEach
                val previous = storage.putIfAbsent(identifier(property), property)
                if (previous != null && !previous.overrides(property) && !property.overrides(previous)) {
                    diagnostics.unsupported(declaration, "Inherited storage name shadowing is not supported")
                }
            }
            klass.superTypes.mapNotNull { it.classOrNull?.owner }.filter { sourceFile(it) != null }.forEach(::visit)
        }
        visit(declaration)
    }

    private fun rejectInitializationThis(element: IrElement, declaration: IrClass) {
        rejectInheritedInitializerThis(element, declaration, diagnostics)
    }

    private fun functionSymbol(function: IrSimpleFunction): EtsSymbol {
        val property = function.correspondingPropertySymbol?.owner
        val originalName = property?.let { identifier(it) } ?: identifier(function)
        val emittedName = if (property == null) overloadNaming.name(function) else originalName
        return etsFunctionSymbol(emittedName,
            (listOfNotNull(function.extensionReceiverParameter) + function.valueParameters).map { type(it.type) },
            type(function.returnType), declarationSource(function), typeParameters(function), sourceName = originalName,
            kind = when (function) {
                property?.getter -> EtsFunctionKind.GETTER
                property?.setter -> EtsFunctionKind.SETTER
                else -> EtsFunctionKind.FUNCTION
            })
    }

    private fun hasCustomAccessor(property: IrProperty): Boolean =
        listOfNotNull(property.getter, property.setter).any { it.origin != IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR }

    private fun isVirtualProperty(property: IrProperty): Boolean = property.modality != Modality.FINAL ||
        property.getter?.overriddenSymbols.orEmpty().flatMap { it.owner.collectRealOverrides() }
            .any { (it.parent as? IrClass)?.kind != ClassKind.INTERFACE }

    private fun memberVisibility(visibility: org.jetbrains.kotlin.descriptors.DescriptorVisibility): EtsVisibility = when {
        DescriptorVisibilities.isPrivate(visibility) -> EtsVisibility.PRIVATE
        visibility == DescriptorVisibilities.PROTECTED -> EtsVisibility.PROTECTED
        else -> EtsVisibility.PUBLIC
    }

    private fun requiresAccessor(property: IrProperty): Boolean = hasCustomAccessor(property) || isVirtualProperty(property) ||
        property.setter?.visibility?.let { it != property.visibility } == true

    private fun fieldName(field: IrField): String {
        if (hasCaptureOrigin(field)) return capturedFieldSymbol(field).name
        if (field.origin === IrDeclarationOrigin.FIELD_FOR_OUTER_THIS) return outerFieldSymbol(field).name
        val property = field.correspondingPropertySymbol?.owner
        // Overriding a property changes dispatch, not the identity of each owner's backing field.
        if (property != null && isVirtualProperty(property)) {
            return "__etsField_${classNaming.name(field.parent as IrClass)}_${identifier(property)}"
        }
        return if (property != null && requiresAccessor(property)) "__etsField_${identifier(property)}" else identifier(field)
    }

    private fun bind(value: IrValueDeclaration, scope: Scope): EtsSymbol {
        val generated = isGeneratedName(value)
        val name = capturedParameters[value.symbol] ?: if (generated || etsRestrictedValueBinding(value.name.asString())) temporaryNames.getOrPut(value.symbol) {
            freshName(if (generated) "__etsTmp" else "${identifier(value)}_", scope)
        } else identifier(value)
        val symbol = symbols.getOrPut(value.symbol) { synthetic(name, withElement(value) { type(value.type) }, value) }
        scope.bindings[value.symbol] = EtsReference(symbol)
        return symbol
    }

    private fun hasCaptureOrigin(field: IrField): Boolean =
        field.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE

    private fun captureOwner(declaration: IrClass): Boolean = declaration.visibility == DescriptorVisibilities.LOCAL &&
        declaration.kind == ClassKind.CLASS && !declaration.isInner && !declaration.name.isSpecial && sourceFile(declaration) != null &&
        declaration.constructors.toList().let { it.size == 1 && isEtsNativeConstructor(it.single()) } &&
        declaration.superTypes.all { it.classOrNull?.owner?.fqNameWhenAvailable?.asString() == "kotlin.Any" }

    private fun capturedFieldSymbol(field: IrField): EtsSymbol {
        val owner = field.parent as? IrClass
        if (!hasCaptureOrigin(field) || owner == null || !captureOwner(owner) || field !in owner.declarations ||
            field.isStatic || field.isExternal || !field.isFinal || field.initializer != null) {
            diagnostics.unsupported(field, "Unsupported captured field ownership or shape")
        }
        capturedFields[field.symbol]?.let { return it }
        val fields = owner.declarations.filterIsInstance<IrField>().filter(::hasCaptureOrigin)
        val occupied = mutableSetOf("constructor")
        owner.declarations.filterIsInstance<IrProperty>().forEach { property ->
            occupied += identifier(property)
            property.backingField?.let { occupied += fieldName(it) }
        }
        owner.declarations.filterIsInstance<IrSimpleFunction>().filterNot { it.isFakeOverride }.forEach {
            occupied += functionSymbol(it).name
        }
        val table = NameTable<IrField>(reserved = (occupied + fields.map { it.name.asString() }).toMutableSet())
        for (capture in fields) {
            if (capture.parent !== owner || capture.isStatic || capture.isExternal || !capture.isFinal || capture.initializer != null)
                diagnostics.unsupported(capture, "Unsupported captured field ownership or shape")
            val original = identifier(capture)
            val name = if (original in occupied) table.declareFreshName(capture, original)
                else original.also { table.declareStableName(capture, it) }
            capturedFields[capture.symbol] = EtsSymbol("language:${nextSymbol++}", name, type(capture.type), declarationSource(capture))
        }
        return capturedFields.getValue(field.symbol)
    }

    private fun isCapturedParameter(parameter: IrValueParameter): Boolean =
        parameter.origin === BOUND_VALUE_PARAMETER || parameter.origin === BOUND_RECEIVER_PARAMETER

    private fun prepareCapturedParameters(function: IrFunction) {
        val owner = function.parent as? IrClass ?: return
        val inner = innerBinding(owner)
        val captures = if (inner != null) function.valueParameters.filter { it.origin === JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS }
            else if (captureOwner(owner)) function.valueParameters.filter(::isCapturedParameter) else return
        if (captures.isEmpty() || captures.all { it.symbol in capturedParameters }) return
        val occupied = function.valueParameters.filterNot { it in captures }.map { identifier(it) }.toMutableSet()
        val reserved = mutableSetOf<String>()
        sourceFile(owner)!!.module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrDeclarationWithName && !element.name.isSpecial) reserved += element.name.asString()
                // Root bindings are visible in flat output and through resolved module imports.
                if (element is IrClass && element.parent is IrFile) occupied += classNaming.name(element)
                if (element is IrSimpleFunction && element.parent is IrFile) occupied += overloadNaming.name(element)
                element.acceptChildrenVoid(this)
            }
        })
        reserved += occupied
        val table = NameTable<IrValueParameter>(reserved = reserved)
        for (parameter in captures) {
            val original = identifier(parameter)
            capturedParameters[parameter.symbol] = if (original in occupied) table.declareFreshName(parameter, original)
                else original.also { table.declareStableName(parameter, it) }
        }
    }

    private fun innerSource(binding: SourceInnerClassBinding, element: IrElement): SourceSpan =
        if (element.startOffset >= 0 && element.endOffset >= element.startOffset)
            SourceSpan(binding.source.file, element.startOffset, element.endOffset) else binding.source

    private fun rejectInner(binding: SourceInnerClassBinding, element: IrElement, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, innerSource(binding, element)))

    private fun innerBinding(owner: IrClass, visited: MutableSet<IrClass> = mutableSetOf()): SourceInnerClassBinding? {
        val binding = sourceInnerClassBinding(owner)
        if (binding == null) {
            if (owner.isInner) diagnostics.unsupported(owner, "Inner class has no registered source binding")
            return null
        }
        if (!visited.add(owner)) rejectInner(binding, owner, "Invalid registered inner class binding cycle")
        val field = binding.field
        val constructor = binding.constructor
        val parameter = binding.parameter
        if (!owner.isInner || owner.kind != ClassKind.CLASS || owner.name.isSpecial || owner.typeParameters.isNotEmpty() ||
            owner.superTypes.any { !it.isAny() } || binding.outer.kind != ClassKind.CLASS ||
            binding.outer.name.isSpecial || binding.outer.typeParameters.isNotEmpty() || binding.outer.parent !is IrFile ||
            sourceFile(owner)?.fileEntry?.name != binding.source.file || sourceFile(binding.outer) !== sourceFile(owner) ||
            field.parent !== owner || field !in owner.declarations || field.origin !== IrDeclarationOrigin.FIELD_FOR_OUTER_THIS ||
            field.isStatic || field.isExternal || !field.isFinal || field.initializer != null || field.type != binding.outer.defaultType ||
            constructor.parent !== owner || owner.constructors.toList() != listOf(constructor) || !isEtsNativeConstructor(constructor) ||
            constructor.valueParameters.firstOrNull() !== parameter || parameter.parent !== constructor ||
            parameter.origin !== JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS || parameter.type != field.type ||
            parameter.defaultValue != null || parameter.varargElementType != null) {
            rejectInner(binding, owner, "Invalid registered inner class binding")
        }
        if (binding.outer.isInner) innerBinding(binding.outer, visited)
        return binding
    }

    private fun outerFieldSymbol(field: IrField): EtsSymbol {
        val owner = field.parent as? IrClass ?: diagnostics.unsupported(field, "Outer field requires a registered class owner")
        val binding = innerBinding(owner) ?: diagnostics.unsupported(owner, "Outer field requires a registered inner class")
        if (binding.field !== field) rejectInner(binding, field, "Outer field differs from registered identity")
        outerFields[field.symbol]?.let { return it }
        val occupied = mutableSetOf("constructor")
        owner.declarations.filterIsInstance<IrProperty>().forEach { property ->
            occupied += identifier(property)
            property.backingField?.let { occupied += fieldName(it) }
        }
        owner.declarations.filterIsInstance<IrSimpleFunction>().filterNot { it.isFakeOverride }.forEach {
            occupied += functionSymbol(it).name
        }
        val original = identifier(field)
        val table = NameTable<IrField>(reserved = (occupied + original).toMutableSet())
        val name = if (original in occupied) table.declareFreshName(field, original)
            else original.also { table.declareStableName(field, it) }
        return EtsSymbol("language:${nextSymbol++}", name, type(field.type), innerSource(binding, field)).also {
            outerFields[field.symbol] = it
        }
    }

    private fun synthetic(name: String, type: EtsType, element: IrElement, external: Boolean = false): EtsSymbol =
        EtsSymbol("language:${nextSymbol++}", name, type, source(element), external)

    private fun classReference(declaration: IrClass, element: IrElement): EtsExpression =
        EtsReference(etsClassSymbol(classNaming.name(declaration), declarationSource(declaration),
            sourceName = identifier(declaration)), source(element))

    private fun declarationSource(declaration: IrDeclaration): SourceSpan =
        SourceSpan(sourceFile(declaration)?.fileEntry?.name ?: diagnostics.currentFile, declaration.startOffset, declaration.endOffset)

    private fun thisReference(declaration: IrClass, element: IrElement): EtsExpression =
        EtsReference(synthetic("this", classType(declaration), element, external = true))

    private fun classType(declaration: IrClass,
        arguments: List<EtsType> = declaration.typeParameters.map(::typeParameterType)): EtsNamedType =
        EtsNamedType(classNaming.name(declaration), arguments,
            etsClassSymbol(classNaming.name(declaration), declarationSource(declaration), sourceName = identifier(declaration)).id)

    private fun typeParameterType(parameter: IrTypeParameter): EtsTypeParameterType {
        val owner = parameter.parent as IrDeclarationWithName
        val source = declarationSource(owner)
        val kind = if (owner is IrClass) "class" else "function"
        // Official lifting preserves parameter offsets while copying their owning declaration.
        return EtsTypeParameterType("type-parameter:$kind:${source.file}:${source.start}:${owner.name}:${parameter.index}:${parameter.name}",
            identifier(parameter))
    }

    private fun typeParameters(declaration: IrTypeParametersContainer): List<EtsTypeParameter> =
        declaration.typeParameters.map { parameter ->
            if (parameter.isReified || parameter.variance != org.jetbrains.kotlin.types.Variance.INVARIANT) {
                diagnostics.unsupported(parameter, "Reified and variant type parameters are not supported")
            }
            val bound = parameter.superTypes.singleOrNull()
                ?: diagnostics.unsupported(parameter, "Multiple generic upper bounds are not supported")
            val reference = typeParameterType(parameter)
            EtsTypeParameter(reference.id, reference.name,
                if (bound.classOrNull?.owner?.fqNameWhenAvailable?.asString() == "kotlin.Any" && bound.isNullable()) null
                else withElement(parameter) { type(bound) })
        }

    private fun receiverSubstitution(owner: IrClass?, receiver: IrExpression?): Map<String, EtsType> {
        if (owner == null) return emptyMap()
        val actual = receiver?.type
            ?: diagnostics.unsupported(owner, "Generic member requires a resolved receiver type")
        val substitution = ownerSubstitution(owner, actual, receiver)
        return owner.typeParameters.associate { typeParameterType(it).id to type(substitution.substitute(it.defaultType)) }
    }

    private fun ownerSubstitution(owner: IrClass, receiverType: IrType, element: IrElement): AbstractIrTypeSubstitutor {
        val actual = receiverClassType(receiverType, element)
        if (owner.typeParameters.isEmpty()) return AbstractIrTypeSubstitutor.Empty
        val receiver = actual.classifier.owner as? IrClass
            ?: diagnostics.unsupported(element, "Generic member requires a resolved class receiver")
        if (actual.arguments.size != receiver.typeParameters.size || actual.arguments.any {
                it !is IrTypeProjection || it.variance != org.jetbrains.kotlin.types.Variance.INVARIANT
            }) diagnostics.unsupported(element, "Only invariant generic receiver arguments are supported")
        val instantiated = if (receiver == owner) actual else {
            val substitution = IrTypeSubstitutor(receiver.typeParameters.map { it.symbol }, actual.arguments)
            // The official utility composes every ancestor edge before applying this receiver's arguments.
            getAllSubstitutedSupertypes(receiver).filter { it.classifier == owner.symbol }
                .map { substitution.substitute(it) as IrSimpleType }.distinct().singleOrNull()
                ?: diagnostics.unsupported(element, "Missing or incompatible generic heritage paths to ${owner.name}")
        }
        if (instantiated.arguments.size != owner.typeParameters.size || instantiated.arguments.any {
                it !is IrTypeProjection || it.variance != org.jetbrains.kotlin.types.Variance.INVARIANT
            }) diagnostics.unsupported(element, "Only invariant generic heritage arguments are supported")
        return IrTypeSubstitutor(owner.typeParameters.map { it.symbol }, instantiated.arguments, allowEmptySubstitution = true)
    }

    private fun receiverClassType(receiverType: IrType, element: IrElement): IrSimpleType {
        var current = receiverType as? IrSimpleType
            ?: diagnostics.unsupported(element, "Member requires a resolved receiver type")
        val visited = mutableSetOf<IrTypeParameterSymbol>()
        while (current.classifier is IrTypeParameterSymbol) {
            val parameter = current.classifier as IrTypeParameterSymbol
            if (!visited.add(parameter)) diagnostics.unsupported(element, "Cyclic receiver bound chain")
            if (current.nullability != SimpleTypeNullability.NOT_SPECIFIED) {
                diagnostics.unsupported(element, "Only nonnullable receiver bounds are supported")
            }
            current = parameter.superTypes().singleOrNull() as? IrSimpleType
                ?: diagnostics.unsupported(element, "Receiver requires one available upper bound")
        }
        if (visited.isNotEmpty()) {
            val declaration = current.classifier.owner as? IrClass
            if (current.isNullable() || declaration == null || sourceFile(declaration) == null) {
                diagnostics.unsupported(element, "Receiver bound must be a nonnullable source class or interface")
            }
        }
        // A named F-bound is terminal here; its arguments stay intact for official owner substitution.
        return current
    }

    private fun freshName(prefix: String, scope: Scope): String {
        var candidate: String
        do { candidate = "$prefix${nextTemporary++}" }
        while (candidate in sourceNames || scope.bindings.values.any { it is EtsReference && it.symbol.name == candidate })
        return candidate
    }

    private fun reserveNames(element: IrElement) {
        element.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrDeclarationWithName && !isGeneratedName(element)) sourceNames.add(element.name.asString())
                element.acceptChildrenVoid(this)
            }
        })
    }

    private fun isGeneratedName(declaration: IrDeclarationWithName): Boolean = declaration.name.isSpecial ||
        declaration.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE ||
        declaration.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER ||
        // The official inliner strips <this> into a local named this, which ETS reserves.
        (declaration.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE_FOR_INLINED_PARAMETER &&
            declaration.name.asString() == "this")

    private fun identifier(value: IrDeclarationWithName): String {
        val name = value.name.asString()
        if (name.isEmpty() || !(name.first().isLetter() || name.first() == '_' || name.first() == '$') ||
            name.any { !(it.isLetterOrDigit() || it == '_' || it == '$') } ||
            name in setOf("function", "class", "var", "let", "const", "new", "default", "delete", "export", "import")) {
            diagnostics.unsupported(value, "Name cannot be preserved as a target identifier: $name")
        }
        return name
    }

    private fun constant(value: IrConst): EtsExpression {
        val constant = when (val constant = value.value) {
        null -> null
        is String -> constant
        is Char -> constant.toString()
        is Boolean, is Byte, is Short, is Int -> constant
        is Long -> if (constant in -9007199254740991L..9007199254740991L) constant
            else diagnostics.unsupported(value, "Long constant cannot be represented exactly as a target number")
        is Float -> if (constant.isFinite()) constant else diagnostics.unsupported(value, "Non-finite float constant")
        is Double -> if (constant.isFinite()) constant else diagnostics.unsupported(value, "Non-finite double constant")
        else -> diagnostics.unsupported(value, "Unsupported constant type: ${constant.javaClass.simpleName}")
        }
        val targetType = when (constant) {
            null -> EtsTypes.NULL
            is String -> EtsTypes.STRING
            is Boolean -> EtsTypes.BOOLEAN
            else -> EtsTypes.NUMBER
        }
        return EtsLiteral(constant, targetType, source(value))
    }

    private fun <T> withFile(declaration: IrDeclaration, action: () -> T): T {
        val previous = diagnostics.currentFile
        sourceFile(declaration)?.let { diagnostics.currentFile = it.fileEntry.name }
        try { return withElement(declaration, action) } finally { diagnostics.currentFile = previous }
    }

    private fun <T> withElement(element: IrElement, action: () -> T): T {
        val previous = currentElement
        currentElement = element
        try { return action() } finally { currentElement = previous }
    }
}
