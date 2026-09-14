@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.CommonBackendContext
import org.jetbrains.kotlin.backend.common.defaultArgumentsOriginalFunction
import org.jetbrains.kotlin.backend.common.ir.Ir
import org.jetbrains.kotlin.backend.common.ir.moveBodyTo
import org.jetbrains.kotlin.backend.common.lower.*
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.builders.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrCallImpl
import org.jetbrains.kotlin.ir.expressions.impl.IrTypeOperatorCallImpl
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.types.impl.makeTypeProjection
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.Name
import java.util.IdentityHashMap

internal val ETS_DEFAULT_VISIBILITY_BRIDGE by IrDeclarationOriginImpl

/** Common default dispatch is resolved before ETS emission; user method bodies stay callable. */
internal fun lowerInheritedDefaults(input: JvmFir2IrPipelineArtifact) {
    val module = input.result.irModuleFragment
    val providers = mutableSetOf<IrSimpleFunction>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitSimpleFunction(declaration: IrSimpleFunction) {
            val owner = declaration.parent as? IrClass
            if (owner != null && declaration.dispatchReceiverParameter != null &&
                !declaration.isFakeOverride && !declaration.isInline && !declaration.isSuspend &&
                declaration.extensionReceiverParameter == null && declaration.contextReceiverParametersCount == 0 &&
                declaration.valueParameters.any { it.defaultValue != null } &&
                (owner.modality != Modality.FINAL || owner.superTypes.any {
                    it.classOrNull?.owner?.fqNameWhenAvailable?.asString() != "kotlin.Any"
                })) providers.add(declaration)
            super.visitSimpleFunction(declaration)
        }
    })
    if (providers.isEmpty()) return
    providers.forEach { provider ->
        if (generateSequence(provider.parent as? IrDeclaration) { it.parent as? IrDeclaration }.any {
                it is IrFunction || it is IrClass && it.isInner && sourceInnerClassBinding(it) == null
            }) DiagnosticSink(provider.file.fileEntry.name).unsupported(provider,
                "Inherited default providers in local or inner classes require capture lowering before static dispatch")
    }
    val realContext = createJvmLoweringContext(input)
    val context = object : CommonBackendContext by realContext {
        override val ir = object : Ir() { override val symbols = realContext.ir.symbols }
    }
    val factory = MaskedDefaultArgumentFunctionFactory(context)
    val stubs = mutableSetOf<IrFunction>()
    val generator = object : DefaultArgumentStubGenerator<CommonBackendContext>(context, factory) {
        override fun defaultArgumentStubVisibility(function: IrFunction) = function.visibility
        override fun getOriginForCallToImplementation(): IrStatementOrigin = IrStatementOrigin.DEFAULT_DISPATCH_CALL
        // JVM stubs mutate parameters for bytecode inlining. ETS selects immutable
        // locals so default closures retain the value visible when they are created.
        override fun IrBlockBodyBuilder.selectArgumentOrDefault(defaultFlag: IrExpression,
            parameter: IrValueParameter, default: IrExpression): IrValueDeclaration =
            irTemporary(irIfThenElse(parameter.type, irNotEquals(defaultFlag, irInt(0)), default, irGet(parameter)))
        override fun transformFlat(declaration: IrDeclaration): List<IrDeclaration>? {
            if (declaration !in providers) return null
            return super.transformFlat(declaration)?.also { generated ->
                stubs.addAll(generated.filterIsInstance<IrFunction>().filter { it !== declaration })
            }
        }
    }
    module.files.forEach(generator::lower)
    val sourceCalls = IdentityHashMap<IrCall, IrSimpleFunction>()
    val injector = object : DefaultParameterInjector<CommonBackendContext>(context, factory) {
        override fun defaultArgumentStubVisibility(function: IrFunction) = function.visibility
        override fun visitCall(expression: IrCall): IrExpression {
            val original = expression.symbol.owner
            val result = super.visitCall(expression)
            fun last(value: IrExpression): IrCall? = when (value) {
                is IrCall -> value
                is IrTypeOperatorCall -> last(value.argument)
                is IrContainerExpression -> (value.statements.lastOrNull() as? IrExpression)?.let { last(it) }
                else -> null
            }
            last(result)?.takeIf { it.symbol.owner in stubs }?.let { sourceCalls[it] = original }
            return result
        }
        override fun shouldReplaceWithSyntheticFunction(functionAccess: IrFunctionAccessExpression): Boolean =
            super.shouldReplaceWithSyntheticFunction(functionAccess) &&
                (functionAccess as? IrCall)?.superQualifierSymbol == null &&
                factory.findBaseFunctionWithDefaultArgumentsFor(functionAccess.symbol.owner, true, true) in providers
    }
    module.files.forEach(injector::lower)
    // Keep ordinary ETS defaults outside this family; these calls now use the official provider.
    (providers + stubs).forEach { function -> function.valueParameters.forEach { it.defaultValue = null } }
    // Like the JVM static-default phase, make the receiver explicit. Keeping a real
    // helper also preserves recursive defaults without recursively expanding code.
    val reserved = mutableSetOf<String>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrDeclarationWithName && !element.name.isSpecial) reserved.add(element.name.asString())
            element.acceptChildrenVoid(this)
        }
    })
    val names = NameTable<IrFunction>(reserved = reserved)
    val helpers = stubs.sortedWith(compareBy({ it.file.fileEntry.name }, { it.startOffset }, { it.name.asString() })).associateWith { stub ->
        val owner = stub.parentAsClass
        val destination = if (owner.kind == ClassKind.INTERFACE) stub.file else owner
        val helper = context.irFactory.createStaticFunctionWithReceivers(destination,
            Name.identifier(names.declareFreshName(stub, "${owner.name}_${stub.name}")), stub,
            typeParametersFromContext = owner.typeParameters,
            remapMultiFieldValueClassStructure = { _, _, _ -> })
        // This official attribute does not follow copyAttributes' attributeOwnerId.
        helper.defaultArgumentsOriginalFunction = stub.defaultArgumentsOriginalFunction
        // Inner lowering can use the class receiver inside a default lambda.
        // Moving to a static helper must remap that identity as well as parameters.
        helper.body = stub.moveBodyTo(helper, stub.parameters.zip(helper.parameters).toMap() +
            (checkNotNull(owner.thisReceiver) to helper.valueParameters.first()))
        val parameters = (owner.typeParameters + stub.typeParameters).zip(helper.typeParameters).toMap() +
            stub.defaultArgumentsOriginalFunction!!.typeParameters.zip(helper.typeParameters.drop(owner.typeParameters.size))
        helper.remapTypes(object : TypeRemapper {
            override fun enterScope(irTypeParametersContainer: IrTypeParametersContainer) = Unit
            override fun leaveScope() = Unit
            override fun remapType(type: IrType): IrType = type.remapTypeParameters(stub, helper, parameters)
        })
        helper.transformChildrenVoid(object : IrElementTransformerVoid() {
            override fun visitCall(expression: IrCall): IrExpression {
                expression.transformChildrenVoid(this)
                if (expression.origin != IrStatementOrigin.DEFAULT_DISPATCH_CALL) return expression
                expression.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
                    val argument = expression.getValueArgument(index) ?: return@forEachIndexed
                    val expected = parameter.type.remapTypeParameters(stub, helper, parameters)
                    if (argument.type != expected) expression.putValueArgument(index,
                        IrTypeOperatorCallImpl(argument.startOffset, argument.endOffset, expected,
                            IrTypeOperator.IMPLICIT_CAST, expected, argument))
                }
                return expression
            }
        })
        helper
    }
    helpers.values.forEach { (it.parent as IrDeclarationContainer).declarations.add(it) }
    val bridges = mutableMapOf<Pair<IrSimpleFunction, IrClass>, IrSimpleFunction>()
    val bridgeNames = NameTable<Pair<IrSimpleFunction, IrClass>>(reserved = (reserved + helpers.values.map { it.name.asString() }).toMutableSet())
    fun accessibleHelper(call: IrCall, helper: IrSimpleFunction): IrSimpleFunction {
        val sourceCall = sourceCalls[call] ?: return helper
        val visible = if (sourceCall.isFakeOverride) sourceCall.collectRealOverrides().singleOrNull() ?: return helper else sourceCall
        val owner = visible.parent as? IrClass ?: return helper
        if (helper.visibility != DescriptorVisibilities.PROTECTED || visible.visibility != DescriptorVisibilities.PUBLIC ||
            owner === helper.parent) return helper
        // Widening overrides own the public entry; the provider and its default body stay protected.
        return bridges.getOrPut(helper to owner) {
            context.irFactory.createStaticFunctionWithReceivers(owner,
                Name.identifier(bridgeNames.declareFreshName(helper to owner, "${visible.name}\$default")), helper,
                remapMultiFieldValueClassStructure = { _, _, _ -> }).apply bridge@{
                origin = ETS_DEFAULT_VISIBILITY_BRIDGE
                visibility = visible.visibility
                startOffset = visible.startOffset
                endOffset = visible.endOffset
                returnType = helper.returnType.remapTypeParameters(helper, this, helper.typeParameters.zip(typeParameters).toMap())
                val builder = DeclarationIrBuilder(IrGeneratorContextBase(context.irBuiltIns), symbol, startOffset, endOffset)
                body = builder.irBlockBody {
                    +builder.irReturn(builder.irCall(helper).apply {
                        type = this@bridge.returnType
                        this@bridge.typeParameters.forEachIndexed { index, parameter -> putTypeArgument(index, parameter.defaultType) }
                        this@bridge.valueParameters.forEachIndexed { index, parameter -> putValueArgument(index, builder.irGet(parameter)) }
                    })
                }
            }
        }
    }
    module.files.forEach { file -> file.transformChildrenVoid(object : IrElementTransformerVoid() {
        override fun visitCall(expression: IrCall): IrExpression {
            expression.transformChildrenVoid(this)
            val stub = expression.symbol.owner
            val helper = helpers[stub]?.let { accessibleHelper(expression, it) } ?: return expression
            val owner = stub.parentAsClass
            val diagnostics = DiagnosticSink(file.fileEntry.name)
            val ownerType = defaultReceiverType(owner, expression, diagnostics)
            val types = ownerType.arguments.map { it.typeOrNull!! } + expression.typeArguments.map {
                it ?: diagnostics.unsupported(expression, "Default dispatch requires resolved method type arguments")
            }
            val sourceSubstitution = IrTypeSubstitutor((owner.typeParameters + stub.typeParameters).map { it.symbol },
                types.map { makeTypeProjection(it, org.jetbrains.kotlin.types.Variance.INVARIANT) },
                allowEmptySubstitution = true)
            // Common injection types omitted-argument sentinels with the provider's T.
            // They belong to this call site, not to the removed provider stub's scope.
            expression.remapTypes(object : TypeRemapper {
                override fun enterScope(irTypeParametersContainer: IrTypeParametersContainer) = Unit
                override fun leaveScope() = Unit
                override fun remapType(type: IrType): IrType = sourceSubstitution.substitute(type)
            })
            val substitution = IrTypeSubstitutor(helper.typeParameters.map { it.symbol },
                types.map { makeTypeProjection(it, org.jetbrains.kotlin.types.Variance.INVARIANT) },
                allowEmptySubstitution = true)
            return IrCallImpl(expression.startOffset, expression.endOffset,
                substitution.substitute(helper.returnType), helper.symbol, types.size).also { call ->
                call.copyValueArgumentsFrom(expression, helper, receiversAsArguments = true)
                for (index in call.arguments.indices) {
                    val argument = call.arguments[index] as? IrComposite ?: continue
                    if (argument.origin == IrStatementOrigin.DEFAULT_VALUE && argument.statements.size == 1 &&
                        argument.statements.single() is IrConst) call.arguments[index] = argument.statements.single() as IrConst
                }
                types.forEachIndexed { index, type -> call.typeArguments[index] = type }
            }
        }
    }) }
    bridges.values.forEach { (it.parent as IrClass).declarations.add(it) }
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitFile(declaration: IrFile) {
            declaration.declarations.removeAll { it in stubs }
            super.visitFile(declaration)
        }
        override fun visitClass(declaration: IrClass) {
            declaration.declarations.removeAll { it in stubs }
            super.visitClass(declaration)
        }
    })
    module.patchDeclarationParents()
}

