from . import graphics, layout, material, resources, state, typography, pager, containers
from .registry import AdapterRegistry

BUILTIN_ADAPTERS = (*graphics.ADAPTERS, *layout.ADAPTERS, *resources.ADAPTERS,
                    *state.ADAPTERS, *typography.ADAPTERS, *material.ADAPTERS, *pager.ADAPTERS, *containers.ADAPTERS)
BUILTIN_REGISTRY = AdapterRegistry(BUILTIN_ADAPTERS)
