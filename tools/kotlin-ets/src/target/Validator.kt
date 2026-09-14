package dev.ets

class InvalidTarget(val source: SourceSpan, message: String) : RuntimeException(message)

fun etsRestrictedValueBinding(name: String): Boolean = name == "eval" || name == "arguments"

fun etsAssignable(actual: EtsType, expected: EtsType): Boolean = when {
    actual == expected || actual == EtsTypes.NEVER -> true
    expected == EtsTypes.OBJECT -> actual !in setOf(EtsTypes.VOID, EtsTypes.UNDEFINED, EtsTypes.NULL) &&
        actual !is EtsNullableType && actual !is EtsTypeParameterType
    expected is EtsNullableType -> actual == EtsTypes.NULL ||
        etsAssignable(if (actual is EtsNullableType) actual.inner else actual, expected.inner)
    actual is EtsNamedType && expected is EtsNamedType -> actual.name == expected.name && actual.symbolId == expected.symbolId && actual.external == expected.external &&
        actual.arguments.size == expected.arguments.size &&
        (if (actual.symbolId != null) actual.arguments == expected.arguments
        else actual.arguments.zip(expected.arguments).all { (a, b) -> etsAssignable(a, b) })
    else -> false
}

/** Checks the target contract; does not re-run Kotlin semantic analysis. */
class EtsValidator {
    private var genericScope = emptyMap<String, EtsTypeParameter>()
    private var classes = emptyMap<String, EtsClass>()
    private var globalFunctions = emptyMap<String, EtsFunction>()
    private var currentClass: EtsClass? = null
    private var allowedSuper: EtsSuperConstructorCall? = null
    private var initializingClass: EtsClass? = null
    private fun reject(node: EtsNode, message: String): Nothing = throw InvalidTarget(node.source, message)
    private fun expect(value: EtsExpression, type: EtsType) {
        if (!assignable(value.type, type)) reject(value, "Target type mismatch: ${value.type}; expected $type")
    }

    private fun assignable(actual: EtsType, expected: EtsType, seen: Set<String> = emptySet()): Boolean {
        if (etsAssignable(actual, expected)) return true
        if (expected is EtsNullableType) return assignable((actual as? EtsNullableType)?.inner ?: actual, expected.inner, seen)
        if (actual is EtsTypeParameterType && actual.id !in seen) {
            return genericScope[actual.id]?.upperBound?.let { assignable(it, expected, seen + actual.id) } == true
        }
        if (actual is EtsNamedType && !actual.external && actual.symbolId != null && actual.symbolId !in seen) {
            return classes[actual.symbolId]?.let { declaration ->
                val substitutions = declaration.typeParameters.map { it.id }.zip(actual.arguments).toMap()
                parents(declaration).any { assignable(etsSubstitute(it, substitutions), expected, seen + actual.symbolId) }
            } == true
        }
        return false
    }

    private fun parents(declaration: EtsClass): List<EtsNamedType> = listOfNotNull(declaration.baseClass) + declaration.interfaces

    private fun instance(declaration: EtsClass): EtsNamedType =
        (declaration.symbol.type as EtsNamedType).copy(arguments = declaration.typeParameters.map { EtsTypeParameterType(it.id, it.name) })

    private fun parents(instance: EtsNamedType): List<EtsNamedType> {
        val declaration = classes.getValue(instance.symbolId!!)
        val substitutions = declaration.typeParameters.map { it.id }.zip(instance.arguments).toMap()
        return parents(declaration).map { etsSubstitute(it, substitutions) as EtsNamedType }
    }

    private fun ancestors(instance: EtsNamedType): List<EtsNamedType> = parents(instance).flatMap {
        listOf(it) + ancestors(it)
    }.distinct()

    private fun member(instance: EtsNamedType, name: String, setter: Boolean = false): Pair<EtsNamedType, EtsClassMember>? {
        val declaration = classes.getValue(instance.symbolId!!)
        declaration.members.firstOrNull { when (it) {
            is EtsFunction -> it.name == name && (it.kind == EtsFunctionKind.SETTER) == setter
            is EtsField -> !setter && it.symbol.name == name
        } }?.let { return instance to it }
        return parents(instance).firstNotNullOfOrNull { member(it, name, setter) }
    }

    private fun memberType(owner: EtsNamedType, value: EtsClassMember): EtsType {
        val declaration = classes.getValue(owner.symbolId!!)
        val declared = when (value) {
            is EtsField -> value.symbol.type
            is EtsFunction -> value.symbol.type
        }
        return etsSubstitute(declared, declaration.typeParameters.map { it.id }.zip(owner.arguments).toMap())
    }

