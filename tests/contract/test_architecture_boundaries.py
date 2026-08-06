import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ArchitectureBoundaryTests(unittest.TestCase):
    def imported_modules(self, relative_path: str) -> set[str]:
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        return modules

    def test_domain_does_not_import_infrastructure_layers(self):
        forbidden = ("wuxing.sources", "wuxing.storage", "wuxing.reporting", "wuxing.services", "cli")
        for path in ("wuxing/domain/models.py", "wuxing/domain/enums.py", "wuxing/domain/errors.py"):
            imports = self.imported_modules(path)
            self.assertFalse(
                any(module.startswith(forbidden) for module in imports),
                f"{path} 出现反向依赖：{imports}",
            )


if __name__ == "__main__":
    unittest.main()
