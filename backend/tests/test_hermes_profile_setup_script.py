import unittest
from pathlib import Path


class HermesProfileSetupScriptTests(unittest.TestCase):
    def test_profile_setup_script_documents_required_profiles_and_is_dry_run_by_default(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "scripts/setup_glame_hermes_profiles.sh").read_text(encoding="utf-8")

        self.assertIn("DRY_RUN=${DRY_RUN:-1}", script)
        self.assertIn("glame-agent-worker", script)
        for profile in [
            "glame-director",
            "glame-crm",
            "glame-brand-media",
            "glame-analytics",
            "glame-assortment",
        ]:
            self.assertIn(profile, script)
        self.assertIn("hermes profile create", script)
        self.assertIn("hermes profile list", script)


if __name__ == "__main__":
    unittest.main()