    private fun sameMethodSignature(actual: EtsType, expected: EtsType): Boolean {
        if (actual == expected) return true
        if (actual !is EtsFunctionType || expected !is EtsFunctionType ||
            actual.typeParameters.size != expected.typeParameters.size) return false
        // Only method-owned binders correspond by position; free class identities stay distinct.
        val arguments = expected.typeParameters.map { EtsTypeParameterType(it.id, it.name) }
        val substitutions = actual.typeParameters.map { it.id }.zip(arguments).toMap()
        if (actual.typeParameters.zip(expected.typeParameters).any { (a, b) ->
                a.upperBound?.let { etsSubstitute(it, substitutions) } != b.upperBound
            }) return false
        return etsInstantiate(actual, arguments) == expected.copy(typeParameters = emptyList())
    }

    private fun boundReceiver(value: EtsMember): EtsNamedType {
        var bound = value.receiver.type
        val visited = mutableSetOf<String>()
        while (bound is EtsTypeParameterType) {
            if (!visited.add(bound.id)) reject(value, "Cyclic target receiver bound")
            bound = genericScope[bound.id]?.upperBound
                ?: reject(value, "Target member receiver has no declared bound")
        }
        // A named F-bound retains its arguments; only direct binder chains are followed.
        return (bound as? EtsNamedType)?.takeIf {
            !it.external && it.symbolId in classes
        } ?: reject(value, "Target member requires a nonnullable source-owned receiver bound")
    }

    private fun hierarchy() {
        fun checkPath(declaration: EtsClass, path: Set<String>) {
            if (declaration.symbol.id in path) reject(declaration, "Cyclic target heritage")
            parents(declaration).forEach { parentType ->
                val parent = parentType.symbolId?.takeUnless { parentType.external }?.let { classes[it] }
                    ?: reject(declaration, "Unbound target heritage")
                if (parent.name != parentType.name) reject(declaration, "Target heritage name differs from identity")
                if (parent.component) reject(declaration, "A target component cannot be inherited")
                checkPath(parent, path + declaration.symbol.id)
            }
        }
        classes.values.forEach { declaration ->
            if (declaration.component && (parents(declaration).isNotEmpty() || declaration.kind != EtsClassKind.CLASS || declaration.abstract)) {
                reject(declaration, "Invalid component heritage")
            }
            if (declaration.kind == EtsClassKind.INTERFACE && declaration.baseClass != null) reject(declaration, "Interface must extend interfaces")
            checkPath(declaration, emptySet())
            declaration.baseClass?.let {
                if (classes.getValue(it.symbolId!!).kind != EtsClassKind.CLASS) reject(declaration, "Base class must be a class")
            }
            declaration.interfaces.forEach {
                if (classes.getValue(it.symbolId!!).kind != EtsClassKind.INTERFACE) reject(declaration, "Implemented or extended interface must be an interface")
            }
        }
        classes.values.forEach { declaration -> withTypeParameters(declaration.typeParameters, declaration.source) {
            parents(declaration).forEach { type(it, declaration.source) }
            val inheritedTypes = ancestors(instance(declaration))
            if (inheritedTypes.groupBy { it.symbolId }.values.any { it.size > 1 }) {
                reject(declaration, "Incompatible target ancestor instantiations")
            }
            val inherited = inheritedTypes.flatMap { owner -> classes.getValue(owner.symbolId!!).members
                .filterIsInstance<EtsFunction>().filter { !it.static && it.kind != EtsFunctionKind.CONSTRUCTOR }
                .map { owner to it } }
            declaration.members.forEach { value ->
                if (declaration.kind == EtsClassKind.INTERFACE) when (value) {
                    is EtsFunction -> if (!value.abstract || value.kind != EtsFunctionKind.METHOD)
                        reject(value, "Only abstract method signatures are supported in interfaces")
                    is EtsField -> if (value.initializer != null || value.private || value.static || value.state)
                        reject(value, "Interface property must be a public instance signature")
                }
                if (value is EtsFunction) {
                    if (value.abstract && declaration.kind == EtsClassKind.CLASS && !declaration.abstract) reject(value, "Abstract method requires an abstract class")
                    value.overrides.forEach { id ->
                        val (owner, original) = inherited.firstOrNull { it.second.symbol.id == id } ?: reject(value, "Unbound target override identity")
                        if (original.name != value.name || original.kind != value.kind || !sameMethodSignature(memberType(owner, original), value.symbol.type) ||
                            value.static || value.private || original.private) reject(value, "Target override signature differs")
                    }
                    inherited.filter { it.second.name == value.name && it.second.kind == value.kind }.forEach { (owner, original) ->
                        if (!sameMethodSignature(memberType(owner, original), value.symbol.type) || original.static != value.static) reject(value, "Incompatible inherited target method")
                    }
                }
            }
            inheritedTypes.filter { classes.getValue(it.symbolId!!).kind == EtsClassKind.INTERFACE }.forEach { owner ->
                classes.getValue(owner.symbolId!!).members.filterIsInstance<EtsField>().forEach { requirement ->
                    val resolved = member(instance(declaration), requirement.symbol.name)
                        ?: reject(declaration, "Missing target property: ${requirement.symbol.name}")
                    val implementation = resolved.second
                    val propertyType = when (implementation) {
                        is EtsField -> {
                            if (implementation.private || implementation.static || (!requirement.readonly && implementation.readonly))
                                reject(declaration, "Incompatible target property access")
                            if (declaration.kind == EtsClassKind.CLASS && !declaration.abstract &&
                                classes.getValue(resolved.first.symbolId!!).kind == EtsClassKind.INTERFACE)
                                reject(declaration, "Missing concrete target property: ${requirement.symbol.name}")
                            memberType(resolved.first, implementation)
                        }
                        is EtsFunction -> {
                            if (implementation.kind != EtsFunctionKind.GETTER || implementation.private || implementation.static || implementation.abstract)
                                reject(declaration, "Target property requires a concrete getter")
                            val getterType = (memberType(resolved.first, implementation) as EtsFunctionType).result
                            if (!requirement.readonly) {
                                val setter = member(instance(declaration), requirement.symbol.name, setter = true)
                                    ?: reject(declaration, "Writable target property requires a setter")
                                val function = setter.second as EtsFunction
                                if (function.private || function.static || function.abstract ||
                                    (memberType(setter.first, function) as EtsFunctionType).parameters != listOf(getterType))
                                    reject(declaration, "Incompatible target property setter")
                            }
                            getterType
                        }
                    }
                    if (propertyType != memberType(owner, requirement)) reject(declaration, "Target property type differs from interface")
                }
            }
            if (declaration.kind == EtsClassKind.CLASS && !declaration.abstract) {
                inherited.filter { it.second.abstract }.forEach { (owner, requirement) ->
                    val resolved = member(instance(declaration), requirement.name)
                    val implementation = resolved?.second as? EtsFunction
                    if (implementation == null || implementation.abstract || implementation.static || implementation.private ||
                        implementation.kind != requirement.kind || !sameMethodSignature(memberType(resolved.first, implementation), memberType(owner, requirement))) {
                        reject(declaration, "Missing concrete target implementation: ${requirement.name}")
                    }
                }
            }
        } }
    }

