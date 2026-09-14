@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.ir.ValueRemapper
import org.jetbrains.kotlin.backend.common.ir.moveBodyTo
import org.jetbrains.kotlin.backend.common.lower.DeclarationIrBuilder
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
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

/** Runs after inlining can expand constructor references into calls, before local capture lowering. */
internal fun lowerSecondaryConstructors(input: JvmFir2IrPipelineArtifact) {
    val module = input.result.irModuleFragment
    val constructors = mutableListOf<IrConstructor>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitConstructor(declaration: IrConstructor) {
            if (!declaration.isPrimary) constructors.add(declaration)
            super.visitConstructor(declaration)
        }
    })
    if (constructors.isEmpty()) return
    constructors.forEach { constructor ->
        val owner = constructor.parentAsClass
        val diagnostics = DiagnosticSink(constructor.file.fileEntry.name)
        if (constructor.visibility == DescriptorVisibilities.PROTECTED)
            diagnostics.unsupported(constructor, "Protected secondary constructors require protected target member visibility")
        if (owner.primaryConstructor == null) diagnostics.unsupported(constructor,
            "Secondary constructors without a primary require an ETS allocation and initializer model")
        if (owner.modality == Modality.ABSTRACT || owner.modality == Modality.SEALED)
            diagnostics.unsupported(constructor, "Abstract secondary constructors require derived-instance allocation")
        if (generateSequence(owner as IrDeclaration) { it.parent as? IrDeclaration }.any {
                it is IrFunction || it is IrClass && it.isInner
            }) diagnostics.unsupported(constructor, "Secondary constructors in local or inner classes require capture-aware allocation")
        val body = constructor.body as? IrBlockBody
        val delegation = body?.statements?.firstOrNull() as? IrDelegatingConstructorCall
        if (delegation?.symbol?.owner?.parent !== owner ||
            body.statements.filterIsInstance<IrDelegatingConstructorCall>().size != 1)
            diagnostics.unsupported(constructor, "Secondary constructor requires one leading this delegation")
    }
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
