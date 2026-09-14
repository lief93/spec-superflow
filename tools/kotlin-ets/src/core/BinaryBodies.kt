@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class,
    org.jetbrains.kotlin.ir.util.DelicateSymbolTableApi::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.serialization.signature.PublicIdSignatureComputer
import org.jetbrains.kotlin.backend.common.serialization.*
import org.jetbrains.kotlin.backend.jvm.*
import org.jetbrains.kotlin.backend.jvm.serialization.proto.JvmIr
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.fir.resolve.providers.symbolProvider
import org.jetbrains.kotlin.ir.*
import org.jetbrains.kotlin.ir.backend.jvm.serialization.JvmIrMangler
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.declarations.impl.IrFileImpl
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.*
import org.jetbrains.kotlin.ir.symbols.impl.IrFileSymbolImpl
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.load.kotlin.*
import org.jetbrains.kotlin.load.kotlin.header.KotlinClassHeader
import org.jetbrains.kotlin.name.FqName
import org.jetbrains.kotlin.name.Name
import org.jetbrains.org.objectweb.asm.*

/** A binary SourceFile attribute is not a local source path or a line-offset table. */
private class BinaryFileEntry(override val name: String) : AbstractIrFileEntry() {
    override val maxOffset = UNDEFINED_OFFSET
    override val supportsDebugInfo = false
    override val lineStartOffsets = intArrayOf()
}

/** Load only actual serialized bodies; a resolved bytecode signature is never a body. */
internal class BinaryBodies(private val input: JvmFir2IrPipelineArtifact) : FunctionBodies {
    private val context by lazy { createJvmLoweringContext(input) }
    private val signatures = PublicIdSignatureComputer(JvmIrMangler)
    private val available = mutableMapOf<IrFunctionSymbol, FunctionBody.Available>()
    private val callSites = linkedMapOf<IrFunctionSymbol, SourceSpan>()
    private val declarations = linkedMapOf<IdSignature, IrSimpleFunction>()
    private val originalTypes = mutableMapOf<IrFunctionSymbol, List<IrType>>()
    private val originalTypeParameters = mutableMapOf<IrFunctionSymbol, List<Pair<IrTypeParameter, List<IrType>>>>()
    private val canonical = linkedSetOf<IrSimpleFunctionSymbol>()
    private val loaded = mutableSetOf<String>()
    private val provenance = mutableMapOf<IrFunctionSymbol, BinaryFileEntry>()
    private val visiting = linkedSetOf<IrFunctionSymbol>()

    private fun types(owner: IrFunction) =
        (listOfNotNull(owner.extensionReceiverParameter) + owner.valueParameters).map { it.type } + owner.returnType

    private fun register(owner: IrSimpleFunction, signature: IdSignature, fail: (String) -> Nothing) {
        declarations[signature]?.let {
            if (it !== owner) fail("function signature conflicts with an existing declaration: $signature")
            return
        }
        val registered = context.symbolTable.declareSimpleFunction(signature, { owner.symbol }) { owner }
        if (registered !== owner) fail("function signature conflicts with an existing declaration: $signature")
        declarations[signature] = owner
        originalTypes[owner.symbol] = types(owner)
        originalTypeParameters[owner.symbol] = owner.typeParameters.map { it to it.superTypes.toList() }
        // The official decoder references public parameters by parent signature and index.
        // Seed the real FIR symbols so deserialization cannot replace call-site classifier identity.
        owner.typeParameters.forEach { parameter ->
            context.symbolTable.declareGlobalTypeParameter(signatures.computeSignature(parameter), { parameter.symbol }) { symbol ->
                if (symbol !== parameter.symbol) fail("type parameter signature conflicts with an existing declaration")
                parameter
            }
        }
        val classes = linkedSetOf(context.irBuiltIns.nothingClass.owner)
        fun collect(type: IrType) {
            val simple = type as? IrSimpleType ?: fail("unsupported signature type $type")
            (simple.classifier.owner as? IrClass)?.let(classes::add)
            simple.arguments.filterIsInstance<IrTypeProjection>().forEach { collect(it.type) }
        }
        types(owner).forEach(::collect)
        owner.typeParameters.flatMap { it.superTypes }.forEach(::collect)
        for (declaration in classes) {
            val bound = context.symbolTable.declareClass(signatures.computeSignature(declaration), { declaration.symbol }) { declaration }
            if (bound !== declaration) fail("classifier signature conflicts with an existing declaration")
            declaration.declarations.filterIsInstance<IrSimpleFunction>().forEach { member ->
                val result = context.symbolTable.declareSimpleFunction(signatures.computeSignature(member), { member.symbol }) { member }
                if (result !== member) fail("member signature conflicts with an existing declaration")
                canonical.add(member.symbol)
            }
        }
    }

