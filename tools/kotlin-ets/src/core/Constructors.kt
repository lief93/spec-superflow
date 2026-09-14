@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.ir.ValueRemapper
import org.jetbrains.kotlin.backend.common.ir.moveBodyTo
import org.jetbrains.kotlin.backend.common.lower.DeclarationIrBuilder
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.irAttribute
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.builders.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.Name

private val ETS_SECONDARY_CONSTRUCTOR by IrDeclarationOriginImpl
private var IrConstructor.nativeAllocationOwner: IrClass? by irAttribute(followAttributeOwner = false)

internal fun isEtsNativeConstructor(constructor: IrConstructor): Boolean =
    constructor.isPrimary || isEtsDispatchConstructor(constructor) || constructor.nativeAllocationOwner?.let { it === constructor.parent } == true

internal fun nativeConstructorRoot(owner: IrClass): IrConstructor? = owner.primaryConstructor ?: owner.constructors.singleOrNull {
    val delegation = (it.body as? IrBlockBody)?.statements?.filterIsInstance<IrDelegatingConstructorCall>()?.singleOrNull()
    delegation != null && delegation.symbol.owner.parent !== owner
}

internal fun rejectInheritedInitializerThis(element: IrElement, owner: IrClass, diagnostics: DiagnosticSink,
    allowFieldWrites: Boolean = false, allowFieldReads: Boolean = false) {
    element.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        private fun ownThis(value: IrExpression?) = (value as? IrGetValue)?.symbol == owner.thisReceiver?.symbol
        override fun visitGetField(expression: IrGetField) {
            val field = expression.symbol.owner
            val property = field.correspondingPropertySymbol?.owner
            val stored = property?.parent === owner && property.modality == Modality.FINAL &&
                property.getter?.origin == IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR
            val captured = field.isFinal && (field.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE ||
                field === sourceInnerClassBinding(owner)?.field)
            if (allowFieldReads && field.parent === owner && ownThis(expression.receiver) && !field.isStatic && (stored || captured)) return
            super.visitGetField(expression)
        }
        override fun visitSetField(expression: IrSetField) {
            if (allowFieldWrites && expression.symbol.owner.parent === owner && ownThis(expression.receiver))
                expression.value.acceptVoid(this)
            else super.visitSetField(expression)
        }
        override fun visitCall(expression: IrCall) {
            val property = expression.symbol.owner.correspondingPropertySymbol?.owner
            if (allowFieldWrites && property?.parent === owner && property.modality == Modality.FINAL &&
                property.setter?.symbol == expression.symbol && expression.symbol.owner.origin == IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR &&
                ownThis(expression.dispatchReceiver))
                expression.symbol.owner.valueParameters.indices.forEach { expression.getValueArgument(it)?.acceptVoid(this) }
            else if (allowFieldReads && property?.parent === owner && property.modality == Modality.FINAL &&
                property.getter?.symbol == expression.symbol && expression.symbol.owner.origin == IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR &&
                ownThis(expression.dispatchReceiver))
                expression.symbol.owner.valueParameters.indices.forEach { expression.getValueArgument(it)?.acceptVoid(this) }
            else super.visitCall(expression)
        }
        override fun visitGetValue(expression: IrGetValue) {
            if (expression.symbol == owner.thisReceiver?.symbol)
                diagnostics.unsupported(expression, "Using this during inherited initialization is not supported")
        }
    })
}