    private fun <T> withTypeParameters(parameters: List<EtsTypeParameter>, source: SourceSpan,
        signature: Boolean = false, action: () -> T): T {
        val outer = genericScope
        val names = mutableSetOf<String>()
        val ids = mutableSetOf<String>()
        parameters.forEach {
            bindingName(it.name, source)
            if (!names.add(it.name) || !ids.add(it.id) || it.id.isBlank()) throw InvalidTarget(source, "Conflicting target type parameter")
            if (!signature && outer.values.any { previous -> previous.name == it.name && previous.id != it.id }) {
                throw InvalidTarget(source, "Shadowed type parameter cannot preserve its target name: ${it.name}")
            }
        }
        genericScope = outer + parameters.associateBy { it.id }
        try {
            parameters.forEach { it.upperBound?.let { bound -> type(bound, source) } }
            return action()
        } finally { genericScope = outer }
    }

    private fun typeArguments(parameters: List<EtsTypeParameter>, arguments: List<EtsType>, source: SourceSpan): Map<String, EtsType> {
        if (parameters.size != arguments.size) throw InvalidTarget(source, "Generic target argument count differs from declaration")
        arguments.forEach { type(it, source) }
        val substitutions = parameters.map { it.id }.zip(arguments).toMap()
        parameters.zip(arguments).forEach { (parameter, argument) -> parameter.upperBound?.let {
            if (!assignable(argument, etsSubstitute(it, substitutions))) throw InvalidTarget(source, "Generic target argument violates upper bound: ${parameter.name}")
        } }
        return substitutions
    }
    private fun name(name: String, source: SourceSpan) {
        if (!name.matches(Regex("[A-Za-z_$][A-Za-z0-9_$]*"))) throw InvalidTarget(source, "Invalid target identifier: $name")
    }
    private fun bindingName(name: String, source: SourceSpan) {
        name(name, source)
        if (name in reservedNames) throw InvalidTarget(source, "Reserved target identifier: $name")
    }
    private fun valueBindingName(name: String, source: SourceSpan) {
        bindingName(name, source)
        if (etsRestrictedValueBinding(name)) throw InvalidTarget(source, "Restricted strict-mode target binding: $name")
    }
    private fun type(type: EtsType, source: SourceSpan) {
        when (type) {
            is EtsNamedType -> {
                name(type.name, source)
                type.arguments.forEach { type(it, source) }
                type.symbolId?.takeUnless { type.external }?.let { id ->
                    val declaration = classes[id] ?: throw InvalidTarget(source, "Unbound target class type: $id")
                    if (declaration.name != type.name) throw InvalidTarget(source, "Target class type name differs from its declaration")
                    typeArguments(declaration.typeParameters, type.arguments, source)
                }
            }
            is EtsRecordType -> { name(type.name, source); type.fields.forEach { (field, value) -> name(field, source); type(value, source) } }
            is EtsTypeParameterType -> {
                if (genericScope[type.id]?.name != type.name) throw InvalidTarget(source, "Unbound target type parameter: ${type.id}")
            }
            is EtsNullableType -> type(type.inner, source)
            is EtsTupleType -> type.elements.forEach { type(it, source) }
            is EtsFunctionType -> withTypeParameters(type.typeParameters, source, signature = true) {
                type.parameters.forEach { type(it, source) }; type(type.result, source)
            }
        }
    }

