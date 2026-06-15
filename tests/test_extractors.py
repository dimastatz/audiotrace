from unittest.mock import patch

import pytest

from audiotrace.extractors import extract_media_info


def test_ffprobe_not_installed():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("No such file or directory: 'ffprobe'")
        with pytest.raises(RuntimeError, match="ffprobe not found"):
            extract_media_info("tests/fixtures/premier_phone_call_30s.mp3")
