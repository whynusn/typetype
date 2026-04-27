import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WENLAI_APPLICATION_MODULES = sorted(
    (PROJECT_ROOT / "src/backend/application").glob("**/*wenlai*.py")
)


def _import_names(node: ast.ImportFrom) -> list[str]:
    leading_dots = "." * node.level
    module = f"{leading_dots}{node.module or ''}"
    names = [module]
    names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


def test_wenlai_application_modules_do_not_import_integration_or_secure_storage():
    forbidden_imports = []

    for path in WENLAI_APPLICATION_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = _import_names(node)
            else:
                continue

            for name in names:
                if "integration" in name or "secure_storage" in name:
                    forbidden_imports.append(
                        f"{path.relative_to(PROJECT_ROOT)}: {name}"
                    )

    assert forbidden_imports == []