/** Moving a derived capture write past super is safe only when ancestors cannot observe this. */
internal fun validateCapturedHeritage(owner: IrClass) {
    owner.getAllSuperclasses().filter { !it.defaultType.isAny() && it.kind != ClassKind.INTERFACE }
        .sortedBy { it.fqNameWhenAvailable?.asString() ?: it.name.asString() }.forEach { ancestor ->
            val sourceDiagnostic = DiagnosticSink(owner.file.fileEntry.name)
            val diagnostics = DiagnosticSink(ancestor.fileOrNull?.fileEntry?.name ?: owner.file.fileEntry.name)
            if (!ancestor.constructors.any()) sourceDiagnostic.unsupported(owner, "Captured inheritance requires source ancestor constructors")
            ancestor.constructors.forEach { constructor ->
                val body = constructor.body ?: sourceDiagnostic.unsupported(owner, "Captured inheritance requires source ancestor constructor bodies")
                rejectInheritedInitializerThis(body, ancestor, diagnostics, allowFieldWrites = true, allowFieldReads = true)
            }
            ancestor.declarations.mapNotNull { declaration -> when (declaration) {
                is IrProperty -> declaration.backingField?.initializer
                is IrField -> declaration.initializer
                is IrAnonymousInitializer -> declaration.body
                else -> null
            } }.forEach { rejectInheritedInitializerThis(it, ancestor, diagnostics, allowFieldReads = true) }
        }
}

