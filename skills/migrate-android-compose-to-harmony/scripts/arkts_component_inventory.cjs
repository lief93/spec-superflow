// Read declarations with the SDK parser; never evaluate target project code.
const fs = require('fs');
const ts = require(process.argv[2]);
if (!ts.isStructDeclaration || ts.ScriptKind.ETS === undefined) {
  throw new Error('An ArkTS SDK TypeScript parser is required, not standard TypeScript');
}
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const decorators = node => (ts.getDecorators?.(node) || node.decorators || node.illegalDecorators ||
  (node.modifiers || []).filter(ts.isDecorator)).map(d => {
    const e = ts.isCallExpression(d.expression) ? d.expression.expression : d.expression;
    return e.getText();
  });
const has = (node, kind) => (node.modifiers || []).some(m => m.kind === kind);
function type(node) {
  if (!node) return 'unknown';
  if (ts.isParenthesizedTypeNode(node)) return type(node.type);
  if (ts.isUnionTypeNode(node)) return node.types.map(type).sort().join('|');
  if (ts.isFunctionTypeNode(node)) {
    if (node.parameters.some(p => p.questionToken || p.dotDotDotToken || p.initializer)) return 'unknown';
    return '(' + node.parameters.map(p => type(p.type)).join(',') + ')=>' + type(node.type);
  }
  if (ts.isTypeReferenceNode(node)) return node.typeArguments?.length ? 'unknown' : node.typeName.getText();
  if (ts.isLiteralTypeNode(node) && node.literal.kind === ts.SyntaxKind.NullKeyword) return 'null';
  return ({[ts.SyntaxKind.StringKeyword]:'string', [ts.SyntaxKind.NumberKeyword]:'number',
    [ts.SyntaxKind.BooleanKeyword]:'boolean', [ts.SyntaxKind.VoidKeyword]:'void'})[node.kind] || 'unknown';
}
function propertyType(node) {
  if (node.type) return type(node.type);
  const value = node.initializer;
  if (!value) return 'unknown';
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) return 'string';
  if (ts.isNumericLiteral(value) || (ts.isPrefixUnaryExpression(value) &&
      [ts.SyntaxKind.PlusToken, ts.SyntaxKind.MinusToken].includes(value.operator) && ts.isNumericLiteral(value.operand))) return 'number';
  if ([ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(value.kind)) return 'boolean';
  return 'unknown';
}
const components = [], diagnostics = [];
for (const path of input.files) {
  const source = ts.createSourceFile(path, fs.readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.ETS);
  for (const node of source.statements) {
    const ds = decorators(node);
    const struct = ts.isStructDeclaration(node) && ds.some(d => ['Component','ComponentV2'].includes(d));
    const builder = ts.isFunctionDeclaration(node) && ds.includes('Builder');
    if ((!struct && !builder) || !has(node, ts.SyntaxKind.ExportKeyword) || !node.name) continue;
    if (ds.includes('Entry') || has(node, ts.SyntaxKind.DefaultKeyword)) continue;
    const record = {name:node.name.text, path, call_style:builder ? 'positional' : 'properties', parameters:[], errors:[]};
    if (node.typeParameters?.length) record.errors.push('generic component signature');
    // SDK versions may diagnose UI statements without compiler project options.
    // Ignore only method bodies; declaration diagnostics still reject the candidate.
    const bodies = builder ? [node.body] : (node.members || []).map(m => m.body).filter(Boolean);
    for (const d of source.parseDiagnostics) {
      if (d.start >= node.pos && d.start < node.end && !bodies.some(b => b && d.start >= b.pos && d.start < b.end)) {
        record.errors.push(ts.flattenDiagnosticMessageText(d.messageText, '\n'));
      }
    }
    const members = builder ? node.parameters : node.members.filter(ts.isPropertyDeclaration);
    for (const p of members) {
      const pd = decorators(p);
      if (!builder && (has(p, ts.SyntaxKind.StaticKeyword) || has(p, ts.SyntaxKind.PrivateKeyword) ||
          pd.some(d => ['State','Local','StorageProp','StorageLink','Consume','Consumer','Provide','Provider'].includes(d)))) continue;
      const allowed = ['Prop','Param','Once','Require','BuilderParam','Event'];
      const errors = pd.filter(d => !allowed.includes(d));
      if (errors.length) record.errors.push('unsupported property decorators: ' + errors.join(', '));
      if (!ts.isIdentifier(p.name) || p.dotDotDotToken) record.errors.push('unsupported parameter declaration');
      record.parameters.push({name:p.name.getText(source), type:propertyType(p),
        slot:pd.includes('BuilderParam'), required:pd.includes('Require') || !(p.initializer || p.questionToken),
        optional:!!p.questionToken});
    }
    components.push(record);
  }
}
process.stdout.write(JSON.stringify({components, diagnostics}));
