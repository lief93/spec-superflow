"""Select a declaration, not every overload sharing the page's source/name."""
from .source_symbols import function_identity
from .model import RealPageError


def select_root_declaration(index, source, name):
    candidates = [f for f in index.by_source[source] if f['name'] == name]
    if len(candidates) == 1:
        return candidates[0]
    identities = {function_identity(f) for f in candidates}
    called = {function_identity(target) for caller in candidates
              for _, targets in index.edges[function_identity(caller)] for target in targets
              if function_identity(target) in identities and function_identity(target) != function_identity(caller)}
    entries = [f for f in candidates if function_identity(f) not in called]
    if len(entries) == 1:
        return entries[0]
    details = [f"{f['name']}({', '.join(p.get('type', '?') for p in f['parameters'])}) at {source}:{f['line']}"
               for f in candidates]
    raise RealPageError('page entry overload is ambiguous; select an unambiguous wrapper: ' + '; '.join(details))
