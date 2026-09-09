"""Prove non-emitting expressions without treating @Composable as a visual node."""


def returns_only_value(node):
    kind = node.get('kind')
    # Creating a lambda/reference does not execute its body.
    if kind in {'name', 'lambda', 'callable_reference'}:
        return True
    if kind == 'literal':
        return all(p.get('kind') == 'text' or (
            p.get('kind') == 'expression' and returns_only_value(p['value'])) for p in node.get('parts', []))
    if kind == 'qualified':
        return returns_only_value(node['receiver']) and returns_only_value(node['selector'])
    if kind == 'if':
        return all(returns_only_value(node[key]) for key in ('condition', 'yes', 'no') if node.get(key))
    # Calls and blocks remain subject to content/dependency analysis, even if
    # their result is assigned to a local variable.
    return False