private fun defaultReceiverType(owner: IrClass, call: IrCall, diagnostics: DiagnosticSink): IrSimpleType {
    var receiver = call.dispatchReceiver?.type as? IrSimpleType
        ?: diagnostics.unsupported(call, "Default dispatch requires a resolved receiver type")
    val visited = mutableSetOf<org.jetbrains.kotlin.ir.symbols.IrClassifierSymbol>()
    while (receiver.classifier.owner is IrTypeParameter) {
        val parameter = receiver.classifier.owner as IrTypeParameter
        if (!visited.add(receiver.classifier) || parameter.superTypes.size != 1)
            diagnostics.unsupported(call, "Default dispatch requires one noncyclic receiver bound")
        receiver = parameter.superTypes.single() as? IrSimpleType
            ?: diagnostics.unsupported(call, "Default dispatch requires a class receiver bound")
    }
    val receiverClass = receiver.classOrNull?.owner
        ?: diagnostics.unsupported(call, "Default dispatch requires a class receiver")
    fun checked(type: IrSimpleType, declaration: IrClass): IrSimpleType {
        if (type.arguments.size != declaration.typeParameters.size || type.arguments.any {
                it !is IrTypeProjection || it.variance != org.jetbrains.kotlin.types.Variance.INVARIANT
            }) diagnostics.unsupported(call, "Default dispatch requires invariant receiver and heritage arguments")
        return type
    }
    checked(receiver, receiverClass)
    if (receiverClass == owner) return receiver
    val substitution = IrTypeSubstitutor(receiverClass.typeParameters.map { it.symbol }, receiver.arguments)
    val inherited = getAllSubstitutedSupertypes(receiverClass).filter { it.classifier == owner.symbol }
        .map { substitution.substitute(it) as IrSimpleType }.distinct().singleOrNull()
        ?: diagnostics.unsupported(call, "Default dispatch has no unique heritage path to ${owner.name}")
    return checked(inherited, owner)
}
