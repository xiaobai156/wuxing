from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SingleBatPeriodPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "杀五行_修复版2-单期.bat").read_text(encoding="utf-8-sig")

    def test_double_click_path_prompts_for_a_period(self):
        self.assertIn('if not "%~1"=="" goto run_args', self.source)
        self.assertIn('set /p "PERIOD=', self.source)
        self.assertIn('py -3 -m cli.single "%PERIOD%"', self.source)

    def test_explicit_arguments_are_forwarded_without_rewriting(self):
        self.assertIn("py -3 -m cli.single %*", self.source)


if __name__ == "__main__":
    unittest.main()
