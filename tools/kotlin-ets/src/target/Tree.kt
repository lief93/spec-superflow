package dev.ets

data class SourceSpan(val file: String?, val start: Int, val end: Int)

sealed interface EtsType
data class EtsCapturedType(val readType: EtsType, val writeType: EtsType) : EtsType
data class EtsNamedType(val name: String, val arguments: List<EtsType> = emptyList(), val symbolId: String? = null,
    val external: Boolean = false) : EtsType
data class EtsRecordType(val name: String, val fields: Map<String, EtsType>) : EtsType
enum class EtsVariance { INVARIANT, IN, OUT }
data class EtsTypeParameter(val id: String, val name: String, val upperBound: EtsType? = null,
    val variance: EtsVariance = EtsVariance.INVARIANT)
data class EtsTypeParameterType(val id: String, val name: String) : EtsType
data class EtsFunctionType(val parameters: List<EtsType>, val result: EtsType,
    val typeParameters: List<EtsTypeParameter> = emptyList()) : EtsType
data class EtsNullableType(val inner: EtsType) : EtsType
data class EtsTupleType(val elements: List<EtsType>) : EtsType

object EtsTypes {
    val NUMBER = EtsNamedType("number")
    val STRING = EtsNamedType("string")
    val BOOLEAN = EtsNamedType("boolean")
    val VOID = EtsNamedType("void")
    val NEVER = EtsNamedType("never")
    val OBJECT = EtsNamedType("Object")
    val NULL = EtsNamedType("null")
    val UNDEFINED = EtsNamedType("undefined")
}

data class EtsSymbol(
    val id: String,
    val name: String,
    val type: EtsType,
    val source: SourceSpan,
    val external: Boolean = false,
)

sealed interface EtsNode { val source: SourceSpan }
sealed interface EtsExpression : EtsNode { val type: EtsType }
sealed interface EtsStatement : EtsNode
sealed interface EtsDeclaration : EtsNode
enum class EtsVisibility { PUBLIC, PROTECTED, PRIVATE }
sealed interface EtsClassMember : EtsNode { val visibility: EtsVisibility }

data class EtsLiteral(val value: Any?, override val type: EtsType, override val source: SourceSpan) : EtsExpression
data class EtsUndefined(override val source: SourceSpan) : EtsExpression { override val type = EtsTypes.UNDEFINED }
data class EtsReference(val symbol: EtsSymbol, override val source: SourceSpan = symbol.source) : EtsExpression {
    override val type get() = symbol.type
}
data class EtsMember(val receiver: EtsExpression, val name: String, override val type: EtsType,
    override val source: SourceSpan, val symbolId: String? = null) : EtsExpression
data class EtsCall(val callee: EtsExpression, val arguments: List<EtsExpression>, override val type: EtsType,
    override val source: SourceSpan, val typeArguments: List<EtsType> = emptyList()) : EtsExpression
data class EtsNew(val classType: EtsNamedType, val arguments: List<EtsExpression>, override val source: SourceSpan) : EtsExpression {
    override val type get() = classType
}
data class EtsBinary(val operator: String, val left: EtsExpression, val right: EtsExpression,
    override val type: EtsType, override val source: SourceSpan) : EtsExpression
data class EtsUnary(val operator: String, val operand: EtsExpression, override val type: EtsType,
    override val source: SourceSpan) : EtsExpression
data class EtsConditional(val condition: EtsExpression, val whenTrue: EtsExpression, val whenFalse: EtsExpression,
    override val type: EtsType, override val source: SourceSpan) : EtsExpression
data class EtsAssignment(val target: EtsExpression, val value: EtsExpression,
    override val source: SourceSpan) : EtsExpression { override val type get() = target.type }
data class EtsCast(val value: EtsExpression, override val type: EtsType, override val source: SourceSpan) : EtsExpression
data class EtsArray(val elements: List<EtsExpression>, val elementType: EtsType,
    override val source: SourceSpan) : EtsExpression { override val type = EtsNamedType("Array", listOf(elementType)) }
data class EtsObject(val fields: Map<String, EtsExpression>, override val type: EtsRecordType,
    override val source: SourceSpan) : EtsExpression
data class EtsParameter(val symbol: EtsSymbol, val defaultValue: EtsExpression? = null)
data class EtsLambda(val parameters: List<EtsParameter>, val body: List<EtsStatement>, val returnType: EtsType,
    override val source: SourceSpan) : EtsExpression {
    override val type = EtsFunctionType(parameters.map { it.symbol.type }, returnType)
}

data class EtsVariable(val symbol: EtsSymbol, val initializer: EtsExpression?, val mutable: Boolean,
    override val source: SourceSpan = symbol.source) : EtsStatement
data class EtsGlobal(val symbol: EtsSymbol, val initializer: EtsExpression, val mutable: Boolean,
    val exported: Boolean = false, override val source: SourceSpan = symbol.source) : EtsDeclaration
data class EtsExpressionStatement(val expression: EtsExpression,
    override val source: SourceSpan = expression.source) : EtsStatement
