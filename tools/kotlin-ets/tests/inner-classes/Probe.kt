@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.jvm.JvmLoweredDeclarationOrigin
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.IrGetValueImpl
import org.jetbrains.kotlin.ir.expressions.impl.IrGetFieldImpl
import org.jetbrains.kotlin.ir.expressions.impl.IrSetFieldImpl
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

private fun span(declaration: IrDeclaration) =
    SourceSpan(sourceFile(declaration)!!.fileEntry.name, declaration.startOffset, declaration.endOffset)

private fun generatedSpan(binding: SourceInnerClassBinding, element: IrElement) =
    if (element.startOffset >= 0 && element.endOffset >= element.startOffset)
        SourceSpan(binding.source.file, element.startOffset, element.endOffset) else binding.source

fun main(args: Array<String>) {
    val output = File(args[1])
    val baseline = args[2] == "baseline"
    var negatives = 0
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(3)) { module ->
        File(output, "lowered.ir").writeText(module.dump())
        val classes = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        val owners = classes.filter { sourceInnerClassBinding(it) != null }
        check(owners.size == 3)
        val bindings = owners.associateWith { checkNotNull(sourceInnerClassBinding(it)) }
        fun lower() = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        if (baseline) {
            val failure = runCatching { lower() }.exceptionOrNull()
            check(failure is Unsupported && failure.diagnostic.message.contains("Unsupported nested source class declaration")) { "$failure" }
            check(bindings.values.any { failure.diagnostic.source == span(it.field) })
            File(output, "rejection.txt").writeText(failure.diagnostic.toString())
            return@withKotlinModule null
        }
        val originalNames = classes.associateWith { it.name }
        val originalParameters = bindings.values.associate { it.constructor to it.constructor.valueParameters.map { p -> p.symbol to p.name } }
        val backend = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules()))
        val program = backend.lower(module)
        val targets = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.symbol.id }
        val nodes = mutableListOf<EtsNode>()
        program.files.forEach { file -> file.declarations.forEach { walkEts(it, nodes::add) } }
        val records = mutableListOf<String>()
        for ((owner, binding) in bindings) {
            check(owner.name == originalNames.getValue(owner))
            check(binding.constructor.valueParameters.map { it.symbol to it.name } == originalParameters.getValue(binding.constructor))
            val target = targets.getValue(etsClassSymbol(owner.name.asString(), span(owner)).id)
            check(target.source == binding.source && (target.sourceName ?: target.name) == owner.name.asString())
            check(target.exported == sourceClassIsExported(owner))
            check(program.files.single { target in it.declarations }.sourcePath == binding.source.file)
            val constructor = target.members.filterIsInstance<EtsFunction>().single { it.kind == EtsFunctionKind.CONSTRUCTOR }
            val first = constructor.body.first() as EtsExpressionStatement
            val assignment = first.expression as EtsAssignment
            val member = assignment.target as EtsMember
            val field = target.members.filterIsInstance<EtsField>().single { it.symbol.id == member.symbolId }
            val outer = targets.getValue(etsClassSymbol(binding.outer.name.asString(), span(binding.outer)).id)
            check(field.private && !field.static && field.initializer == null && field.symbol.type == outer.symbol.type)
            check(field.source == generatedSpan(binding, binding.field))
            check(constructor.parameters.first().symbol.type == outer.symbol.type)
            check(constructor.parameters.first().symbol.source == generatedSpan(binding, binding.parameter))
            check((assignment.value as EtsReference).symbol == constructor.parameters.first().symbol)
            check((member.receiver as EtsReference).symbol.name == "this")
            val write = (binding.constructor.body as IrBlockBody).statements.first()
            check(first.source == generatedSpan(binding, write) && member.source == first.source && assignment.source == first.source)
            val reads = nodes.filterIsInstance<EtsMember>().filter { it.symbolId == field.symbol.id }
            check(reads.size > 1 && reads.all { it.name == field.symbol.name && it.type == field.symbol.type })
            check(reads.all { it.source.start >= 0 && it.source.end >= it.source.start })
            val scope = Scope()
            scope.bindings[owner.thisReceiver!!.symbol] = EtsReference(
                EtsSymbol("probe:this", "this", target.symbol.type, binding.source, external = true))
            val absentRead = IrGetFieldImpl(-1, -1, binding.field.symbol, binding.field.type,
                IrGetValueImpl(-1, -1, owner.thisReceiver!!.symbol))
            val loweredRead = backend.language.expression(absentRead, scope) as EtsMember
            check(loweredRead.source == binding.source && loweredRead.symbolId == field.symbol.id)
            check(backend.language.source(IrGetValueImpl(-1, -1, binding.parameter.symbol)) == binding.source)
            check(constructor.parameters.drop(1).map { it.symbol.name } == binding.constructor.valueParameters.drop(1).map { it.name.asString() })
            val rootNames = program.files.flatMap { it.declarations }.map { when (it) {
                is EtsClass -> it.name
                is EtsFunction -> it.name
            } }
            check(constructor.parameters.first().symbol.name !in rootNames)
            val sourceFields = owner.declarations.filterIsInstance<IrProperty>().filterNot { it.isFakeOverride }.map { it.name.asString() }
            check(field.symbol.name !in sourceFields)
            check(sourceFields.all { name -> target.members.filterIsInstance<EtsField>().any { it.symbol.name == name } })
            records += "${owner.name}\t${target.name}\t${outer.symbol.id}\t${field.symbol}\t${constructor.parameters.first().symbol}"
        }
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrConstructorCall && element.symbol.owner.parent in owners) {
                    val owner = element.symbol.owner.parent as IrClass
                    val binding = bindings.getValue(owner)
                    check(element.symbol === binding.constructor.symbol && element.dispatchReceiver == null)
                    val creation = nodes.filterIsInstance<EtsNew>().single { it.source.start == element.startOffset &&
                        it.source.end == element.endOffset && it.classType.symbolId == etsClassSymbol(owner.name.asString(), span(owner)).id }
                    check(creation.arguments.size == element.valueArgumentsCount)
                    check(creation.arguments.first().type == backend.language.type(binding.field.type))
                    check(creation.classType == backend.language.type(element.type))
                }
                element.acceptChildrenVoid(this)
            }
        })
        File(output, "bindings.tsv").writeText(records.joinToString("\n"))

        val owner = owners.single { bindings.getValue(it).outer.name.asString() == "Outer" }
        val binding = bindings.getValue(owner)
        val field = binding.field
        val constructor = binding.constructor
        val parameter = binding.parameter
        val body = constructor.body as IrBlockBody
        val statements = body.statements.toList()
        val write = statements.first() as IrSetField
        fun reject(label: String, expected: String, at: SourceSpan, change: () -> Unit, restore: () -> Unit) {
            val failure = try { change(); runCatching { lower() }.exceptionOrNull() } finally { restore() }
            check(failure is Unsupported && failure.diagnostic.message.contains(expected)) { "$label: $failure" }
            check(failure.diagnostic.source == at) { "$label: ${failure.diagnostic.source}, expected $at" }
            records += "$label\t${failure.diagnostic}"
            negatives++
        }
        fun restoreBody() { body.statements.clear(); body.statements.addAll(statements) }
        val prefixError = "one registered outer initialization"
        reject("Missing prefix", prefixError, span(constructor), { body.statements.removeAt(0) }, ::restoreBody)
        reject("Duplicate prefix", prefixError, span(constructor), { body.statements.add(0, write) }, ::restoreBody)
        reject("Late prefix", prefixError, span(constructor),
            { body.statements.removeAt(0); body.statements.add(1, write) }, ::restoreBody)
        val sourceField = owner.declarations.filterIsInstance<IrProperty>().first().backingField!!
        reject("Wrong field", prefixError, span(constructor),
            { body.statements[0] = IrSetFieldImpl(write.startOffset, write.endOffset, sourceField.symbol,
                write.receiver, write.value, write.type) }, ::restoreBody)
        val value = write.value
        reject("Wrong parameter", prefixError, span(constructor),
            { write.value = IrGetValueImpl(-1, -1, constructor.valueParameters[1].symbol) }, { write.value = value })
        val receiver = write.receiver
        reject("Wrong receiver", prefixError, span(constructor), { write.receiver = value }, { write.receiver = receiver })
        val fieldOrigin = field.origin
        reject("Spoofed field origin", "Invalid registered inner", binding.source,
            { field.origin = IrDeclarationOriginImpl(fieldOrigin.name, true) }, { field.origin = fieldOrigin })
        val parameterOrigin = parameter.origin
        check(parameterOrigin === JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS)
        reject("Spoofed parameter origin", "Invalid registered inner", binding.source,
            { parameter.origin = IrDeclarationOriginImpl(parameterOrigin.name, true) }, { parameter.origin = parameterOrigin })
        val fieldType = field.type
        reject("Wrong outer field type", "Invalid registered inner", binding.source,
            { field.type = owner.defaultType }, { field.type = fieldType })
        val parameterType = parameter.type
        reject("Wrong outer parameter type", "Invalid registered inner", binding.source,
            { parameter.type = owner.defaultType }, { parameter.type = parameterType })
        reject("Static outer storage", "Invalid registered inner", binding.source,
            { field.isStatic = true }, { field.isStatic = false })
        reject("Mutable outer storage", "Invalid registered inner", binding.source,
            { field.isFinal = false }, { field.isFinal = true })
        val fieldParent = field.parent
        reject("Transferred field owner", "Invalid registered inner", binding.source,
            { field.parent = binding.outer }, { field.parent = fieldParent })
        val file = sourceFile(owner)!!
        val copy = owner.deepCopyWithSymbols(file)
        check(sourceInnerClassBinding(copy) == null)
        val index = file.declarations.indexOf(owner)
        reject("Unregistered class copy", "no registered source binding", binding.source,
            { file.declarations[index] = copy }, { file.declarations[index] = owner })
        File(output, "negatives.tsv").writeText(records.takeLast(negatives).joinToString("\n"))
        program
    }
    if (baseline) { println("PASS expected RED: official outer field rejected by frozen language"); return }
    checkNotNull(program)
    val modules = File(output, "modules").also { check(it.mkdir()) }
    emitEtsModules(program, StandardLibraryRuntime).forEach { (name, text) -> File(modules, name).writeText(text) }
    File(output, "Combined.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
    File(output, "negative-count.txt").writeText(negatives.toString())
    println("PASS three registered inner classes, outer identity/import types, source names/spans, $negatives malformed bindings")
}
