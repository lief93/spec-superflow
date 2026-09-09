from . import graphics, layout, material, resources, state, typography
from .registry import AdapterRegistry

BUILTIN_ADAPTERS = (*graphics.ADAPTERS, *layout.ADAPTERS, *resources.ADAPTERS,
                    *state.ADAPTERS, *typography.ADAPTERS, *material.ADAPTERS)
BUILTIN_REGISTRY = AdapterRegistry(BUILTIN_ADAPTERS)
