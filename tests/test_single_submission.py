import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from always_attend_mvp.codes import AttendanceCode, LocalJsonCodeSource
from always_attend_mvp.runner import SingleSubmissionRunner


def test_local_json_code_source_reads_first_entry(tmp_path: Path) -> None:
    codes_path = tmp_path / "codes.json"
    payload = [
        {"slot": "Workshop 1", "code": "ABCD1"},
        {"slot": "Workshop 2", "code": "EFGH2"},
    ]
    codes_path.write_text(json.dumps(payload), encoding="utf-8")

    source = LocalJsonCodeSource(codes_path)

    code = source.next_code()

    assert code == AttendanceCode(slot="Workshop 1", code="ABCD1")


def test_runner_submits_code_and_logs_success(caplog: pytest.LogCaptureFixture) -> None:
    source = MagicMock()
    code = AttendanceCode(slot="Workshop 7", code="MNOP7")
    source.next_code.return_value = code

    navigator = MagicMock()

    runner = SingleSubmissionRunner(code_source=source, navigator=navigator)

    with caplog.at_level(logging.INFO):
        runner.run()

    navigator.submit_code.assert_called_once_with(code)
    log_messages = [record.getMessage() for record in caplog.records]
    assert any("Workshop 7" in message and "MNOP7" in message for message in log_messages)
    assert any("elapsed" in message.lower() for message in log_messages)