    private fun index(binary: KotlinJvmBinaryClass, fail: (String) -> Nothing) {
        val proto = JvmIr.ClassOrFile.parseFrom(binary.classHeader.serializedIr!!)
        val library = object : IrLibraryFile() {
            override fun declaration(index: Int) = proto.declarationList[index]
            override fun type(index: Int) = proto.typeList[index]
            override fun signature(index: Int) = proto.signatureList[index]
            override fun string(index: Int) = proto.stringList[index]
            override fun expressionBody(index: Int) = proto.bodyList[index].expression
            override fun statementBody(index: Int) = proto.bodyList[index].statement
            override fun debugInfo(index: Int) = proto.debugInfoList[index]
        }
        val decoder = IdSignatureDeserializer(library,
            IdSignature.FileSignature(proto.fileFacadeFqName, binary.classId.packageFqName, binary.location), IrInterningService())
        for (index in proto.signatureList.indices) {
            val signature = decoder.deserializeIdSignature(index) as? IdSignature.CommonSignature ?: continue
            if (signature.id == null || !Name.isValidIdentifier(signature.declarationFqName) || '.' in signature.declarationFqName) continue
            if (signature in declarations) continue
            // Names only enumerate official FIR candidates; the entire serialized signature selects identity.
            val candidates = input.result.components.session.symbolProvider.getTopLevelFunctionSymbols(
                FqName(signature.packageFqName), Name.identifier(signature.declarationFqName))
                .map { input.result.components.declarationStorage.getIrFunctionSymbol(it).owner }
                .filterIsInstance<IrSimpleFunction>()
                .filter { signatures.computeSignature(it) == signature }
            if (candidates.size > 1) fail("ambiguous serialized function signature: $signature")
            candidates.singleOrNull()?.let { register(it, signature, fail) }
        }
    }

