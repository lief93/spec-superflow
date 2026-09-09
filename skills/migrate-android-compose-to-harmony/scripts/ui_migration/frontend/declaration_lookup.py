"""Narrow symbol candidates without changing lexical resolution or source order."""
from collections import defaultdict


class DeclarationLookup:
    def __init__(self, declarations, qualified_name):
        self.by_name = defaultdict(list)
        self.by_qualified_name = defaultdict(list)
        for position, declaration in enumerate(declarations):
            entry = (position, declaration)
            self.by_name[declaration['name']].append(entry)
            self.by_qualified_name[qualified_name(declaration)].append(entry)

    def candidates(self, name, imports, package):
        prefix, dot, suffix = name.partition('.')
        imported = imports.get(prefix)
        target = imported + ('.' + suffix if dot else '') if imported else None
        if dot:
            names = {target or name, '.'.join(filter(None, (package, name)))}
            groups = [self.by_qualified_name.get(key, ()) for key in names]
        else:
            groups = [self.by_name.get(name, ())]
            if target:
                groups.append(self.by_qualified_name.get(target, ()))
        # An import alias may overlap a local name. Preserve all candidates and
        # their original order; the existing resolver decides scope precedence.
        entries = {position: declaration for group in groups for position, declaration in group}
        return [entries[position] for position in sorted(entries)]
