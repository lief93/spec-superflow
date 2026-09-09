"""Same-file references for Lanhu data; instance identities are never merged."""
from .shared_storage import pack_shared_document, unpack_shared_document

STORAGE = 'lanhu_storage'
REFERENCE = '$lanhuRef'
SCHEMA = 'android-to-harmony.lanhu-storage.v1'


def pack_lanhu_document(payload):
    return pack_shared_document(payload, storage_key=STORAGE, reference_key=REFERENCE, schema=SCHEMA)


def unpack_lanhu_document(payload):
    return unpack_shared_document(payload, storage_key=STORAGE, reference_key=REFERENCE, schema=SCHEMA)
