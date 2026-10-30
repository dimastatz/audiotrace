"""The console script builds its parser and routes commands (cli.py is excluded
from coverage, so this guards against wiring mistakes)."""

import pytest

from audiotrace.cli import main


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["baseline", "--help"],
        ["check", "--help"],
        ["simulate", "--help"],
        ["serve", "--help"],
        ["replay", "ingest", "--help"],
    ],
)
def test_help_for_every_command(argv, capsys):
    with pytest.raises(SystemExit) as exit_:
        main(argv)
    assert exit_.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_replay_review_on_an_empty_store(tmp_path, capsys):
    assert main(["replay", "review", "--store", str(tmp_path)]) == 0
    assert "0 pending case(s)" in capsys.readouterr().out


def test_missing_source_is_a_clean_error():
    with pytest.raises(SystemExit, match="give a calls directory or --provider"):
        main(["baseline"])