    init {
        input.result.irModuleFragment.files.forEach { file ->
            file.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrCall && element.symbol.owner.isInline) {
                        callSites.putIfAbsent(element.symbol,
                            SourceSpan(file.fileEntry.name, element.startOffset, element.endOffset))
                    }
                    element.acceptChildrenVoid(this)
                }
            })
        }
    }

    override fun resolve(symbol: IrFunctionSymbol): FunctionBody {
        available[symbol]?.let { return it }
        if (!symbol.isBound) return FunctionBody.Unavailable(FunctionBody.Reason.UNBOUND_SYMBOL)
        val function = symbol.owner
        if (!function.isInline) return FunctionBody.Unavailable(FunctionBody.Reason.OUTSIDE_MODULE)
        val binary = when (val source = function.containerSource) {
            is JvmPackagePartSource -> source.knownJvmBinaryClass
            is KotlinJvmBinarySourceElement -> source.binaryClass
            else -> null
        } ?: return FunctionBody.Unavailable(FunctionBody.Reason.OUTSIDE_MODULE)
        if (binary.classHeader.serializedIr == null) return FunctionBody.Unavailable(FunctionBody.Reason.NO_BODY)
        fun fail(message: String): Nothing = throw Unsupported(Diagnostic("UNSUPPORTED",
            "Binary inline body ${symbolName(function)}: $message", callSites[symbol]
                ?: SourceSpan(binary.location, UNDEFINED_OFFSET, UNDEFINED_OFFSET)))
        try {
            visit(function, ::fail)
            return available.getValue(symbol)
        } catch (failure: Unsupported) {
            throw failure
        } catch (failure: Exception) {
            fail("official serialized IR loading failed (${failure.javaClass.simpleName}): ${failure.message}")
        }
    }

    private fun visit(function: IrFunction, fail: (String) -> Nothing) {
        if (function.symbol in available) return
        if (!visiting.add(function.symbol)) {
            fail("serialized inline dependency cycle: ${(visiting.toList() + function.symbol).joinToString(" -> ") { it.owner.name.asString() }}")
        }
        try {
            if (!function.isInline || function.dispatchReceiverParameter != null) {
                fail("unsupported binary inline dependency: ${symbolName(function)}; require top-level inline (members are unsupported)")
            }
            if (function.typeParameters.any { it.isReified }) {
                fail("unsupported reified binary inline dependency: ${symbolName(function)}")
            }
            val source = function.containerSource as? JvmPackagePartSource
                ?: fail("unsupported dependency format for ${symbolName(function)}")
            val binary = source.knownJvmBinaryClass ?: fail("missing binary ownership for ${symbolName(function)}")
            if (binary.classHeader.serializedIr == null) {
                fail("missing serialized IR body for dependency ${symbolName(function)} at ${binary.location}")
            }
            load(function, source, binary, fail)
            if (types(function) != originalTypes[function.symbol]) fail("deserialization changed resolved signature type identity")
            val parameters = originalTypeParameters.getValue(function.symbol)
            if (function.typeParameters.size != parameters.size || parameters.withIndex().any { (index, original) ->
                    function.typeParameters[index] !== original.first || original.first.superTypes != original.second
                }) fail("deserialization changed resolved type parameter identity or bounds")
            val body = function.body ?: fail("serialized IR does not contain dependency body ${symbolName(function)}")
            val dependencies = linkedSetOf<IrFunction>()
            fun checkType(type: IrType) {
                val simple = type as? IrSimpleType ?: return
                if (!simple.classifier.isBound) fail("unlinked serialized type: ${simple.classifier.signature}")
                simple.arguments.filterIsInstance<IrTypeProjection>().forEach { checkType(it.type) }
            }
            val visitor = object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrDeclarationReference && !element.symbol.isBound) fail("unlinked serialized dependencies: ${element.symbol.signature}")
                    if (element is IrExpression) checkType(element.type)
                    if (element is IrValueDeclaration) checkType(element.type)
                    if (element is IrCall && element.symbol !in canonical) {
                        if (!element.symbol.owner.isInline) fail("unsupported serialized body call: ${symbolName(element.symbol.owner)}")
                        dependencies.add(element.symbol.owner)
                    }
                    if (element is IrConstructorCall) fail("binary inline constructors are not supported")
                    element.acceptChildrenVoid(this)
                }
            }
            body.acceptVoid(visitor)
            function.valueParameters.forEach { it.defaultValue?.acceptVoid(visitor) }
            dependencies.forEach { visit(it, fail) }
            val entry = provenance.getValue(function.symbol)
            available[function.symbol] = FunctionBody.Available(function, body,
                SourceSpan(entry.name, body.startOffset, body.endOffset))
        } finally {
            visiting.remove(function.symbol)
        }
    }

    private fun load(function: IrFunction, source: JvmPackagePartSource, binary: KotlinJvmBinaryClass, fail: (String) -> Nothing) {
        if (binary.location in loaded) return
        if (binary.classHeader.kind != KotlinClassHeader.Kind.FILE_FACADE) {
            fail("unsupported serialized dependency format ${binary.classHeader.kind}; expected a JVM file facade")
        }
        val virtual = binary as? VirtualFileKotlinClass
            ?: fail("unsupported binary provider ${binary.javaClass.name}; class bytes unavailable")
        var sourceName: String? = null
        val reader = ClassReader(virtual.file.contentsToByteArray())
        reader.accept(object : ClassVisitor(Opcodes.ASM9) {
            override fun visitSource(source: String?, debug: String?) { sourceName = source }
        }, ClassReader.SKIP_CODE or ClassReader.SKIP_FRAMES)
        val name = sourceName?.takeIf { it.isNotBlank() }
            ?: fail("class has no SourceFile attribute; source identity unavailable at ${binary.location}")
        val entry = BinaryFileEntry("${binary.location}#SourceFile=$name")
        register(function as IrSimpleFunction, signatures.computeSignature(function), fail)
        index(binary, fail)
        val owners = declarations.values.filter {
            it.isInline && (it.containerSource as? JvmPackagePartSource)?.knownJvmBinaryClass == binary
        }
        val facade = createJvmFileFacadeClass(IrDeclarationOrigin.FILE_CLASS,
            source.className.fqNameForTopLevelClassMaybeWithDollars.shortName(), source) { false }.apply {
            parent = function.parent
            createThisReceiverParameter()
            classNameOverride = source.className
        }
        owners.forEach { it.parent = facade }
        if (!JvmIrDeserializerImpl().deserializeTopLevelClass(facade, context.irBuiltIns,
                context.symbolTable, context.irProviders, context.generatorExtensions)) {
            fail("official deserializer did not load serialized IR")
        }
        // This represents the classfile's actual SourceFile record, not invented source contents.
        val file = IrFileImpl(entry, IrFileSymbolImpl(), binary.classId.packageFqName)
        facade.parent = file
        file.declarations.add(facade)
        owners.forEach { provenance[it.symbol] = entry }
        loaded.add(binary.location)
    }
}
