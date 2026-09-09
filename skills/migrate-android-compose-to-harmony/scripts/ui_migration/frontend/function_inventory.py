"""PSI function bodies used only for bounded, fixed-state source evaluation."""
from ui_migration.frontend.source_symbols import SourceSymbolIndex


def source_functions(source_root, index=None):
    if source_root is None:
        return []
    functions = []
    index = index or SourceSymbolIndex.from_root(source_root)
    files = {source_root/path: syntax for path, syntax in index.syntax.items()}
    for path, syntax in files.items():
        for function in syntax['functions']:
            globals = index.global_values({**function, 'source':path.relative_to(source_root).as_posix()})
            functions.append({**function, 'source': path.relative_to(source_root).as_posix(),
                              'imports': syntax['imports'], 'wildcard_imports': syntax['wildcardImports'],
                              'global_values': {k: v for k, v in globals.items() if v is not None}})
    return functions