/** Runs after inlining and official capture/outer binding; factories retain those explicit arguments. */
internal fun lowerSecondaryConstructors(input: JvmFir2IrPipelineArtifact) {
    val module = input.result.irModuleFragment
    val constructors = mutableListOf<IrConstructor>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitConstructor(declaration: IrConstructor) {
            if (!isEtsNativeConstructor(declaration)) constructors.add(declaration)
            super.visitConstructor(declaration)
        }
    })
    if (constructors.isEmpty()) return
    constructors.forEach { constructor ->
        val owner = constructor.parentAsClass
        val diagnostics = DiagnosticSink(constructor.file.fileEntry.name)
        if (generateSequence(owner as IrDeclaration) { it.parent as? IrDeclaration }.any {
                it is IrFunction || it is IrClass && it.isInner && sourceInnerClassBinding(it) == null
            }) diagnostics.unsupported(constructor, "Secondary constructors in local or inner classes require capture-aware allocation")
        val body = constructor.body as? IrBlockBody
        val delegation = body?.statements?.filterIsInstance<IrDelegatingConstructorCall>()?.singleOrNull()
        val prefix = body?.statements?.takeWhile { it !== delegation }.orEmpty()
        val outer = sourceInnerClassBinding(owner)?.field
        if (delegation == null || prefix.any { it !is IrSetField ||
                it.origin !== IrStatementOrigin.STATEMENT_ORIGIN_INITIALIZER_OF_FIELD_FOR_CAPTURED_VALUE && it.symbol.owner !== outer } ||
            prefix.isNotEmpty() && delegation.symbol.owner.parent === owner)
            diagnostics.unsupported(constructor, "Secondary constructor requires one direct leading delegation")
    }
    // Preserve the source allocation root, including a secondary that directly calls super.
    constructors.groupBy { it.parentAsClass }.forEach { (owner, secondary) ->
        val root = nativeConstructorRoot(owner) ?: DiagnosticSink(owner.file.fileEntry.name).unsupported(owner,
            "A source class requires one native allocating constructor root")
        if (!root.isPrimary) root.nativeAllocationOwner = owner
        secondary.filter { it !== root }.forEach { constructor ->
            val diagnostics = DiagnosticSink(constructor.file.fileEntry.name)
            if (owner.modality == Modality.ABSTRACT || owner.modality == Modality.SEALED)
                diagnostics.unsupported(constructor, "Abstract secondary constructors require derived-instance allocation")
            if (((constructor.body as IrBlockBody).statements.first() as IrDelegatingConstructorCall).symbol.owner.parent !== owner)
                diagnostics.unsupported(constructor, "Secondary constructor requires one leading this delegation")
        }
    }
    constructors.removeAll(::isEtsNativeConstructor)
    // A superclass factory must never allocate a base object in place of a derived instance.
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitConstructor(declaration: IrConstructor) {
            declaration.body?.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
                override fun visitDelegatingConstructorCall(expression: IrDelegatingConstructorCall) {
                    if (expression.symbol.owner in constructors &&
                        expression.symbol.owner.parent !== declaration.parent)
                        DiagnosticSink(declaration.file.fileEntry.name).unsupported(expression,
                            "Delegation to a superclass secondary constructor requires derived-instance allocation")
                    super.visitDelegatingConstructorCall(expression)
                }
            })
            super.visitConstructor(declaration)
        }
    })
    if (constructors.isEmpty()) return
    val context = createJvmLoweringContext(input)
    val reserved = mutableSetOf<String>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrDeclarationWithName && !element.name.isSpecial) reserved.add(element.name.asString())
            element.acceptChildrenVoid(this)
        }
    })
    val names = NameTable<IrConstructor>(reserved = reserved)
    val factories = constructors.sortedWith(compareBy({ it.file.fileEntry.name }, { it.startOffset })).associateWith { constructor ->
        val owner = constructor.parentAsClass
        context.irFactory.createStaticFunctionWithReceivers(owner,
            Name.identifier(names.declareFreshName(constructor, "new_${owner.name}")), constructor,
            origin = ETS_SECONDARY_CONSTRUCTOR, typeParametersFromContext = owner.typeParameters,
            remapMultiFieldValueClassStructure = { _, _, _ -> })
    }
    factories.forEach { (constructor, factory) ->
        val owner = constructor.parentAsClass
        factory.body = constructor.moveBodyTo(factory)
        val parameters = constructor.parameters.zip(factory.parameters).associate { (from, to) -> from.symbol to to.symbol }
        factory.parameters.forEach { it.defaultValue?.transformChildrenVoid(ValueRemapper(parameters)) }
        val types = (owner.typeParameters + constructor.typeParameters).zip(factory.typeParameters).toMap()
        factory.remapTypes(object : TypeRemapper {
            override fun enterScope(irTypeParametersContainer: IrTypeParametersContainer) = Unit
            override fun leaveScope() = Unit
            override fun remapType(type: IrType): IrType = type.remapTypeParameters(constructor, factory, types)
        })
        val body = factory.body as IrBlockBody
        val delegation = body.statements.removeAt(0) as IrDelegatingConstructorCall
        val creation = IrConstructorCallImpl.fromSymbolOwner(delegation.startOffset, delegation.endOffset,
            factory.returnType, delegation.symbol).apply {
            copyValueArgumentsFrom(delegation, delegation.symbol.owner)
            delegation.typeArguments.forEachIndexed { index, type -> typeArguments[index] = type }
        }
        val builder = DeclarationIrBuilder(IrGeneratorContextBase(context.irBuiltIns), factory.symbol,
            constructor.startOffset, constructor.endOffset)
        factory.body = builder.irBlockBody {
            val instance = irTemporary(creation, "instance")
            body.transformChildrenVoid(ValueRemapper(mapOf(owner.thisReceiver!!.symbol to instance.symbol)))
            body.transformChildrenVoid(object : IrElementTransformerVoid() {
                override fun visitReturn(expression: IrReturn): IrExpression {
                    expression.transformChildrenVoid(this)
                    if (expression.returnTargetSymbol == factory.symbol) expression.value = irGet(instance)
                    return expression
                }
            })
            body.statements.forEach { +it }
            +irReturn(irGet(instance))
        }
        val position = owner.declarations.indexOf(constructor)
        owner.declarations[position] = factory
    }
    module.files.forEach { file -> file.transformChildrenVoid(object : IrElementTransformerVoid() {
        override fun visitConstructorCall(expression: IrConstructorCall): IrExpression {
            expression.transformChildrenVoid(this)
            val factory = factories[expression.symbol.owner] ?: return expression
            return IrCallImpl(expression.startOffset, expression.endOffset, expression.type,
                factory.symbol, expression.typeArguments.size).apply {
                copyValueArgumentsFrom(expression, factory)
                expression.typeArguments.forEachIndexed { index, type -> typeArguments[index] = type }
            }
        }
    }) }
    module.patchDeclarationParents()
}
