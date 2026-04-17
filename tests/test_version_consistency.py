import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SKILL_MD_PATH = ROOT / "skills" / "last30days" / "SKILL.md"


def _skill_version() -> str:
    text = SKILL_MD_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise AssertionError("SKILL.md version frontmatter not found")
    return match.group(1)


class TestVersionConsistency(unittest.TestCase):
    def test_root_skill_header_matches_frontmatter_version(self) -> None:
        text = SKILL_MD_PATH.read_text(encoding="utf-8")
        version = _skill_version()
        self.assertIn(f"# last30days v{version}:", text)

    def test_sync_cache_path_uses_skill_version(self) -> None:
        sync_text = (ROOT / "scripts" / "sync.sh").read_text(encoding="utf-8")
        version = _skill_version()
        self.assertIn(f'last30days-3/{version}"', sync_text)


if __name__ == "__main__":
    unittest.main()