    fun validate(program: EtsProgram, perFileNames: Boolean = false) {
        genericScope = emptyMap()
        currentClass = null
        allowedSuper = null
        val declarationIds = mutableSetOf<String>()
        program.files.flatMap { it.declarations }.forEach { declaration ->
            val id = when (declaration) { is EtsFunction -> declaration.symbol.id; is EtsClass -> declaration.symbol.id }
            if (!declarationIds.add(id)) reject(declaration, "Duplicate target declaration identity: $id")
            if (declaration is EtsClass) {
                val memberIds = mutableSetOf<Pair<String, EtsFunctionKind>>()
                declaration.members.filterIsInstance<EtsFunction>().forEach {
                    if (!memberIds.add(it.symbol.id to it.kind)) reject(it, "Duplicate target member identity: ${it.symbol.id}")
                }
            }
        }
        classes = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().associateBy { it.symbol.id }
        globalFunctions = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>().associateBy { it.symbol.id }
        hierarchy()
        val names = mutableSetOf<String>()
        val globals = program.files.flatMap { it.declarations }.map { when (it) {
            is EtsFunction -> it.symbol
            is EtsClass -> it.symbol
        } }.associateBy { it.id }
        program.imports.forEach {
            val source = SourceSpan(null, -1, -1)
            name(it.name, source); valueBindingName(it.alias ?: it.name, source)
            if (!names.add(it.alias ?: it.name)) throw InvalidTarget(source, "Conflicting target import")
        }
        val importedNames = names.toSet()
        program.files.forEach { file ->
            if (perFileNames) { names.clear(); names.addAll(importedNames) }
            file.declarations.forEach { declaration ->
            val declaredName = when (declaration) { is EtsFunction -> declaration.name; is EtsClass -> declaration.name }
            if (declaration is EtsClass && declaration.kind == EtsClassKind.INTERFACE)
                bindingName(declaredName, declaration.source)
            else valueBindingName(declaredName, declaration.source)
            if (!names.add(declaredName)) reject(declaration, "Conflicting target declaration: $declaredName")
            when (declaration) {
                is EtsFunction -> function(declaration, globals)
                is EtsClass -> {
                    currentClass = declaration
                    if (declaration.entry && !declaration.component) reject(declaration, "Entry requires a target component")
                    val memberNames = mutableSetOf<String>()
                    declaration.members.forEach { member ->
                        val key = when (member) { is EtsFunction -> member.name + if (member.kind == EtsFunctionKind.SETTER) ":set" else ""; is EtsField -> member.symbol.name }
                        if (!memberNames.add(key)) reject(member, "Conflicting target member: $key")
                        if (member is EtsFunction && (member.builder || member.build) && !declaration.component) reject(member, "UI method requires a target component")
                        if (member is EtsField && member.state && (!declaration.component || member.static)) reject(member, "State field requires a component instance")
                    }
                    withTypeParameters(declaration.typeParameters, declaration.source) { }
                    declaration.members.forEach { member ->
                    val static = when (member) { is EtsFunction -> member.static; is EtsField -> member.static }
                    withTypeParameters(if (static) emptyList() else declaration.typeParameters, declaration.source) { when (member) {
                    is EtsFunction -> function(member, globals)
                    is EtsField -> {
                        name(member.symbol.name, member.source); type(member.symbol.type, member.source)
                        member.initializer?.let { expression(it, globals); expect(it, member.symbol.type) }
                    }
                } } }
                    currentClass = null
                }
            }
        } }
    }

