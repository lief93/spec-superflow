@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.CommonBackendContext
import org.jetbrains.kotlin.backend.common.IrElementTransformerVoidWithContext
import org.jetbrains.kotlin.backend.common.ir.Ir
import org.jetbrains.kotlin.backend.common.ir.moveBodyTo
import org.jetbrains.kotlin.backend.common.lower.*
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.builders.*
import org.jetbrains.kotlin.ir.builders.declarations.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.*
import org.jetbrains.kotlin.ir.inline.FunctionInlining
import org.jetbrains.kotlin.ir.inline.InlineFunctionResolver
import org.jetbrains.kotlin.ir.inline.InlineMode
import org.jetbrains.kotlin.ir.irAttribute
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.Name

private val ETS_CONSTRUCTOR_DISPATCH by IrDeclarationOriginImpl
private var IrConstructor.dispatchOwner: IrClass? by irAttribute(followAttributeOwner = false)
internal fun isEtsDispatchConstructor(constructor: IrConstructor): Boolean =
    constructor.dispatchOwner?.let { it === constructor.parent } == true

/** Normalize constructor families that cannot allocate through one source root. */
internal fun lowerNativeConstructorDispatch(input: JvmFir2IrPipelineArtifact) {
    val module = input.result.irModuleFragment
    val classes = mutableListOf<IrClass>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitClass(declaration: IrClass) { classes.add(declaration); super.visitClass(declaration) }
    })
    fun root(owner: IrClass): IrConstructor? = nativeConstructorRoot(owner)
    val selected = classes.filter { owner -> owner.constructors.any() &&
        (root(owner) == null || owner.modality in setOf(Modality.ABSTRACT, Modality.SEALED) && owner.constructors.count() > 1)
    }.toMutableSet()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitConstructor(declaration: IrConstructor) {
            declaration.body?.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
                override fun visitDelegatingConstructorCall(expression: IrDelegatingConstructorCall) {
                    val owner = expression.symbol.owner.parentAsClass
                    if (owner in classes && owner !== declaration.parent && expression.symbol.owner !== root(owner)) selected.add(owner)
                    super.visitDelegatingConstructorCall(expression)
                }
            })
            super.visitConstructor(declaration)
        }
    })
    if (selected.isEmpty()) return
    selected.forEach { owner ->
        val diagnostics = DiagnosticSink(owner.file.fileEntry.name)
        if (generateSequence(owner as IrDeclaration) { it.parent as? IrDeclaration }.any { it is IrFunction || it is IrClass && it.isInner } ||
            owner.declarations.filterIsInstance<IrField>().any { it.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE })
            diagnostics.unsupported(owner, "Constructor dispatch in local or inner classes requires capture-aware allocation")
        val inherited = owner.modality != Modality.FINAL || owner.superTypes.any {
            it.classOrNull?.owner?.fqNameWhenAvailable?.asString() != "kotlin.Any"
        }
        if (inherited) owner.constructors.forEach { constructor ->
            constructor.body?.let { rejectInheritedInitializerThis(it, owner, diagnostics, allowFieldWrites = true) }
        }
        owner.declarations.mapNotNull { declaration -> when (declaration) {
            is IrProperty -> declaration.backingField?.initializer
            is IrField -> declaration.initializer
            is IrAnonymousInitializer -> declaration.body
            else -> null
        } }.forEach { initializer ->
            if (inherited) rejectInheritedInitializerThis(initializer, owner, diagnostics)
            initializer.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
                override fun visitClass(declaration: IrClass) {
                    diagnostics.unsupported(declaration, "Local classes in constructor initializers require local-class popup before initializer duplication")
                }
            })
        }
    }
    val real = createJvmLoweringContext(input)
    val generators = IrGeneratorContextBase(real.irBuiltIns)
    val context = object : CommonBackendContext by real {
        override val ir = object : Ir() { override val symbols = real.ir.symbols }
    }
    val providers = selected.flatMap { it.constructors.toList() }.toSet()
    val defaults = MaskedDefaultArgumentFunctionFactory(context)
    val defaultGenerator = object : DefaultArgumentStubGenerator<CommonBackendContext>(context, defaults) {
        override fun defaultArgumentStubVisibility(function: IrFunction) = function.visibility
        override fun useConstructorMarker(function: IrFunction) = false
        override fun getOriginForCallToImplementation() = IrStatementOrigin.DEFAULT_DISPATCH_CALL
        override fun IrBlockBodyBuilder.selectArgumentOrDefault(flag: IrExpression, parameter: IrValueParameter, default: IrExpression): IrValueDeclaration =
            irTemporary(irIfThenElse(parameter.type, irNotEquals(flag, irInt(0)), default, irGet(parameter)))
        override fun transformFlat(declaration: IrDeclaration): List<IrDeclaration>? =
            if (declaration in providers) super.transformFlat(declaration) else null
    }
    module.files.forEach(defaultGenerator::lower)
    val injector = object : DefaultParameterInjector<CommonBackendContext>(context, defaults) {
        override fun defaultArgumentStubVisibility(function: IrFunction) = function.visibility
        override fun useConstructorMarker(function: IrFunction) = false
        override fun shouldReplaceWithSyntheticFunction(functionAccess: IrFunctionAccessExpression): Boolean =
            functionAccess.symbol.owner in providers && super.shouldReplaceWithSyntheticFunction(functionAccess)
    }
    module.files.forEach(injector::lower)
    val originals = selected.flatMap { it.constructors.toList() }.sortedWith(compareBy({ it.file.fileEntry.name }, { it.startOffset }))
    originals.forEach { it.valueParameters.forEach { parameter -> parameter.defaultValue = null } }
    // Move source initializers before inlining so the common inliner binds their parameters too.
    val initialization = InitializersLowering(context)
    originals.forEach { constructor -> constructor.body?.let { initialization.lower(it, constructor) } }
    val cleanup = object : InitializersCleanupLowering(context, { !it.isStatic }) {
        override fun transformFlat(declaration: IrDeclaration): List<IrDeclaration>? =
            if (declaration.parent in selected &&
                (declaration is IrField || declaration is IrAnonymousInitializer && !declaration.isStatic))
                super.transformFlat(declaration) else null
    }
    module.files.forEach(cleanup::lower)
    val reserved = mutableSetOf<String>()
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrDeclarationWithName && !element.name.isSpecial) reserved.add(element.name.asString())
            element.acceptChildrenVoid(this)
        }
    })
    val names = NameTable<IrConstructor>(reserved = reserved)
    val initializers = originals.associateWith { constructor ->
        val owner = constructor.parentAsClass
        real.irFactory.buildFun {
            startOffset = constructor.startOffset
            endOffset = constructor.endOffset
            name = Name.identifier("initialize")
            returnType = real.irBuiltIns.unitType
            visibility = DescriptorVisibilities.PRIVATE
            origin = ETS_CONSTRUCTOR_DISPATCH
        }.apply {
            parent = owner
            dispatchReceiverParameter = owner.thisReceiver!!.copyTo(this, type = owner.defaultType)
            constructor.valueParameters.forEach { valueParameters += it.copyTo(this, type = it.type) }
            body = constructor.moveBodyTo(this, constructor.valueParameters.zip(valueParameters).toMap() +
                (owner.thisReceiver!! to dispatchReceiverParameter!!))
        }
    }
    val dispatchers = selected.associateWith { owner -> owner.addConstructor {
        startOffset = owner.startOffset
        endOffset = owner.endOffset
        origin = ETS_CONSTRUCTOR_DISPATCH
        isPrimary = false
        visibility = if (owner.modality == Modality.FINAL || originals.filter { it.parent === owner }.all {
            it.visibility == DescriptorVisibilities.PRIVATE
        }) DescriptorVisibilities.PRIVATE else DescriptorVisibilities.PROTECTED
        returnType = owner.defaultType
    }.apply {
        dispatchOwner = owner
        addValueParameter("__constructor", real.irBuiltIns.intType)
        originals.filter { it.parent === owner }.forEachIndexed { index, original ->
            original.valueParameters.forEach { addValueParameter("__${index}_${it.name}", it.type.makeNullable()) }
        }
    } }
    fun dispatchArguments(call: IrFunctionAccessExpression, target: IrConstructor, builder: DeclarationIrBuilder): List<IrExpression> {
        val family = originals.filter { it.parent === target.parent }
        val chosen = call.symbol.owner
        return listOf(builder.irInt(family.indexOf(chosen))) + family.flatMap { constructor ->
            constructor.valueParameters.mapIndexed { index, parameter ->
                if (constructor === chosen) call.getValueArgument(index)
                    ?: DiagnosticSink(chosen.file.fileEntry.name).unsupported(call, "Constructor default injection left an unbound argument")
                else builder.irNull(parameter.type.makeNullable())
            }
        }
    }
    initializers.forEach { (constructor, initializer) ->
        val builder = DeclarationIrBuilder(generators, initializer.symbol, constructor.startOffset, constructor.endOffset)
        initializer.body!!.transformChildrenVoid(object : IrElementTransformerVoid() {
            override fun visitDelegatingConstructorCall(expression: IrDelegatingConstructorCall): IrExpression {
                expression.transformChildrenVoid(this)
                val called = expression.symbol.owner
                if (called.parent === constructor.parent) return builder.irCall(initializers.getValue(called)).apply {
                    dispatchReceiver = builder.irGet(initializer.dispatchReceiverParameter!!)
                    called.valueParameters.indices.forEach { putValueArgument(it, expression.getValueArgument(it)) }
                }
                return expression
            }
        })
    }
    dispatchers.forEach { (owner, dispatcher) ->
        val builder = DeclarationIrBuilder(generators, dispatcher.symbol, owner.startOffset, owner.endOffset)
        var parameter = 1
        dispatcher.body = builder.irBlockBody {
            +builder.irWhen(real.irBuiltIns.unitType, originals.filter { it.parent === owner }.mapIndexed { index, original ->
                val call = builder.irCall(initializers.getValue(original)).apply {
                    dispatchReceiver = builder.irGet(owner.thisReceiver!!)
                    original.valueParameters.forEachIndexed { argument, value ->
                        putValueArgument(argument, builder.irImplicitCast(builder.irGet(dispatcher.valueParameters[parameter++]), value.type))
                    }
                }
                builder.irBranch(builder.irEquals(builder.irGet(dispatcher.valueParameters.first()), builder.irInt(index)), call)
            } + builder.irElseBranch(builder.irCall(real.irBuiltIns.illegalArgumentExceptionSymbol).apply {
                putValueArgument(0, builder.irString("Invalid constructor entry"))
            }))
        }
    }
    val factories = originals.filter { it.parentAsClass.modality !in setOf(Modality.ABSTRACT, Modality.SEALED) }.associateWith { original ->
        val owner = original.parentAsClass
        real.irFactory.createStaticFunctionWithReceivers(owner,
            Name.identifier(names.declareFreshName(original, "new_${owner.name}")), original,
            origin = ETS_CONSTRUCTOR_DISPATCH, typeParametersFromContext = owner.typeParameters,
            remapMultiFieldValueClassStructure = { _, _, _ -> }).apply {
            val builder = DeclarationIrBuilder(generators, symbol, original.startOffset, original.endOffset)
            val call = builder.irCallConstructor(original.symbol, typeParameters.map { it.defaultType }).apply {
                valueParameters.forEachIndexed { index, value -> putValueArgument(index, builder.irGet(value)) }
            }
            val allocation = builder.irCallConstructor(dispatchers.getValue(owner).symbol, typeParameters.map { it.defaultType }).apply {
                dispatchArguments(call, dispatchers.getValue(owner), builder).forEachIndexed { index, value -> putValueArgument(index, value) }
            }
            body = builder.irBlockBody { +builder.irReturn(allocation) }
            val types = (owner.typeParameters + original.typeParameters).zip(typeParameters).toMap()
            remapTypes(object : TypeRemapper {
                override fun enterScope(irTypeParametersContainer: IrTypeParametersContainer) = Unit
                override fun leaveScope() = Unit
                override fun remapType(type: IrType): IrType = type.remapTypeParameters(original, this@apply, types)
            })
        }
    }
    selected.forEach { owner ->
        owner.declarations.removeAll { it in originals }
        owner.declarations.addAll(initializers.filterKeys { it.parent === owner }.values)
        owner.declarations.addAll(factories.filterKeys { it.parent === owner }.values)
    }
    module.files.forEach { file -> file.transformChildrenVoid(object : IrElementTransformerVoidWithContext() {
        override fun visitConstructorCall(expression: IrConstructorCall): IrExpression {
            expression.transformChildrenVoid(this)
            val factory = factories[expression.symbol.owner] ?: return expression
            return IrCallImpl(expression.startOffset, expression.endOffset, expression.type, factory.symbol, expression.typeArguments.size).apply {
                copyValueArgumentsFrom(expression, factory)
                expression.typeArguments.forEachIndexed { index, type -> typeArguments[index] = type }
            }
        }
        override fun visitDelegatingConstructorCall(expression: IrDelegatingConstructorCall): IrExpression {
            expression.transformChildrenVoid(this)
            val target = dispatchers[expression.symbol.owner.parentAsClass] ?: return expression
            if (expression.symbol.owner === target) return expression
            val builder = DeclarationIrBuilder(generators, currentScope!!.scope.scopeOwnerSymbol, expression.startOffset, expression.endOffset)
            return builder.irDelegatingConstructorCall(target).apply {
                expression.typeArguments.forEachIndexed { index, type -> typeArguments[index] = type }
                dispatchArguments(expression, target, builder).forEachIndexed { index, value -> putValueArgument(index, value) }
            }
        }
    }) }
    val resolver = object : InlineFunctionResolver(InlineMode.ALL_FUNCTIONS) {
        override fun needsInlining(function: IrFunction) = function in initializers.values
    }
    FunctionInlining(real, resolver, produceOuterThisFields = false).inline(module)
    selected.forEach { it.declarations.removeAll { declaration -> declaration in initializers.values } }
    module.transformChildrenVoid(ReturnableBlockTransformer(real))
    module.patchDeclarationParents()
}
