import pathlib
import sys

SYS_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_PATH = SYS_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from config.config_wizard import ConfigWizard


def test_mark_setup_complete_prevents_reprompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text('PORTAL_URL="https://example.com"\n', encoding="utf-8")

    assert ConfigWizard.should_run_wizard() is True

    ConfigWizard.mark_setup_complete()

    assert ConfigWizard.should_run_wizard() is False