    private fun parameters(parameters: List<EtsParameter>, outer: Map<String, EtsSymbol>): MutableMap<String, EtsSymbol> {
        val scope = outer.toMutableMap()
        val names = mutableSetOf<String>()
        parameters.forEach { parameter ->
            valueBindingName(parameter.symbol.name, parameter.symbol.source); type(parameter.symbol.type, parameter.symbol.source)
            if (!names.add(parameter.symbol.name)) throw InvalidTarget(parameter.symbol.source, "Conflicting target parameter")
            scope.entries.removeAll { it.value.name == parameter.symbol.name }
            scope[parameter.symbol.id] = parameter.symbol
        }
        parameters.forEach { parameter -> parameter.defaultValue?.let {
            expression(it, scope); expect(it, parameter.symbol.type)
        } }
        return scope
    }

    private fun constructorArguments(classType: EtsNamedType, arguments: List<EtsExpression>, node: EtsNode) {
        val declaration = classType.symbolId?.let { classes[it] } ?: reject(node, "Unknown target constructor class")
        val constructor = declaration.members.filterIsInstance<EtsFunction>()
            .singleOrNull { it.kind == EtsFunctionKind.CONSTRUCTOR }
            ?: reject(node, "Source class requires one target constructor")
        val substitutions = typeArguments(declaration.typeParameters, classType.arguments, node.source)
        if (arguments.size > constructor.parameters.size ||
            constructor.parameters.drop(arguments.size).any { it.defaultValue == null }) reject(node, "Target constructor argument count differs")
        arguments.zip(constructor.parameters).forEach { (argument, parameter) ->
            if (argument is EtsUndefined) {
                if (parameter.defaultValue == null) reject(node, "Missing required constructor argument")
            } else expect(argument, etsSubstitute(parameter.symbol.type, substitutions))
        }
    }

    private fun function(function: EtsFunction, outer: Map<String, EtsSymbol>) {
        if (function.abstract && (function.body.isNotEmpty() || function.static || function.private || function.exported ||
            function.builder || function.build || function.kind != EtsFunctionKind.METHOD || currentClass == null ||
            function.parameters.any { it.defaultValue != null })) reject(function, "Invalid abstract method signature")
        if (function.overrides.isNotEmpty() && currentClass == null) reject(function, "Override requires a target class")
        if ((function.builder || function.build) && (function.returnType != EtsTypes.VOID || function.static ||
            (function.builder && function.build))) reject(function, "Invalid target UI method")
        if (function.builder) {
            val expectedKind = if (currentClass == null) EtsFunctionKind.FUNCTION else EtsFunctionKind.METHOD
            if (function.kind != expectedKind || (currentClass == null && function.private)) reject(function, "Invalid target builder ownership")
        }
        if (function.build && (currentClass == null || function.kind != EtsFunctionKind.METHOD)) reject(function, "Build requires a component method")
        if (function.build && (function.name != "build" || function.parameters.isNotEmpty())) reject(function, "Invalid component build signature")
        if (function.typeParameters.isNotEmpty() && function.kind in
            setOf(EtsFunctionKind.CONSTRUCTOR, EtsFunctionKind.GETTER, EtsFunctionKind.SETTER)) {
            reject(function, "Constructors and accessors cannot declare type parameters")
        }
        if (function.kind == EtsFunctionKind.GETTER &&
            (function.parameters.isNotEmpty() || function.returnType == EtsTypes.VOID)) {
            reject(function, "Target getter requires no parameters and a value result")
        }
        if (function.kind == EtsFunctionKind.SETTER &&
            (function.parameters.size != 1 || function.parameters.single().defaultValue != null || function.returnType != EtsTypes.VOID)) {
            reject(function, "Target setter requires one parameter and a void result")
        }
        val previousSuper = allowedSuper
        val previousInitializer = initializingClass
        initializingClass = currentClass.takeIf { function.kind == EtsFunctionKind.CONSTRUCTOR }
        allowedSuper = null
        val delegations = mutableListOf<EtsSuperConstructorCall>()
        walkEts(function) { if (it is EtsSuperConstructorCall) delegations.add(it) }
        val base = currentClass?.baseClass
        if (function.kind == EtsFunctionKind.CONSTRUCTOR && base != null) {
            val first = function.body.firstOrNull() as? EtsSuperConstructorCall
            if (delegations.size != 1 || first == null || first.baseClass != base) reject(function, "Derived constructor requires its direct super call first")
            allowedSuper = first
        } else if (delegations.isNotEmpty()) reject(function, "Super delegation requires a derived constructor")
        try { withTypeParameters(function.typeParameters, function.source) {
            bindingName(function.name, function.source); type(function.returnType, function.source)
            statements(function.body, parameters(function.parameters, outer), function.returnType, emptySet(), function.parameters.map { it.symbol.name }.toSet(), function.builder || function.build)
        } } finally { allowedSuper = previousSuper; initializingClass = previousInitializer }
    }

