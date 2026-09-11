// Relocate only generated declarations, using SDK AST positions to preserve UI syntax.
const fs = require('fs');
const path = require('path').posix;
const ts = require(process.argv[2]);
if (!ts.isStructDeclaration || ts.ScriptKind.ETS === undefined) {
  throw new Error('An ArkTS SDK parser is required');
}
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let source = ts.createSourceFile('Page.ets', input.code, ts.ScriptTarget.Latest, true, ts.ScriptKind.ETS);
const text = n => n.getText(source);
const collapsed = new Map();
// Inline only generated, single-use facades with inert arguments. Calls, local
// bindings and multi-state dispatch stay intact, preserving evaluation and scope.
const originalPage = source.statements.find(ts.isStructDeclaration);
const originalMethods = new Map((originalPage?.members || []).filter(ts.isMethodDeclaration).map(m => [m.name.text, m]));
const thisCall = n => ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) &&
  n.expression.expression.kind === ts.SyntaxKind.ThisKeyword;
const inert = n => ts.isIdentifier(n) || ts.isStringLiteral(n) || ts.isNumericLiteral(n) ||
  [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword, ts.SyntaxKind.NullKeyword].includes(n.kind);
const collapses = [];
for (const [facadeName, helperName] of Object.entries(input.facades || {})) {
  const facade = originalMethods.get(facadeName), helper = originalMethods.get(helperName);
  const statement = facade?.body?.statements;
  const call = statement?.length === 1 && ts.isExpressionStatement(statement[0]) ? statement[0].expression : null;
  if (!call || !thisCall(call) || call.expression.name.text !== helperName || !helper?.body ||
      helper.parameters.length !== call.arguments.length) continue;
  let uses = 0, safe = true;
  function count(n) {
    if (ts.isPropertyAccessExpression(n) && n.expression.kind === ts.SyntaxKind.ThisKeyword && n.name.text === helperName) uses++;
    ts.forEachChild(n, count);
  }
  count(source);
  if (uses !== 1) continue;
  const substitutions = new Map(), parameters = new Set();
  helper.parameters.forEach((p, index) => {
    if (!ts.isIdentifier(p.name)) { safe = false; return; }
    parameters.add(p.name.text);
    const argument = call.arguments[index];
    if (ts.isObjectLiteralExpression(argument)) {
      for (const property of argument.properties) {
        if (!ts.isPropertyAssignment(property) || !ts.isIdentifier(property.name) || !inert(property.initializer)) { safe = false; continue; }
        substitutions.set(p.name.text + '.' + property.name.text, text(property.initializer));
      }
    } else if (inert(argument)) substitutions.set(p.name.text, text(argument));
    else safe = false;
  });
  const replacements = [], facadeParameters = new Set(facade.parameters.map(p => text(p.name)));
  function substitute(n) {
    if (ts.isVariableDeclaration(n) || ts.isParameter(n) || ts.isFunctionDeclaration(n) || ts.isClassDeclaration(n)) safe = false;
    if (ts.isPropertyAccessExpression(n) && ts.isIdentifier(n.expression) && parameters.has(n.expression.text)) {
      const replacement = substitutions.get(text(n));
      if (replacement === undefined) safe = false;
      else replacements.push([n.getStart(source), n.end, replacement]);
      return;
    }
    if (ts.isIdentifier(n) && parameters.has(n.text)) {
      const replacement = substitutions.get(n.text);
      if (replacement === undefined) safe = false;
      else replacements.push([n.getStart(source), n.end, replacement]);
    } else if (ts.isIdentifier(n) && facadeParameters.has(n.text) &&
        !(ts.isPropertyAccessExpression(n.parent) && n.parent.name === n)) {
      safe = false;
    }
    ts.forEachChild(n, substitute);
  }
  substitute(helper.body);
  if (!safe) continue;
  let body = text(helper.body), start = helper.body.getStart(source);
  for (const [a, b, value] of replacements.sort((a,b) => b[0]-a[0])) body = body.slice(0,a-start) + value + body.slice(b-start);
  collapses.push([facade.body.getStart(source), facade.body.end, body], [helper.getStart(source), helper.end, '']);
  collapsed.set(helperName, facadeName);
  delete input.owners[helperName];
}
if (collapses.length) {
  let code = input.code;
  for (const [a, b, value] of collapses.sort((a,b) => b[0]-a[0])) code = code.slice(0,a) + value + code.slice(b);
  source = ts.createSourceFile('Page.ets', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.ETS);
}
const decorators = n => (ts.getDecorators?.(n) || n.decorators || n.illegalDecorators ||
  (n.modifiers || []).filter(ts.isDecorator)).map(d => text(d.expression));
const page = source.statements.find(ts.isStructDeclaration);
if (!page) throw new Error('Generated page struct is missing');
const builders = new Map(page.members.filter(m => ts.isMethodDeclaration(m) && decorators(m).includes('Builder'))
  .filter(m => m.name.text !== 'renderAndroidPageSnapshot').map(m => [m.name.text, m]));
