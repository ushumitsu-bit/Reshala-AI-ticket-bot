import importlib

import pytest

ROUTER_MODULES = [
    "routers.actions",
    "routers.lookup",
    "routers.knowledge",
    "routers.bedolaga",
    "routers.settings",
    "routers.ai_router",
    "routers.tickets",
    "routers.kb_suggestions",
]


@pytest.mark.parametrize("module_name", ROUTER_MODULES)
def test_router_requires_manager(module_name):
    module = importlib.import_module(module_name)
    router = module.router
    dependencies = router.dependencies or []
    assert any(
        getattr(dep.dependency, "__name__", "") == "require_manager"
        for dep in dependencies
    ), f"{module_name} не защищён require_manager"