data class EtsReturn(val value: EtsExpression?, override val source: SourceSpan) : EtsStatement
data class EtsThrow(val value: EtsExpression, override val source: SourceSpan) : EtsStatement
data class EtsCatch(val parameter: EtsSymbol, val body: List<EtsStatement>)
data class EtsTry(val body: List<EtsStatement>, val handler: EtsCatch? = null,
    val finallyBody: List<EtsStatement>? = null, override val source: SourceSpan) : EtsStatement
data class EtsSuperConstructorCall(val baseClass: EtsNamedType, val arguments: List<EtsExpression>,
    override val source: SourceSpan) : EtsStatement
data class EtsBlock(val statements: List<EtsStatement>, override val source: SourceSpan) : EtsStatement
data class EtsBranch(val condition: EtsExpression?, val body: List<EtsStatement>)
data class EtsIf(val branches: List<EtsBranch>, override val source: SourceSpan) : EtsStatement
data class EtsLoop(val label: String, val condition: EtsExpression, val body: List<EtsStatement>, val doWhile: Boolean,
    override val source: SourceSpan) : EtsStatement
data class EtsJump(val label: String, val isContinue: Boolean, override val source: SourceSpan) : EtsStatement
data class EtsUiElement(val call: EtsCall, val children: List<EtsStatement>? = null,
    val attributes: List<EtsCall> = emptyList(), override val source: SourceSpan = call.source) : EtsStatement
data class EtsUiForEach(val items: EtsExpression, val item: EtsParameter, val body: List<EtsStatement>,
    override val source: SourceSpan) : EtsStatement
enum class EtsFunctionKind { FUNCTION, METHOD, CONSTRUCTOR, GETTER, SETTER }
data class EtsFunction(val name: String, val parameters: List<EtsParameter>, val returnType: EtsType,
    val body: List<EtsStatement>, override val source: SourceSpan,
    val kind: EtsFunctionKind = EtsFunctionKind.FUNCTION, val exported: Boolean = false,
    override val visibility: EtsVisibility = EtsVisibility.PUBLIC, val static: Boolean = false,
    val typeParameters: List<EtsTypeParameter> = emptyList(), val builder: Boolean = false,
    val build: Boolean = false, val abstract: Boolean = false,
    val overrides: List<String> = emptyList(), val sourceName: String? = null) : EtsDeclaration, EtsStatement, EtsClassMember {
    val symbol get() = etsFunctionSymbol(name, parameters.map { it.symbol.type }, returnType, source, typeParameters, sourceName ?: name, kind)
}
data class EtsField(val symbol: EtsSymbol, val initializer: EtsExpression? = null,
    override val visibility: EtsVisibility = EtsVisibility.PUBLIC, val static: Boolean = false,
    override val source: SourceSpan = symbol.source, val state: Boolean = false,
    val readonly: Boolean = false) : EtsClassMember
enum class EtsClassKind { CLASS, INTERFACE }
data class EtsClass(val name: String, val members: List<EtsClassMember>, override val source: SourceSpan,
    val exported: Boolean = false, val typeParameters: List<EtsTypeParameter> = emptyList(),
    val component: Boolean = false, val entry: Boolean = false,
    val kind: EtsClassKind = EtsClassKind.CLASS, val baseClass: EtsNamedType? = null,
    val interfaces: List<EtsNamedType> = emptyList(), val abstract: Boolean = false,
    val sourceName: String? = null, val constraint: Boolean = false) : EtsDeclaration {
    val symbol get() = etsClassSymbol(name, source, sourceName ?: name)
}
data class EtsImport(val module: String, val name: String, val alias: String? = null, val default: Boolean = false)
data class EtsFile(val sourcePath: String, val declarations: List<EtsDeclaration>)
data class EtsProgram(val files: List<EtsFile>, val imports: List<EtsImport> = emptyList(),
    val externalClasses: Map<String, EtsClass> = emptyMap())

/** Pinned runtime declarations selected by typed symbol references, never by printed source. */
fun interface EtsRuntimeSupport {
    fun declarations(program: EtsProgram): List<String>
}

fun etsDiscard(value: EtsExpression, source: SourceSpan = value.source): EtsExpression =
    EtsCall(EtsLambda(emptyList(), listOf(EtsExpressionStatement(value)), EtsTypes.VOID, source),
        emptyList(), EtsTypes.VOID, source)

fun etsFunctionSymbol(name: String, parameters: List<EtsType>, result: EtsType, source: SourceSpan,
    typeParameters: List<EtsTypeParameter> = emptyList(), sourceName: String = name,
    kind: EtsFunctionKind = EtsFunctionKind.FUNCTION): EtsSymbol {
    val accessor = if (kind in setOf(EtsFunctionKind.GETTER, EtsFunctionKind.SETTER)) ":${kind.name}" else ""
    return EtsSymbol("function:${source.file}:${source.start}:$sourceName$accessor", name,
        EtsFunctionType(parameters, result, typeParameters), source)
}

fun etsClassSymbol(name: String, source: SourceSpan, sourceName: String = name): EtsSymbol {
    val id = "class:${source.file}:${source.start}:$sourceName"
    return EtsSymbol(id, name, EtsNamedType(name, symbolId = id), source)
}