const owners = new Map(Object.entries(input.owners));
const interfaceNodes = source.statements.filter(n => ts.isInterfaceDeclaration(n) || ts.isClassDeclaration(n));
const interfaceNames = new Set(interfaceNodes.map(n => n.name.text));
const types = new Map(interfaceNodes.map(n => [n.name.text, n]));
const isLayoutCall = n => ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) &&
  n.expression.expression.kind === ts.SyntaxKind.ThisKeyword && n.expression.name.text === 'layoutPx';
const fixedLayoutCall = n => isLayoutCall(n) && n.arguments.length === 1 &&
  (ts.isNumericLiteral(n.arguments[0]) || (ts.isPrefixUnaryExpression(n.arguments[0]) &&
    [ts.SyntaxKind.MinusToken, ts.SyntaxKind.PlusToken].includes(n.arguments[0].operator) &&
    ts.isNumericLiteral(n.arguments[0].operand)));
let runtimeLayout = false;
function inspectLayout(n) {
  if (isLayoutCall(n) && !fixedLayoutCall(n)) runtimeLayout = true;
  ts.forEachChild(n, inspectLayout);
}
inspectLayout(page);
const needsContext = new Set(), calls = new Map();
for (const [name, member] of builders) {
  const dependencies = new Set();
  function inspect(n) {
    if (fixedLayoutCall(n)) return;
    if (n.kind === ts.SyntaxKind.ThisKeyword) {
      const p = n.parent;
      if (ts.isPropertyAccessExpression(p) && builders.has(p.name.text) && ts.isCallExpression(p.parent) && p.parent.expression === p) {
        dependencies.add(p.name.text);
      } else needsContext.add(name);
    }
    ts.forEachChild(n, inspect);
  }
  inspect(member);
  calls.set(name, dependencies);
}
let changed = true;
while (changed) {
  changed = false;
  for (const [name, dependencies] of calls) {
    if (!needsContext.has(name) && [...dependencies].some(d => needsContext.has(d))) {
      needsContext.add(name); changed = true;
    }
  }
}
const allNames = new Set();
function collect(n) { if (ts.isIdentifier(n)) allNames.add(n.text); ts.forEachChild(n, collect); }
collect(source);
const reserved = new Set(interfaceNames);
reserved.add(page.name.text);
function reserveBindings(n) {
  if ((ts.isParameter(n) || ts.isVariableDeclaration(n) || ts.isBindingElement(n) ||
       ts.isImportSpecifier(n) || ts.isNamespaceImport(n) || ts.isImportClause(n)) && n.name) {
    reserved.add(text(n.name));
  }
  if ((ts.isCallExpression(n) || ts.isNewExpression(n) || ts.isPropertyAccessExpression(n)) && ts.isIdentifier(n.expression)) {
    reserved.add(n.expression.text);
  }
  ts.forEachChild(n, reserveBindings);
}
reserveBindings(source);
const methodNames = new Map();
for (const name of builders.keys()) {
  const preferred = input.preferred_names?.[name] || name;
  let candidate = preferred, suffix = 2;
  while (reserved.has(candidate) || (candidate !== name && allNames.has(candidate))) candidate = preferred + suffix++;
  reserved.add(candidate);
  methodNames.set(name, candidate);
}
let context = 'migrationContext';
while (allNames.has(context)) context = '_' + context;
let contextType = 'MigrationRenderContext';
while (allNames.has(contextType)) contextType = '_' + contextType;
const files = new Map();
const chunks = file => {
  if (!files.has(file)) files.set(file, {parts: [], imports: new Map(), builders: new Set(), types: new Set(), context: false});
  return files.get(file);
};
function moduleName(from, to) {
  const relative = path.relative(path.dirname(from), to).replace(/\.ets$/, '');
  return relative.startsWith('.') ? relative : './' + relative;
}
function use(file, owner, name) {
  if (file === owner) return;
  const imports = chunks(file).imports;
  if (!imports.has(owner)) imports.set(owner, new Set());
  imports.get(owner).add(name);
}
function rewrite(node, file, ctx) {
  const edits = [];
  function visit(n) {
    if (fixedLayoutCall(n)) {
      edits.push([n.getStart(source), n.end, text(n.arguments[0])]);
      return;
    }
    if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) &&
        n.expression.expression.kind === ts.SyntaxKind.ThisKeyword && builders.has(n.expression.name.text)) {
      const name = n.expression.name.text;
      const owner = owners.get(name) || file;
      chunks(owner).builders.add(name);
      use(file, owner, methodNames.get(name));
      edits.push([n.expression.getStart(source), n.expression.end, methodNames.get(name)]);
      // AST NodeArray.pos is immediately after the opening parenthesis.
      if (needsContext.has(name)) edits.push([n.arguments.pos, n.arguments.pos, ctx + (n.arguments.length ? ', ' : '')]);
    }
    if (n.kind === ts.SyntaxKind.ThisKeyword) {
      const p = n.parent;
      if (!(ts.isPropertyAccessExpression(p) && builders.has(p.name.text) && ts.isCallExpression(p.parent) && p.parent.expression === p)) {
        edits.push([n.getStart(source), n.end, ctx]);
      }
    }
    if (ts.isIdentifier(n) && interfaceNames.has(n.text)) chunks(file).types.add(n.text);
    ts.forEachChild(n, visit);
  }
  visit(node);
  let value = text(node), start = node.getStart(source);
  for (const [a, b, replacement] of edits.sort((x,y) => y[0]-x[0])) {
    value = value.slice(0,a-start) + replacement + value.slice(b-start);
  }
  return value;
}
const runtimeMembers = ['  getUIContext(): UIContext'];
const pageParts = [];
for (const member of page.members) {
  if (!text(member).trim()) continue;
  if (member.name?.text === 'layoutPx' && !runtimeLayout) continue;
  if (builders.has(member.name?.text)) continue;
  let value = rewrite(member, input.page, 'this');
  // Shared helpers/state are accessed through a typed context, not a page import.
  if (member.name?.text !== 'renderAndroidPageSnapshot' && member.name?.text !== 'build' &&
      member.name?.text !== 'aboutToAppear') {
    const privateModifier = (member.modifiers || []).find(m => m.kind === ts.SyntaxKind.PrivateKeyword);
    if (privateModifier && needsContext.size) value = value.replace(/\bprivate\s+/, '');
    if (ts.isPropertyDeclaration(member)) {
      if (!member.type) throw new Error('Generated runtime property needs an explicit type');
      runtimeMembers.push('  ' + text(member.name) + ': ' + text(member.type));
    } else if (ts.isMethodDeclaration(member)) {
      if (!member.type) throw new Error('Generated runtime helper needs an explicit return type');
      runtimeMembers.push('  ' + text(member.name) + '(' + member.parameters.map(p =>
        text(p.name) + (p.questionToken || p.initializer ? '?' : '') + ': ' + text(p.type)).join(', ') + '): ' + text(member.type));
    }
  }
  pageParts.push('  ' + value);
}
chunks(input.page).parts.push('@Component\nexport struct ' + page.name.text + ' {\n' + pageParts.join('\n\n') + '\n}');
for (const [name, file] of owners) chunks(file).builders.add(name);
// Anonymous slot builders and structural types belong to their consuming module.
// Iterate to a fixed point because a helper can reach another source module.
const emitted = new Map();
let pending = true;
while (pending) {
  pending = false;
  for (const [file, value] of files) {
    if (!emitted.has(file)) emitted.set(file, new Set());
    for (const name of value.builders) {
      if (emitted.get(file).has(name)) continue;
      emitted.get(file).add(name);
      pending = true;
      const member = builders.get(name);
      const parameters = member.parameters.map(p => rewrite(p, file, context));
      if (needsContext.has(name)) {
        value.context = true;
        parameters.unshift(context + ': ' + contextType);
      }
      const body = rewrite(member.body, file, context).split('\n').map((line,i) => i ? line.replace(/^  /, '') : line).join('\n');
      value.parts.push('@Builder\nexport function ' + methodNames.get(name) + '(' + parameters.join(', ') + ') ' + body);
    }
  }
}
for (const [file, value] of files) {
  if (value.context) {
    value.parts.push('export interface ' + contextType + ' {\n' + runtimeMembers.join('\n') + '\n}');
    value.parts.unshift("import { UIContext } from '@ohos.arkui.UIContext';");
    for (const member of page.members) {
      if (member.type) rewrite(member.type, file, context);
      if (ts.isMethodDeclaration(member) && !builders.has(member.name?.text)) {
        for (const parameter of member.parameters) if (parameter.type) rewrite(parameter.type, file, context);
      }
    }
  }
  for (const name of value.types) value.parts.push('export ' + rewrite(types.get(name), file, context));
}
const originalImports = source.statements.filter(ts.isImportDeclaration);
const output = {};
for (const [file, value] of files) {
  const imports = originalImports.map(n => {
    const module = n.moduleSpecifier.text;
    if (!module.startsWith('.')) return text(n);
    const rebased = moduleName(file, path.normalize(path.join(path.dirname(input.page), module)));
    return text(n).slice(0,n.moduleSpecifier.getStart(source)-n.getStart(source)) + JSON.stringify(rebased) + ';';
  });
  for (const [owner, names] of [...value.imports].sort()) {
    imports.push('import { ' + [...names].sort().join(', ') + ' } from ' + JSON.stringify(moduleName(file, owner)) + ';');
  }
  output[file] = '// Generated from source UI definitions; see the generation manifest.\n' +
    imports.join('\n') + '\n\n' + value.parts.join('\n\n') + '\n';
}
for (const [helper, facade] of collapsed) methodNames.set(helper, methodNames.get(facade));
process.stdout.write(JSON.stringify({files:output, methods:Object.fromEntries(owners), method_names:Object.fromEntries(methodNames),
  inlined_methods:Object.fromEntries(collapsed), context_parameter:needsContext.size ? context : null}));
