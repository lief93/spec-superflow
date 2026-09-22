package dev.ets

/** Formatting only: no Kotlin IR, symbol resolution, state selection, or library rules. */
class EtsPrinter {
    fun type(value: EtsType): String = when (value) {
        is EtsCapturedType -> type(value.readType)
        is EtsNamedType -> value.name + if (value.arguments.isEmpty()) "" else
            value.arguments.joinToString(", ", "<", ">") { type(it) }
        is EtsRecordType -> value.name
        is EtsTypeParameterType -> value.name
        is EtsFunctionType -> value.parameters.mapIndexed { index, parameter -> "arg$index: ${type(parameter)}" }
            .joinToString(", ", "(${typeParameters(value.typeParameters)}(", ") => ${type(value.result)})")
        is EtsNullableType -> "${type(value.inner)} | null"
        is EtsTupleType -> value.elements.joinToString(", ", "[", "]") { type(it) }
    }

    fun expression(value: EtsExpression): String = expression(value, 0)

    private fun expression(value: EtsExpression, minimumPrecedence: Int): String {
        val text = expressionText(value)
        return if (precedence(value) < minimumPrecedence) "($text)" else text
    }

    private fun precedence(value: EtsExpression): Int = when (value) {
        is EtsLambda, is EtsAssignment -> 1
        is EtsConditional -> 2
        is EtsBinary -> when (value.operator) {
            "??" -> 3
            "||" -> 4
            "&&" -> 5
            "|" -> 6
            "^" -> 7
            "&" -> 8
            "===", "!==" -> 9
            "<", "<=", ">", ">=", "instanceof" -> 10
            "<<", ">>", ">>>" -> 11
            "+", "-" -> 12
            "*", "/", "%" -> 13
            else -> error("Unsupported target operator: ${value.operator}")
        }
        // A following | or < can be parsed as part of the asserted type.
        is EtsCast, is EtsArray -> 1
        is EtsUnary -> 14
        is EtsLiteral -> if (value.value is Number && value.value.toString().startsWith("-")) 14 else 17
        else -> 17
    }

    private fun binaryOperand(value: EtsExpression, parent: EtsBinary, right: Boolean): String {
        // ?? cannot directly mix with &&/||, even where precedence would suffice.
        val mixedNullish = value is EtsBinary &&
            ((parent.operator == "??" && value.operator in setOf("&&", "||")) ||
             (value.operator == "??" && parent.operator in setOf("&&", "||")))
        if (mixedNullish) return "(${expression(value)})"
        // Keep right-hand grouping: arithmetic is not generally associative.
        return expression(value, precedence(parent) + if (right) 1 else 0)
    }

    private fun expressionText(value: EtsExpression): String = when (value) {
        is EtsLiteral -> when (val literal = value.value) {
            null -> "null"
            is String -> quote(literal)
            is Char -> quote(literal.toString())
            is Long -> literal.toString() + if (value.type == EtsTypes.BIGINT) "n" else ""
            is Number, is Boolean -> literal.toString()
            else -> error("Unsupported target literal: ${literal.javaClass.simpleName}")
        }
        is EtsUndefined -> "undefined"
        is EtsReference -> value.symbol.name
        is EtsSuper -> "super"
        is EtsMember -> {
            val receiver = value.receiver
            (if (receiver is EtsLiteral && receiver.value is Number)
                "(${expression(receiver)})" else expression(receiver, 17)) + ".${value.name}"
        }
        // es2abc misparses annotated IIFEs after an `as` inside a conditional.
        // Their result remains typed in the target tree and inferred from the body.
        is EtsCall -> (if (value.callee is EtsLambda) "(${lambda(value.callee, false)})" else expression(value.callee, 17)) +
            (if (value.typeArguments.isEmpty()) "" else value.typeArguments.joinToString(", ", "<", ">") { type(it) }) +
            value.arguments.joinToString(", ", "(", ")") { expression(it) }
        is EtsNew -> "new ${type(value.classType)}" + value.arguments.joinToString(", ", "(", ")") { expression(it) }
        is EtsBinary -> "${binaryOperand(value.left, value, false)} ${value.operator} ${binaryOperand(value.right, value, true)}"
        is EtsUnary -> "${value.operator} ${expression(value.operand, 14)}"
        is EtsConditional -> "${expression(value.condition, 3)} ? ${expression(value.whenTrue)} : ${expression(value.whenFalse)}"
        is EtsAssignment -> "${expression(value.target, 2)} = ${expression(value.value)}"
        is EtsCast -> "${expression(value.value, 10)} as ${type(value.type)}"
        is EtsArray -> value.elements.joinToString(", ", "[", "] as ${type(value.type)}") { expression(it) }
        is EtsObject -> value.fields.entries.joinToString(", ", "{ ", " }") { (name, field) -> "$name: ${expression(field)}" }
        is EtsLambda -> lambda(value, true)
    }

