import com.google.gson.Gson;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.*;
import org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles;
import org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment;
import org.jetbrains.kotlin.com.intellij.openapi.Disposable;
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer;
import org.jetbrains.kotlin.com.intellij.psi.PsiErrorElement;
import org.jetbrains.kotlin.com.intellij.psi.util.PsiTreeUtil;
import org.jetbrains.kotlin.config.CompilerConfiguration;
import org.jetbrains.kotlin.psi.*;

/** Syntax only: no application code is loaded or executed. */
public final class KotlinExpressionTree {
    private static Map<String, Object> node(String kind, Object... fields) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("kind", kind);
        for (int i = 0; i < fields.length; i += 2) result.put((String) fields[i], fields[i + 1]);
        return result;
    }

    private static Map<String, Object> tree(KtExpression expression) {
        if (expression == null) return node("missing");
        Map<String, Object> result;
        if (expression instanceof KtParenthesizedExpression) {
            return tree(((KtParenthesizedExpression) expression).getExpression());
        } else if (expression instanceof KtObjectLiteralExpression) {
            List<Object> properties = new ArrayList<>();
            KtObjectDeclaration object = ((KtObjectLiteralExpression) expression).getObjectDeclaration();
            for (KtDeclaration declaration : object.getDeclarations()) {
                if (declaration instanceof KtProperty) {
                    KtProperty property = (KtProperty) declaration;
                    KtExpression value = property.getInitializer();
                    if (value == null && property.getGetter() != null) value = property.getGetter().getBodyExpression();
                    properties.add(node("property", "name", property.getName(), "mutable", property.isVar(), "value", tree(value)));
                }
            }
            result = node("object", "properties", properties);
        } else if (expression instanceof KtThisExpression) {
            result = node("name", "name", "this");
        } else if (expression instanceof KtReturnExpression) {
            result = node("return", "value", tree(((KtReturnExpression) expression).getReturnedExpression()));
        } else if (expression instanceof KtProperty) {
            KtProperty item = (KtProperty) expression;
            result = node("local", "name", item.getName(), "mutable", item.isVar(),
                "delegated", item.getDelegateExpression() != null,
                "value", tree(item.getInitializer() != null ? item.getInitializer() : item.getDelegateExpression()));
        } else if (expression instanceof KtTryExpression) {
            KtTryExpression item = (KtTryExpression) expression;
            List<Object> catches = new ArrayList<>();
            for (KtCatchClause clause : item.getCatchClauses()) {
                KtParameter parameter = clause.getCatchParameter();
                catches.add(node("catch", "type", parameter.getTypeReference().getText(), "body", tree(clause.getCatchBody())));
            }
            result = node("try", "body", tree(item.getTryBlock()), "catches", catches,
                          "hasFinally", item.getFinallyBlock() != null);
        } else if (expression instanceof KtNameReferenceExpression) {
            result = node("name", "name", ((KtNameReferenceExpression) expression).getReferencedName());
        } else if (expression instanceof KtStringTemplateExpression) {
            List<Object> parts = new ArrayList<>();
            for (KtStringTemplateEntry entry : ((KtStringTemplateExpression) expression).getEntries()) {
                if (entry instanceof KtEscapeStringTemplateEntry) {
                    parts.add(node("text", "value", ((KtEscapeStringTemplateEntry) entry).getUnescapedValue()));
                } else if (entry instanceof KtLiteralStringTemplateEntry) {
                    parts.add(node("text", "value", entry.getText()));
                } else {
                    parts.add(node("expression", "value", tree(entry.getExpression())));
                }
            }
            result = node("literal", "parts", parts);
        } else if (expression instanceof KtConstantExpression) {
            result = node("literal");
        } else if (expression instanceof KtIfExpression) {
            KtIfExpression item = (KtIfExpression) expression;
            result = node("if", "condition", tree(item.getCondition()), "yes", tree(item.getThen()), "no", tree(item.getElse()));
        } else if (expression instanceof KtWhenExpression) {
            KtWhenExpression item = (KtWhenExpression) expression;
            List<Object> entries = new ArrayList<>();
            for (KtWhenEntry entry : item.getEntries()) {
                List<Object> conditions = new ArrayList<>();
                for (KtWhenCondition condition : entry.getConditions()) {
                    if (condition instanceof KtWhenConditionIsPattern) {
                        KtWhenConditionIsPattern pattern = (KtWhenConditionIsPattern) condition;
                        conditions.add(node("type_check", "value", tree(item.getSubjectExpression()),
                            "type", pattern.getTypeReference().getText(), "negated", pattern.isNegated()));
                    } else {
                        conditions.add(condition instanceof KtWhenConditionWithExpression
                            ? tree(((KtWhenConditionWithExpression) condition).getExpression())
                            : node("unsupported", "text", condition.getText()));
                    }
                }
                entries.add(node("entry", "otherwise", entry.isElse(), "conditions", conditions, "body", tree(entry.getExpression())));
            }
            result = node("when", "subject", tree(item.getSubjectExpression()), "entries", entries);
        } else if (expression instanceof KtIsExpression) {
            KtIsExpression item = (KtIsExpression) expression;
            result = node("type_check", "value", tree(item.getLeftHandSide()),
                          "type", item.getTypeReference().getText(), "negated", item.isNegated());
        } else if (expression instanceof KtBinaryExpression) {
            KtBinaryExpression item = (KtBinaryExpression) expression;
            result = node("binary", "operator", item.getOperationReference().getText(), "left", tree(item.getLeft()), "right", tree(item.getRight()));
        } else if (expression instanceof KtUnaryExpression) {
            KtUnaryExpression item = (KtUnaryExpression) expression;
            result = node("unary", "operator", item.getOperationReference().getText(), "value", tree(item.getBaseExpression()));
        } else if (expression instanceof KtCallableReferenceExpression) {
            KtCallableReferenceExpression item = (KtCallableReferenceExpression) expression;
            result = node("callable_reference", "receiver", tree(item.getReceiverExpression()),
                          "name", item.getCallableReference().getReferencedName());
        } else if (expression instanceof KtArrayAccessExpression) {
            KtArrayAccessExpression item = (KtArrayAccessExpression) expression;
            result = node("index", "receiver", tree(item.getArrayExpression()),
                          "indices", item.getIndexExpressions().stream().map(KotlinExpressionTree::tree).toList());
        } else if (expression instanceof KtQualifiedExpression) {
            KtQualifiedExpression item = (KtQualifiedExpression) expression;
            result = node("qualified", "receiver", tree(item.getReceiverExpression()), "selector", tree(item.getSelectorExpression()),
                          "safe", expression instanceof KtSafeQualifiedExpression);
        } else if (expression instanceof KtCallExpression) {
            KtCallExpression item = (KtCallExpression) expression;
            List<Object> arguments = new ArrayList<>();
            for (KtValueArgument argument : item.getValueArguments()) {
                arguments.add(node("argument", "name", argument.getArgumentName() == null ? null : argument.getArgumentName().getAsName().asString(),
                                   "value", tree(argument.getArgumentExpression())));
            }
            result = node("call", "callee", tree(item.getCalleeExpression()), "arguments", arguments,
                          "trailingLambda", !item.getLambdaArguments().isEmpty());
        } else if (expression instanceof KtLambdaExpression) {
            KtLambdaExpression item = (KtLambdaExpression) expression;
            List<String> parameters = new ArrayList<>();
            List<Object> patterns = new ArrayList<>();
            for (KtParameter parameter : item.getValueParameters()) {
                parameters.add(parameter.getName());
                if (parameter.getDestructuringDeclaration() != null) {
                    List<String> entries = new ArrayList<>();
                    for (KtDestructuringDeclarationEntry entry : parameter.getDestructuringDeclaration().getEntries())
                        entries.add(entry.getName());
                    patterns.add(entries);
                } else {
                    patterns.add(parameter.getName());
                }
            }
            result = node("lambda", "parameters", parameters, "parameterPatterns", patterns,
                          "body", tree(item.getBodyExpression()));
        } else if (expression instanceof KtBlockExpression) {
            List<Object> statements = new ArrayList<>();
            for (KtExpression statement : ((KtBlockExpression) expression).getStatements()) statements.add(tree(statement));
            result = node("block", "statements", statements);
        } else {
            result = node("unsupported", "psiType", expression.getClass().getSimpleName());
        }
        result.put("text", expression.getText());
        return result;
    }

    private static Map<String, Object> declarations(KtFile file) {
        List<Object> functions = new ArrayList<>();
        List<Object> typeAliases = new ArrayList<>();
        for (KtTypeAlias alias : PsiTreeUtil.findChildrenOfType(file, KtTypeAlias.class)) {
            if (alias.getTypeReference() != null)
                typeAliases.add(node("type_alias", "name", alias.getName(), "type", alias.getTypeReference().getText()));
        }
        List<Object> localBindings = new ArrayList<>();
        List<Object> qualifiedCalls = new ArrayList<>();
        List<Object> globalProperties = new ArrayList<>();
        List<Object> propertyGetters = new ArrayList<>();
        List<Object> forLoops = new ArrayList<>();
        List<Object> lambdas = new ArrayList<>();
        List<Object> recordClasses = new ArrayList<>();
        for (KtClass item : PsiTreeUtil.findChildrenOfType(file, KtClass.class)) {
            if (item.getName() == null) continue;
            List<Object> fields = new ArrayList<>();
            for (KtParameter p : item.getPrimaryConstructorParameters()) {
                if (!p.hasValOrVar()) continue;
                fields.add(node("parameter", "name", p.getName(),
                    "type", p.getTypeReference() == null ? "" : p.getTypeReference().getText(),
                    "default", p.getDefaultValue() == null ? null : p.getDefaultValue().getText()));
            }
            if (!fields.isEmpty()) recordClasses.add(node("record", "name", item.getName(), "properties", fields));
        }
        for (KtForExpression loop : PsiTreeUtil.findChildrenOfType(file, KtForExpression.class)) {
            if (loop.getLoopParameter() != null && loop.getLoopParameter().getName() != null
                    && loop.getLoopRange() != null && loop.getBody() != null) {
                forLoops.add(node("for", "item_parameter", loop.getLoopParameter().getName(),
                    "collection", loop.getLoopRange().getText(),
                    "start", loop.getBody().getTextRange().getStartOffset(),
                    "end", loop.getBody().getTextRange().getEndOffset()));
            }
        }
        for (KtCallExpression call : PsiTreeUtil.findChildrenOfType(file, KtCallExpression.class)) {
            if (call.getParent() instanceof KtDotQualifiedExpression && call.getCalleeExpression() != null) {
                KtDotQualifiedExpression qualified = (KtDotQualifiedExpression) call.getParent();
                List<Object> lambdaScopes = new ArrayList<>();
                List<KtLambdaExpression> directLambdas = new ArrayList<>();
                for (KtValueArgument argument : call.getValueArguments()) {
                    if (argument.getArgumentExpression() instanceof KtLambdaExpression)
                        directLambdas.add((KtLambdaExpression) argument.getArgumentExpression());
                }
                for (KtLambdaArgument argument : call.getLambdaArguments()) {
                    KtLambdaExpression lambda = argument.getLambdaExpression();
                    if (lambda != null && !directLambdas.contains(lambda)) directLambdas.add(lambda);
                }
                for (KtLambdaExpression lambda : directLambdas) {
                    lambdaScopes.add(node("lambda_scope", "expression", tree(lambda),
                        "start", lambda.getBodyExpression().getTextOffset(),
                        "end", lambda.getBodyExpression().getTextRange().getEndOffset()));
                }
                qualifiedCalls.add(node("call", "start", call.getTextOffset(),
                    "name", qualified.getReceiverExpression().getText() + "." + call.getCalleeExpression().getText(),
                    "callee", call.getCalleeExpression().getText(),
                    "receiver", qualified.getReceiverExpression().getText(), "lambdaScopes", lambdaScopes));
            }
        }
        for (KtProperty property : PsiTreeUtil.findChildrenOfType(file, KtProperty.class)) {
            if (property.getGetter() != null && property.getGetter().getBodyExpression() != null)
                propertyGetters.add(tree(property.getGetter().getBodyExpression()));
            KtExpression propertyValue = property.getInitializer() != null ? property.getInitializer() : property.getDelegateExpression();
            boolean getterValue = property.getGetter() != null && property.getGetter().getBodyExpression() != null;
            if (getterValue) propertyValue = property.getGetter().getBodyExpression();
            if (!property.isLocal() && !property.isVar() && propertyValue != null && property.getName() != null) {
                KtClassOrObject owner = PsiTreeUtil.getParentOfType(property, KtClassOrObject.class);
                if (owner != null && owner.getName() == null) continue;
                if (owner instanceof KtObjectDeclaration && ((KtObjectDeclaration) owner).isCompanion())
                    owner = PsiTreeUtil.getParentOfType(owner, KtClassOrObject.class);
                globalProperties.add(node("property", "name", property.getName(),
                    "type", property.getTypeReference() == null ? null : property.getTypeReference().getText(),
                    "owner", owner == null ? null : owner.getName(), "expression", propertyValue.getText(),
                    "value_syntax", getterValue ? tree(propertyValue) : null));
            }
            if (!property.isLocal() || property.getName() == null) continue;
            KtBlockExpression block = PsiTreeUtil.getParentOfType(property, KtBlockExpression.class);
            KtExpression value = property.getInitializer() != null ? property.getInitializer() : property.getDelegateExpression();
            if (block != null && value != null)
                localBindings.add(node("binding", "name", property.getName(), "expression", value.getText(),
                    "delegated", property.getDelegateExpression() != null,
                    "start", property.getTextRange().getEndOffset(), "end", block.getTextRange().getEndOffset()));
        }
        for (KtDestructuringDeclaration declaration : PsiTreeUtil.findChildrenOfType(file, KtDestructuringDeclaration.class)) {
            KtBlockExpression block = PsiTreeUtil.getParentOfType(declaration, KtBlockExpression.class);
            if (block == null || declaration.getInitializer() == null) continue;
            int index = 0;
            for (KtDestructuringDeclarationEntry entry : declaration.getEntries()) {
                index++;
                if ("_".equals(entry.getName())) continue;
                localBindings.add(node("binding", "name", entry.getName(),
                    "expression", "(" + declaration.getInitializer().getText() + ").component" + index + "()",
                    "start", declaration.getTextRange().getEndOffset(), "end", block.getTextRange().getEndOffset()));
            }
        }
        for (KtLambdaExpression lambda : PsiTreeUtil.findChildrenOfType(file, KtLambdaExpression.class)) {
            lambdas.add(node("lambda_declaration", "start", lambda.getTextOffset(),
                "end", lambda.getTextRange().getEndOffset(), "expression", tree(lambda),
                "body_start", lambda.getBodyExpression().getTextOffset(),
                "line", file.getText().substring(0, lambda.getTextOffset()).split("\n", -1).length));
            for (KtParameter parameter : lambda.getValueParameters()) {
                List<String> names = new ArrayList<>();
                if (parameter.getDestructuringDeclaration() == null) names.add(parameter.getName());
                else for (KtDestructuringDeclarationEntry entry : parameter.getDestructuringDeclaration().getEntries()) names.add(entry.getName());
                for (String name : names) if (name != null)
                    localBindings.add(node("binding", "name", name, "expression", name,
                        "start", lambda.getBodyExpression().getTextOffset(), "end", lambda.getTextRange().getEndOffset()));
            }
        }
        Map<String, String> imports = new LinkedHashMap<>();
        List<String> wildcardImports = new ArrayList<>();
        for (KtImportDirective item : file.getImportDirectives()) {
            if (item.getImportedFqName() != null && item.isAllUnder()) wildcardImports.add(item.getImportedFqName().asString());
            if (item.getImportedFqName() != null && !item.isAllUnder()) {
                String name = item.getAliasName();
                imports.put(name != null ? name : item.getImportedFqName().shortName().asString(), item.getImportedFqName().asString());
            }
        }
        for (KtNamedFunction function : PsiTreeUtil.findChildrenOfType(file, KtNamedFunction.class)) {
            if (!function.hasBody() || function.getName() == null) continue;
            List<Object> parameters = new ArrayList<>();
            for (KtParameter parameter : function.getValueParameters()) {
                parameters.add(node("parameter", "name", parameter.getName(),
                    "type", parameter.getTypeReference() == null ? "" : parameter.getTypeReference().getText(),
                    "default", parameter.getDefaultValue() == null ? null : parameter.getDefaultValue().getText()));
            }
            KtClassOrObject owner = PsiTreeUtil.getParentOfType(function, KtClassOrObject.class);
            if (owner instanceof KtObjectDeclaration && ((KtObjectDeclaration) owner).isCompanion())
                owner = PsiTreeUtil.getParentOfType(owner, KtClassOrObject.class);
            functions.add(node("function", "name", function.getName(),
                "annotations", function.getAnnotationEntries().stream().map(a -> a.getShortName() == null ? "" : a.getShortName().asString()).toList(),
                "parameters_text", function.getValueParameterList() == null ? "" : function.getValueParameterList().getText(),
                "body_start", function.getBodyExpression().getTextRange().getStartOffset(),
                "start", function.getTextRange().getStartOffset(), "end", function.getTextRange().getEndOffset(),
                "package", file.getPackageFqName().asString(),
                "owner", owner == null ? null : owner.getName(),
                "receiver", function.getReceiverTypeReference() == null ? null : function.getReceiverTypeReference().getText(),
                "return_type", function.getTypeReference() == null ? null : function.getTypeReference().getText(),
                "parameters", parameters, "body", tree(function.getBodyExpression()),
                "line", file.getText().substring(0, function.getTextOffset()).split("\n", -1).length));
        }
        return node("declarations", "functions", functions, "typeAliases", typeAliases, "imports", imports, "localBindings", localBindings,
                    "qualifiedCalls", qualifiedCalls, "globalProperties", globalProperties,
                    "propertyGetters", propertyGetters, "forLoops", forLoops, "lambdas", lambdas, "recordClasses", recordClasses,
                    "package", file.getPackageFqName().asString(), "wildcardImports", wildcardImports);
    }

    public static void main(String[] args) throws Exception {
        Disposable disposable = Disposer.newDisposable();
        try {
            KotlinCoreEnvironment environment = KotlinCoreEnvironment.createForProduction(disposable,
                new CompilerConfiguration(), EnvironmentConfigFiles.JVM_CONFIG_FILES);
            KtPsiFactory factory = new KtPsiFactory(environment.getProject(), false);
            Gson gson = new Gson();
            BufferedReader input = new BufferedReader(new InputStreamReader(System.in, java.nio.charset.StandardCharsets.UTF_8));
            for (String line; (line = input.readLine()) != null;) {
                try {
                    com.google.gson.JsonElement request = gson.fromJson(line, com.google.gson.JsonElement.class);
                    if (request.isJsonObject()) {
                        String source = request.getAsJsonObject().get("source").getAsString();
                        if (source.length() > 1048576) throw new IllegalArgumentException("source exceeds 1 MiB");
                        System.out.println(gson.toJson(declarations(factory.createFile(source))));
                        System.out.flush();
                        continue;
                    }
                    String source = request.getAsString();
                    if (source.length() > 65536) throw new IllegalArgumentException("expression exceeds 64 KiB");
                    // Parse the entire input: comments are trivia, extra declarations are not.
                    String normalizedSource = source.replace("\r\n", "\n").replace('\r', '\n');
                    KtFile file = factory.createFile("val __expression = " + normalizedSource + "\n");
                    List<KtDeclaration> declarations = file.getDeclarations();
                    if (declarations.size() != 1 || !(declarations.get(0) instanceof KtProperty))
                        throw new IllegalArgumentException("expression contains unparsed trailing declarations");
                    Collection<PsiErrorElement> errors = PsiTreeUtil.findChildrenOfType(file, PsiErrorElement.class);
                    if (!errors.isEmpty()) throw new IllegalArgumentException(errors.iterator().next().getErrorDescription());
                    KtProperty property = (KtProperty) declarations.get(0);
                    System.out.println(gson.toJson(tree(property.getInitializer())));
                } catch (RuntimeException error) {
                    System.out.println(gson.toJson(node("error", "message", error.getMessage())));
                }
                System.out.flush();
            }
        } finally {
            Disposer.dispose(disposable);
        }
    }
}