    private fun statements(values: List<EtsStatement>, outer: Map<String, EtsSymbol>, result: EtsType, loops: Set<String>, occupiedNames: Set<String> = emptySet(), ui: Boolean = false) {
        val scope = outer.toMutableMap()
        val names = occupiedNames.toMutableSet()
        values.forEach { value ->
            if (ui && value !is EtsUiElement && value !is EtsUiForEach && value !is EtsIf) reject(value, "Ordinary statement cannot occur directly in target UI DSL")
            when (value) {
            is EtsVariable -> {
                valueBindingName(value.symbol.name, value.source); type(value.symbol.type, value.source)
                value.initializer?.let { expression(it, scope); expect(it, value.symbol.type) }
                if (!names.add(value.symbol.name)) reject(value, "Conflicting target local declaration")
                scope.entries.removeAll { it.value.name == value.symbol.name }
                scope[value.symbol.id] = value.symbol
            }
            is EtsExpressionStatement -> expression(value.expression, scope)
            is EtsReturn -> if (value.value == null) {
                if (result != EtsTypes.VOID) reject(value, "Missing target return value")
            } else { expression(value.value, scope); expect(value.value, result) }
            is EtsThrow -> expression(value.value, scope)
            is EtsSuperConstructorCall -> {
                if (value !== allowedSuper) reject(value, "Super delegation outside its constructor")
                type(value.baseClass, value.source)
                value.arguments.forEach { expression(it, scope) }
                constructorArguments(value.baseClass, value.arguments, value)
            }
            is EtsBlock -> statements(value.statements, scope, result, loops)
            is EtsIf -> value.branches.forEachIndexed { index, branch ->
                if (branch.condition == null && index != value.branches.lastIndex) reject(value, "Target else branch must be last")
                branch.condition?.let { expression(it, scope); expect(it, EtsTypes.BOOLEAN) }
                statements(branch.body, scope, result, loops, ui = ui)
            }
            is EtsLoop -> {
                name(value.label, value.source); expression(value.condition, scope); expect(value.condition, EtsTypes.BOOLEAN)
                statements(value.body, scope, result, loops + value.label)
            }
            is EtsJump -> if (value.label !in loops) reject(value, "Target loop jump escapes its function or loop")
            is EtsUiElement -> {
                if (!ui) reject(value, "UI element requires a builder or component build body")
                val reference = value.call.callee as? EtsReference
                if (reference != null && !reference.symbol.external &&
                    globalFunctions[reference.symbol.id]?.builder != true) reject(value, "Source UI invocation requires a declared builder")
                expression(value.call, scope, uiInvocation = true); expect(value.call, EtsTypes.VOID)
                if (value.call.arguments.size != (value.call.callee.type as EtsFunctionType).parameters.size) reject(value, "Missing UI call argument")
                value.children?.let { statements(it, scope, EtsTypes.VOID, emptySet(), ui = true) }
                value.attributes.forEach { attribute ->
                    if (attribute.callee !is EtsReference) reject(attribute, "UI attribute requires a declared attribute symbol")
                    expression(attribute, scope); expect(attribute, EtsTypes.VOID)
                    if (attribute.arguments.size != (attribute.callee.type as EtsFunctionType).parameters.size) reject(attribute, "Missing UI attribute argument")
                }
            }
            is EtsUiForEach -> {
                if (!ui) reject(value, "UI iteration requires a builder body")
                expression(value.items, scope)
                val array = value.items.type as? EtsNamedType ?: reject(value, "UI iteration requires a target array")
                if (array.name != "Array" || array.arguments.size != 1 || array.arguments.single() != value.item.symbol.type || value.item.defaultValue != null) reject(value, "UI iteration item type differs from its array")
                statements(value.body, parameters(listOf(value.item), scope), EtsTypes.VOID, emptySet(), setOf(value.item.symbol.name), ui = true)
            }
            is EtsFunction -> reject(value, "Nested target function declarations are not supported (arkts-no-nested-funcs)")
        } }
    }

