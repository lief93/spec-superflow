"""Lossless, single-file sharing for source-page analysis data, not Lanhu layouts."""
import copy
import json

STORAGE = 'source_page_storage'
REFERENCE = '$sourceRef'
SCHEMA = 'android-to-harmony.source-page-storage.v1'


def pack_source_page(payload):
    payload = unpack_source_page(payload)
    nodes, identities, counts, sizes, scalars = [], {}, [], [], {}

    def visit(value):
        if isinstance(value, dict):
            if set(value) == {REFERENCE}:
                raise ValueError('source-page contains reserved reference object: ' + REFERENCE)
            signature = ('object', tuple((key, visit(child)) for key, child in value.items()))
            size = 2 + sum(len(json.dumps(key, ensure_ascii=False).encode()) + 2 + sizes[child]
                           for key, child in signature[1])
        elif isinstance(value, list):
            signature = ('array', tuple(visit(child) for child in value))
            size = 2 + sum(sizes[child] + 1 for child in signature[1])
        else:
            serialized = json.dumps(value, ensure_ascii=False)
            signature = (type(value).__name__, serialized)
            size = len(serialized.encode())
        identity = identities.get(signature)
        if identity is None:
            identity = len(nodes)
            identities[signature] = identity
            nodes.append(signature)
            sizes.append(size)
            counts.append(0)
            if not isinstance(value, (dict, list)):
                scalars[identity] = value
        counts[identity] += 1
        return identity

    root = visit(payload)
    shared = {}

    def emit(identity, reference=True):
        if reference and counts[identity] > 1 and sizes[identity] >= 256:
            key = 'v' + str(identity)
            if key not in shared:
                shared[key] = emit(identity, False)
            return {REFERENCE: key}
        kind, data = nodes[identity]
        if kind == 'object':
            return {key: emit(child) for key, child in data}
        if kind == 'array':
            return [emit(child) for child in data]
        return scalars[identity]

    result = emit(root, False)
    if shared:
        result[STORAGE] = {'schema': SCHEMA, 'shared': shared}
    return result


def unpack_source_page(payload):
    if STORAGE not in payload:
        return payload
    storage = payload[STORAGE]
    if not isinstance(storage, dict) or storage.get('schema') != SCHEMA:
        raise ValueError('unsupported source-page storage schema')
    shared = storage.get('shared')
    if not isinstance(shared, dict):
        raise ValueError('source-page storage requires a shared table')
    active, resolved = set(), {}

    def expand(value):
        if isinstance(value, dict):
            if set(value) == {REFERENCE}:
                key = value[REFERENCE]
                if not isinstance(key, str) or key not in shared:
                    raise ValueError('missing source-page shared reference: ' + str(key))
                if key in active:
                    raise ValueError('cyclic source-page shared reference: ' + key)
                if key not in resolved:
                    active.add(key)
                    resolved[key] = expand(shared[key])
                    active.remove(key)
                return copy.deepcopy(resolved[key])
            return {key: expand(child) for key, child in value.items()}
        if isinstance(value, list):
            return [expand(child) for child in value]
        return value

    return {key: expand(value) for key, value in payload.items() if key != STORAGE}
