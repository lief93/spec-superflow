"""Readable target identifiers; hashes belong to identity records, not public names."""
import re


RESERVED = set('class interface struct function var let const new this super return default switch case if else for while do break continue try catch finally throw import export extends implements private protected public static enum type namespace package null true false void delete typeof instanceof in with yield await async constructor build aboutToAppear aboutToDisappear onPageShow onPageHide onBackPress'.split())


def source_identifier(value, fallback='Component'):
    value = str(value or '').strip('`')
    name = re.sub(r'[^A-Za-z0-9_$]', '_', value) or fallback
    if not re.match(r'[A-Za-z_$]', name):
        name = fallback + name
    return name + 'Value' if name in RESERVED else name


class NameScope:
    def __init__(self, reserved=()):
        self.used = set(reserved)

    def allocate(self, preferred, fallback='value'):
        base = source_identifier(preferred, fallback)
        name, number = base, 2
        while name in self.used:
            name = base + str(number)
            number += 1
        self.used.add(name)
        return name