    private fun expression(value: EtsExpression, scope: Map<String, EtsSymbol>, uiInvocation: Boolean = false) {
        val classValue = value is EtsReference && classes[value.symbol.id]?.symbol == value.symbol
        if (!classValue) type(value.type, value.source)
        fun visit(child: EtsExpression) = expression(child, scope)
        when (value) {
            is EtsReference -> {
                name(value.symbol.name, value.source)
                if (value.symbol.name == "this" && currentClass == null) reject(value, "Target this requires an owning class")
                if (!value.symbol.external && scope[value.symbol.id] != value.symbol) reject(value, "Unbound target symbol: ${value.symbol.name}")
            }
            is EtsLiteral -> when (value.value) {
                null -> if (value.type != EtsTypes.NULL && value.type !is EtsNullableType) reject(value, "Null target literal has non-null type")
                is String, is Char -> expect(value, EtsTypes.STRING)
                is Number -> {
                    expect(value, EtsTypes.NUMBER)
                    if (!value.value.toDouble().isFinite()) reject(value, "Non-finite target numeric literal")
                }
                is Boolean -> expect(value, EtsTypes.BOOLEAN)
                else -> reject(value, "Unsupported target literal")
            }
            is EtsUndefined -> Unit
            is EtsMember -> {
                visit(value.receiver); name(value.name, value.source)
                val bounded = value.receiver.type is EtsTypeParameterType
                val receiverType = if (bounded) boundReceiver(value) else value.receiver.type as? EtsNamedType
                val declaration = receiverType?.takeUnless { it.external }?.symbolId?.let { classes[it] }
                if (declaration != null) {
                    val (owner, member) = member(receiverType, value.name)
                        ?: reject(value, "Unknown target class member: ${value.name}")
                    if (bounded && value.symbolId == null) reject(value, "Bounded target member requires declaration identity")
                    value.symbolId?.let { id ->
                        val actual = when (member) { is EtsFunction -> member.symbol.id; is EtsField -> member.symbol.id }
                        if (id != actual) reject(value, "Target member identity differs from receiver declaration")
                    }
                    val classReceiver = (value.receiver as? EtsReference)?.symbol == declaration.symbol
                    val static = when (member) { is EtsField -> member.static; is EtsFunction -> member.static }
                    if (classReceiver != static) reject(value, "Target member requires ${if (static) "class" else "instance"} receiver")
                    val substituted = memberType(owner, member)
                    val expected = if (member is EtsFunction && member.kind == EtsFunctionKind.GETTER)
                        (substituted as EtsFunctionType).result else substituted
                    if (expected != value.type) reject(value, "Target member type differs from receiver substitution")
                }
            }
            is EtsCall -> {
                val reference = value.callee as? EtsReference
                if (reference != null && !reference.symbol.external &&
                    globalFunctions[reference.symbol.id]?.builder == true && !uiInvocation) reject(value, "Builder invocation requires target UI DSL")
                visit(value.callee); value.arguments.forEach { visit(it) }
                val generic = value.callee.type as? EtsFunctionType ?: reject(value, "Target call requires a function type")
                val signature = if (generic.typeParameters.isEmpty()) {
                    // Existing stdlib adapters carry already-instantiated signatures and printed type arguments.
                    value.typeArguments.forEach { type(it, value.source) }
                    val memberCall = value.callee as? EtsMember
                    val receiverType = memberCall?.let {
                        if (it.receiver.type is EtsTypeParameterType) boundReceiver(it) else it.receiver.type as? EtsNamedType
                    }
                    val sourceOwned = (reference != null && !reference.symbol.external) ||
                        (receiverType != null && !receiverType.external && receiverType.symbolId in classes)
                    if (value.typeArguments.isNotEmpty() && sourceOwned) {
                        reject(value, "Non-generic source call has target type arguments")
                    }
                    generic
                } else {
                    typeArguments(generic.typeParameters, value.typeArguments, value.source)
                    etsInstantiate(generic, value.typeArguments)
                }
                if (generic.typeParameters.isNotEmpty() &&
                    (signature.result != value.type || value.arguments.size != signature.parameters.size)) {
                    reject(value, "Generic target call differs from its instantiated signature")
                }
                if (!assignable(signature.result, value.type)) reject(value, "Target call result differs from its signature")
                if (value.arguments.size > signature.parameters.size) reject(value, "Too many target arguments")
                value.arguments.zip(signature.parameters).forEach { (argument, parameter) ->
                    if (argument !is EtsUndefined) expect(argument, parameter)
                }
            }
            is EtsNew -> {
                value.arguments.forEach { visit(it) }
                value.classType.symbolId?.takeUnless { value.classType.external }?.let { id ->
                    val declaration = classes.getValue(id)
                    if (declaration.kind == EtsClassKind.INTERFACE || declaration.abstract) reject(value, "Cannot instantiate an interface or abstract class")
                    constructorArguments(value.classType, value.arguments, value)
                }
            }
            is EtsBinary -> {
                visit(value.left); visit(value.right)
                if (value.operator !in setOf("+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>", ">>>", "===", "!==", "<", "<=", ">", ">=", "&&", "||", "??", "instanceof")) reject(value, "Unknown target binary operator")
                when (value.operator) {
                    "&&", "||" -> { expect(value.left, EtsTypes.BOOLEAN); expect(value.right, EtsTypes.BOOLEAN); expect(value, EtsTypes.BOOLEAN) }
                    "===", "!==", "instanceof" -> expect(value, EtsTypes.BOOLEAN)
                    "<", "<=", ">", ">=" -> {
                        expect(value, EtsTypes.BOOLEAN)
                        if (value.left.type !in setOf(EtsTypes.NUMBER, EtsTypes.STRING) || value.left.type != value.right.type) reject(value, "Target comparison operands differ")
                    }
                    "??" -> {
                        val left = (value.left.type as? EtsNullableType)?.inner ?: value.left.type
                        if (!etsAssignable(left, value.type)) reject(value, "Target coalescing result differs from its operand")
                        expect(value.right, value.type)
                    }
                    "+" -> if (value.type == EtsTypes.STRING) {
                        if (value.left.type != EtsTypes.STRING && value.right.type != EtsTypes.STRING) reject(value, "Target string addition requires a string operand")
                    } else { expect(value.left, EtsTypes.NUMBER); expect(value.right, EtsTypes.NUMBER); expect(value, EtsTypes.NUMBER) }
                    else -> { expect(value.left, EtsTypes.NUMBER); expect(value.right, EtsTypes.NUMBER); expect(value, EtsTypes.NUMBER) }
                }
            }
            is EtsUnary -> {
                visit(value.operand)
                if (value.operator !in setOf("!", "+", "-", "~", "typeof")) reject(value, "Unknown target unary operator")
                if (value.operator == "!") { expect(value.operand, EtsTypes.BOOLEAN); expect(value, EtsTypes.BOOLEAN) }
                if (value.operator in setOf("+", "-", "~")) { expect(value.operand, EtsTypes.NUMBER); expect(value, EtsTypes.NUMBER) }
                if (value.operator == "typeof") expect(value, EtsTypes.STRING)
            }
            is EtsConditional -> {
                visit(value.condition); expect(value.condition, EtsTypes.BOOLEAN)
                visit(value.whenTrue); visit(value.whenFalse); expect(value.whenTrue, value.type); expect(value.whenFalse, value.type)
            }
            is EtsAssignment -> {
                if (value.target !is EtsReference && value.target !is EtsMember) reject(value, "Target assignment is not addressable")
                visit(value.target); visit(value.value); expect(value.value, value.target.type)
                val target = value.target as? EtsMember
                val receiver = target?.receiver?.type as? EtsNamedType
                if (receiver?.symbolId in classes) {
                    val resolved = member(receiver!!, target!!.name)!!
                    val field = resolved.second as? EtsField
                    if (field?.readonly == true && (initializingClass?.symbol?.id != resolved.first.symbolId ||
                        (target.receiver as? EtsReference)?.symbol?.name != "this")) {
                        reject(value, "Cannot assign a readonly target property")
                    }
                }
            }
            is EtsCast -> visit(value.value)
            is EtsArray -> value.elements.forEach { visit(it); expect(it, value.elementType) }
            is EtsObject -> {
                if (value.fields.keys != value.type.fields.keys) reject(value, "Target object fields differ from its record type")
                value.fields.forEach { (name, child) -> visit(child); expect(child, value.type.fields.getValue(name)) }
            }
            is EtsLambda -> {
                val previous = initializingClass
                initializingClass = null
                try { statements(value.body, parameters(value.parameters, scope), value.returnType, emptySet(), value.parameters.map { it.symbol.name }.toSet()) }
                finally { initializingClass = previous }
            }
        }
    }

    private companion object {
        val reservedNames = setOf("break", "case", "catch", "class", "const", "continue", "debugger", "default",
            "delete", "do", "else", "enum", "export", "extends", "false", "finally", "for", "function", "if",
            "import", "in", "instanceof", "new", "null", "return", "super", "switch", "this", "throw", "true",
            "try", "typeof", "var", "void", "while", "with", "yield", "implements", "interface", "let", "package",
            "private", "protected", "public", "static", "await")
    }
}
