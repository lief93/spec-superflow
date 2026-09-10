// Relocate only generated declarations, using SDK AST positions to preserve UI syntax.
const fs = require('fs');
const path = require('path').posix;
const ts = require(process.argv[2]);
if (!ts.isStructDeclaration || ts.ScriptKind.ETS === undefined) {
  throw new Error('An ArkTS SDK parser is required');
}
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = ts.createSourceFile('Page.ets', input.code, ts.ScriptTarget.Latest, true, ts.ScriptKind.ETS);
const text = n => n.getText(source);
const decorators = n => (ts.getDecorators?.(n) || n.decorators || n.illegalDecorators ||
  (n.modifiers || []).filter(ts.isDecorator)).map(d => text(d.expression));
const page = source.statements.find(ts.isStructDeclaration);
if (!page) throw new Error('Generated page struct is missing');
const builders = new Map(page.members.filter(m => ts.isMethodDeclaration(m) && decorators(m).includes('Builder'))
  .filter(m => m.name.text !== 'renderAndroidPageSnapshot').map(m => [m.name.text, m]));
const runtimePath = input.support + '/Runtime.ets';
const slotsPath = input.support + '/Builders.ets';
const owners = new Map([...builders.keys()].map(name => [name, input.owners[name] || slotsPath]));
const interfaceNodes = source.statements.filter(n => ts.isInterfaceDeclaration(n) || ts.isClassDeclaration(n));
const interfaceNames = new Set(interfaceNodes.map(n => n.name.text));
const interfaceOwners = new Map(interfaceNodes.map(n => [n.name.text,
  owners.get(n.name.text.replace(/Props$/, '')) || runtimePath]));
const needsContext = new Set(), calls = new Map();
for (const [name, member] of builders) {
  const dependencies = new Set();
  function inspect(n) {
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
  let candidate = name, suffix = 2;
  while (reserved.has(candidate) || (candidate !== name && allNames.has(candidate))) candidate = name + suffix++;
  reserved.add(candidate);
  methodNames.set(name, candidate);
}
let context = 'migrationContext';
while (allNames.has(context)) context = '_' + context;
let contextType = 'MigrationRenderContext';
while (allNames.has(contextType)) contextType = '_' + contextType;
const files = new Map();
const chunks = file => {
  if (!files.has(file)) files.set(file, {parts: [], imports: new Map()});
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
    if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) &&
        n.expression.expression.kind === ts.SyntaxKind.ThisKeyword && builders.has(n.expression.name.text)) {
      const name = n.expression.name.text;
      use(file, owners.get(name), methodNames.get(name));
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
    if (ts.isIdentifier(n) && interfaceNames.has(n.text)) use(file, interfaceOwners.get(n.text), n.text);
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
for (const [name, member] of builders) {
  const file = owners.get(name);
  if (needsContext.has(name)) use(file, runtimePath, contextType);
  const parameters = member.parameters.map(p => rewrite(p, file, context));
  if (needsContext.has(name)) parameters.unshift(context + ': ' + contextType);
  const body = rewrite(member.body, file, context).split('\n').map((line,i) => i ? line.replace(/^  /, '') : line).join('\n');
  chunks(file).parts.push('@Builder\nexport function ' + methodNames.get(name) + '(' + parameters.join(', ') + ') ' + body);
}
for (const node of interfaceNodes) chunks(interfaceOwners.get(node.name.text)).parts.push('export ' + text(node));
if (needsContext.size) {
  chunks(runtimePath).parts.push('export interface ' + contextType + ' {\n' + runtimeMembers.join('\n') + '\n}');
  chunks(runtimePath).parts.unshift("import { UIContext } from '@ohos.arkui.UIContext';");
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
process.stdout.write(JSON.stringify({files:output, methods:Object.fromEntries(owners), method_names:Object.fromEntries(methodNames), context_parameter:needsContext.size ? context : null}));
