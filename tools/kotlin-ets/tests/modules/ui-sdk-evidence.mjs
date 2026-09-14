import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import ts from '/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js';

function interfaceOnly(source) {
  const interfaces = source.statements.filter(ts.isInterfaceDeclaration);
  const imports = source.statements.filter(ts.isImportDeclaration);
  if (!interfaces.length || interfaces.length + imports.length !== source.statements.length) return false;
  if (imports.some(statement => !ts.isStringLiteral(statement.moduleSpecifier) || statement.attributes || statement.assertClause ||
      !statement.importClause || statement.importClause.name || !statement.importClause.namedBindings ||
      !ts.isNamedImports(statement.importClause.namedBindings) || !statement.importClause.namedBindings.elements.length)) return false;

  // Bind only this parsed file, without resolving dependencies, checking types or emitting.
  // Alias symbols distinguish imported type references from shadowing binders/member names.
  const options = { noLib: true, noResolve: true, noEmit: true, allowNonTsExtensions: true };
  const host = { ...ts.createCompilerHost(options),
    getSourceFile: name => name === source.fileName ? source : undefined,
    fileExists: name => name === source.fileName,
    readFile: name => name === source.fileName ? source.text : undefined,
  };
  const checker = ts.createProgram([source.fileName], options, host).getTypeChecker();
  const bindings = new Map();
  for (const statement of imports) for (const specifier of statement.importClause.namedBindings.elements) {
    const symbol = checker.getSymbolAtLocation(specifier.name);
    if (!symbol || bindings.has(symbol)) return false;
    bindings.set(symbol, false);
  }
  let valid = true;
  function visit(node) {
    if (ts.isTypeQueryNode(node) || ts.isComputedPropertyName(node) || ts.isImportTypeNode(node)) valid = false;
    if (ts.isIdentifier(node)) {
      const symbol = checker.getSymbolAtLocation(node);
      if (bindings.has(symbol)) {
        let name = node;
        while (ts.isQualifiedName(name.parent) && name.parent.left === name) name = name.parent;
        const parent = name.parent;
        const typeUse = ts.isTypeReferenceNode(parent) && parent.typeName === name ||
          ts.isExpressionWithTypeArguments(parent) && parent.expression === name && ts.isHeritageClause(parent.parent);
        if (!typeUse) valid = false;
        bindings.set(symbol, true);
      }
    }
    ts.forEachChild(node, visit);
  }
  interfaces.forEach(visit);
  return valid && [...bindings.values()].every(Boolean);
}

export function verifyModuleCoverage({ modules, ets, records, buildInfoPath, buildInfo, checker }) {
  const program = buildInfo.program;
  const paths = program.fileNames.map(path => resolve(dirname(buildInfoPath), path).toLowerCase());
  const coverage = modules.map(input => {
    const sourcePath = join(ets, 'modules', input.name);
    const index = paths.indexOf(sourcePath.toLowerCase());
    assert.ok(index >= 0, `Missing SDK checker input: ${input.name}`);
    const info = program.fileInfos[index];
    assert.equal(typeof info === 'string' ? info : info.version, input.sha256,
      `SDK checker input hash differs: ${input.name}`);
    // The pinned SDK serializes an empty diagnostic list as a numeric file ID.
    assert.ok(program.semanticDiagnosticsPerFile.includes(index + 1), `Missing clean SDK semantic result: ${input.name}`);
    const checked = checker.fileList[sourcePath];
    assert.equal(checked?.error, false, `Missing clean SDK checker-cache result: ${input.name}`);
    const record = records.find(line => line.includes(`/modules/${input.name.slice(0, -4)}.ts;`) && line.endsWith(';ets'));
    if (record) return { name: input.name, kind: 'runtime', checkerFileId: index + 1, record };

    const source = ts.createSourceFile(input.name, readFileSync(input.path, 'utf8'), ts.ScriptTarget.Latest, true);
    assert.equal(source.parseDiagnostics.length, 0, `Cannot classify erased module: ${input.name}`);
    assert.ok(interfaceOnly(source),
      `Missing runtime SDK input for non-interface-only module: ${input.name}`);
    const parents = checked.parent.filter(parent => checker.fileList[parent]?.error === false &&
      checker.fileList[parent]?.children.includes(sourcePath));
    const dependencies = parents.filter(parent => {
      const parentId = paths.indexOf(parent.toLowerCase()) + 1;
      return program.referencedMap.some(([id, list]) => id === parentId &&
        program.fileIdsList[list - 1].includes(index + 1));
    });
    assert.ok(dependencies.length > 0, `Missing SDK checked dependency for erased interface: ${input.name}`);
    return { name: input.name, kind: 'interface-only', checkerFileId: index + 1, dependencies };
  });
  assert.equal(coverage.length, modules.length);
  return coverage;
}