    private fun lambda(value: EtsLambda, annotated: Boolean): String =
        "(${parameters(value.parameters)})" + (if (annotated) ": ${type(value.returnType)}" else "") + " => {\n" +
            indent(statements(value.body)).joinToString("\n") + "\n}"

    private fun parameters(values: List<EtsParameter>): String = values.joinToString(", ") {
        "${it.symbol.name}: ${type(it.symbol.type)}" + (it.defaultValue?.let { default -> " = ${expression(default)}" } ?: "")
    }

    private fun typeParameters(values: List<EtsTypeParameter>): String = if (values.isEmpty()) "" else
        values.joinToString(", ", "<", ">") { it.name + (it.upperBound?.let { bound -> " extends ${type(bound)}" } ?: "") }

    fun statements(values: List<EtsStatement>): List<String> = values.flatMap { value -> when (value) {
        is EtsVariable -> listOf("${if (value.mutable || value.initializer == null) "let" else "const"} " +
            "${value.symbol.name}: ${type(value.symbol.type)}" +
            (value.initializer?.let { " = ${expression(it)}" } ?: "") + ";")
        is EtsExpressionStatement -> listOf("${expression(value.expression)};")
        is EtsReturn -> listOf("return${value.value?.let { " ${expression(it)}" } ?: ""};")
        is EtsThrow -> listOf("throw ${expression(value.value)};")
        is EtsTry -> listOf("try {") + indent(statements(value.body)) + "}" +
            (value.handler?.let { listOf("catch (${it.parameter.name}) {") + indent(statements(it.body)) + "}" } ?: emptyList()) +
            (value.finallyBody?.let { listOf("finally {") + indent(statements(it)) + "}" } ?: emptyList())
        is EtsSuperConstructorCall -> listOf(value.arguments.joinToString(", ", "super(", ");") { expression(it) })
        is EtsBlock -> listOf("{") + indent(statements(value.statements)) + "}"
        is EtsIf -> value.branches.flatMapIndexed { index, branch ->
            val condition = branch.condition
            val head = if (condition == null) (if (index == 0) "{" else "else {") else
                "${if (index == 0) "if" else "else if"} (${expression(condition)}) {"
            listOf(head) + indent(statements(branch.body)) + "}"
        }
        is EtsLoop -> if (value.doWhile) listOf("${value.label}: do {") + indent(statements(value.body)) +
            "} while (${expression(value.condition)});" else
            listOf("${value.label}: while (${expression(value.condition)}) {") + indent(statements(value.body)) + "}"
        is EtsJump -> listOf("${if (value.isContinue) "continue" else "break"} ${value.label};")
        is EtsFunction -> function(value)
        is EtsUiElement -> {
            val call = expression(value.call)
            val attrs = value.attributes.joinToString("") { ".${expression(it)}" }
            val children = value.children
            if (children == null) listOf(call + attrs)
            else if (children.isEmpty()) listOf("$call {}$attrs")
            else listOf("$call {") + indent(statements(children)) + "}$attrs"
        }
        is EtsUiComponent -> listOf(value.properties.entries.joinToString(", ", "${expression(value.component)}({ ", " })") {
            "${it.key}: ${expression(it.value)}"
        })
        is EtsUiForEach -> listOf("ForEach(${expression(value.items)}, (${parameters(listOf(value.item))}) => {") +
            indent(statements(value.body)) + "})"
    } }

    private fun visibility(value: EtsVisibility): String = when (value) {
        EtsVisibility.PUBLIC -> ""
        EtsVisibility.PROTECTED -> "protected "
        EtsVisibility.PRIVATE -> "private "
    }

