"""Materialize dependency edges only for requested declarations and their closure."""
from collections import deque
from kotlin_psi import parse_expression
from ui_migration.progress import checkpoint, phase
from .source_symbols import expression_calls, function_identity


class DependencyGraph:
    def __init__(self, index):
        self.index = index
        self.edges = {}

    def ensure(self, functions):
        pending = deque(f for f in functions if function_identity(f) not in self.edges)
        if not pending:
            return
        index = self.index
        with phase('function-dependencies', indexed_functions=len(index.functions), roots=len(pending)):
            while pending:
                function = pending.popleft()
                identity = function_identity(function)
                if identity in self.edges:
                    continue
                checkpoint('function-dependencies', indexed_functions=len(index.functions),
                           analyzed_functions=len(self.edges), pending_functions=len(pending), unit=identity)
                expressions = [function['body']]
                expressions.extend(parse_expression(p['default']) for p in function['parameters']
                                   if isinstance(p.get('default'), str))
                edges = [(call, index.resolve(call, function))
                         for expression in expressions for call in expression_calls(expression)]
                for property in index.referenced_properties(function):
                    edges.extend((call, index.resolve(call, property))
                                 for call in expression_calls(parse_expression(property['expression'])))
                self.edges[identity] = edges
                pending.extend(target for _, targets in edges for target in targets)
            checkpoint('function-dependencies', indexed_functions=len(index.functions),
                       analyzed_functions=len(self.edges), completed=len(self.edges), total=len(self.edges))
        # Preserve the original fixed-point order, but only over materialized edges.
        selected = [f for f in index.functions if function_identity(f) in self.edges]
        changed = True
        iteration = 0
        while changed:
            changed = False
            iteration += 1
            checkpoint('content-role-propagation', iteration=iteration, total=len(selected))
            for function in selected:
                identity = function_identity(function)
                if index.roles[identity] == 'unknown' and any(index.roles[function_identity(t)] == 'content'
                        for _, targets in self.edges[identity] for t in targets):
                    index.roles[identity] = 'content'
                    changed = True
        from .content_roles import refine_value_roles
        refine_value_roles(index, selected)
