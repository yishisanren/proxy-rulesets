import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRS_V2_MAGIC = b"SRS\x02"


class KaringRuleSetTests(unittest.TestCase):
    def test_version_deriver_preserves_rules(self):
        source = {
            "version": 1,
            "rules": [
                {"domain": ["exact.example"]},
                {"domain_suffix": ["suffix.example"]},
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source.json"
            output_path = Path(tmpdir) / "karing.json"
            source_path.write_text(json.dumps(source), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "set_ruleset_version.py"),
                    str(source_path),
                    str(output_path),
                    "2",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            derived = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(derived["version"], 2)
            self.assertEqual(derived["rules"], source["rules"])

    def test_committed_ai_and_broker_karing_artifacts_are_v2_and_lossless(self):
        pairs = [
            (
                ROOT / "ai" / "ai-all.json",
                ROOT / "ai" / "ai-all-karing.json",
                ROOT / "ai" / "ai-all-karing.srs",
            ),
            (
                ROOT / "broker" / "broker-hk.json",
                ROOT / "broker" / "broker-hk-karing.json",
                ROOT / "broker" / "broker-hk-karing.srs",
            ),
        ]

        for source_path, karing_json_path, karing_srs_path in pairs:
            with self.subTest(rule_set=source_path.stem):
                self.assertTrue(karing_json_path.is_file(), karing_json_path)
                self.assertTrue(karing_srs_path.is_file(), karing_srs_path)

                source = json.loads(source_path.read_text(encoding="utf-8"))
                derived = json.loads(karing_json_path.read_text(encoding="utf-8"))
                self.assertEqual(derived["version"], 2)
                self.assertEqual(derived["rules"], source["rules"])
                self.assertEqual(karing_srs_path.read_bytes()[:4], SRS_V2_MAGIC)

    def test_adblock_karing_artifact_is_v2(self):
        srs_path = ROOT / "adblock" / "ad-reject.srs"
        self.assertEqual(srs_path.read_bytes()[:4], SRS_V2_MAGIC)


if __name__ == "__main__":
    unittest.main()