    fun global(value: EtsGlobal): List<String> = listOf((if (value.exported) "export " else "") +
        "${if (value.mutable) "let" else "const"} ${value.symbol.name}: ${type(value.symbol.type)} = ${expression(value.initializer)};")

    fun function(value: EtsFunction): List<String> {
        val prefix = (if (value.exported) "export " else "") + visibility(value.visibility) +
            (if (value.static) "static " else "") + (if (value.abstract) "abstract " else "") + when (value.kind) {
                EtsFunctionKind.FUNCTION -> "function "
                EtsFunctionKind.GETTER -> "get "
                EtsFunctionKind.SETTER -> "set "
                else -> ""
            }
        val name = if (value.kind == EtsFunctionKind.CONSTRUCTOR) "constructor" else value.name
        val result = if (value.builder || value.build || value.kind in setOf(EtsFunctionKind.CONSTRUCTOR, EtsFunctionKind.SETTER)) "" else ": ${type(value.returnType)}"
        if (value.abstract) return listOf("$prefix$name${typeParameters(value.typeParameters)}(${parameters(value.parameters)})$result;")
        return (if (value.builder) listOf("@Builder") else emptyList()) +
            listOf("$prefix$name${typeParameters(value.typeParameters)}(${parameters(value.parameters)})$result {") + indent(statements(value.body)) + "}"
    }

    fun clazz(value: EtsClass): List<String> {
        val members = value.members.flatMap { member -> when (member) {
            is EtsFunction -> if (value.kind == EtsClassKind.INTERFACE)
                listOf("${member.name}${typeParameters(member.typeParameters)}(${parameters(member.parameters)}): ${type(member.returnType)};")
                else function(member)
            is EtsField -> listOf((if (member.required) "@Require " else "") +
                (if (member.state) "@State " else if (member.prop) "@Prop " else "") +
                (member.watch?.let { "@Watch(\"$it\") " } ?: "") + visibility(member.visibility) + (if (member.static) "static " else "") +
                (if (member.readonly) "readonly " else "") +
                "${member.symbol.name}: ${type(member.symbol.type)}" +
                (member.initializer?.let { " = ${expression(it)}" } ?: "") + ";")
        } }
        val keyword = if (value.component) "struct" else if (value.kind == EtsClassKind.INTERFACE) "interface" else "class"
        val heritage = (value.baseClass?.let { " extends ${type(it)}" } ?: "") +
            (if (value.interfaces.isEmpty()) "" else value.interfaces.joinToString(", ",
                if (value.kind == EtsClassKind.INTERFACE) " extends " else " implements ") { type(it) })
        val abstract = if (value.abstract && value.kind == EtsClassKind.CLASS) "abstract " else ""
        return (if (value.entry) listOf("@Entry") else emptyList()) + (if (value.component) listOf("@Component") else emptyList()) +
            listOf("${if (value.exported) "export " else ""}$abstract$keyword ${value.name}${typeParameters(value.typeParameters)}$heritage {") + indent(members) + "}"
    }

    fun program(value: EtsProgram, support: List<String> = emptyList()): String {
        EtsValidator().validate(value)
        val imports = value.imports.map {
            if (it.default) "import ${it.alias ?: it.name} from ${quote(it.module)};"
            else "import { ${it.name}${it.alias?.let { alias -> " as $alias" } ?: ""} } from ${quote(it.module)};"
        }
        val declarations = value.files.flatMap { file -> file.declarations.map { declaration ->
            when (declaration) {
                is EtsFunction -> function(declaration)
                is EtsClass -> clazz(declaration)
                is EtsGlobal -> global(declaration)
            }.joinToString("\n")
        } }
        return (imports + listOfNotNull(support.takeIf { it.isNotEmpty() }?.joinToString("\n")) + declarations).joinToString("\n\n") + "\n"
    }

    private fun indent(lines: List<String>) = lines.flatMap { line -> line.lines().map { "  $it" } }

    private fun quote(value: String): String = value.map { character -> when (character) {
        '"' -> "\\\""
        '\\' -> "\\\\"
        '\n' -> "\\n"
        '\r' -> "\\r"
        '\t' -> "\\t"
        else -> if (character.code < 32 || character == '\u2028' || character == '\u2029') "\\u%04x".format(character.code)
            else character.toString()
    } }.joinToString("", "\"", "\"")
}
