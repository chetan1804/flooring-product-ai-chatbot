from __future__ import annotations

import os

from flooring_catalog.config import load_local_environment


def test_local_environment_loads_file_without_overriding_process_values(
    tmp_path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=from-file\nNEW_SETTING=loaded\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "from-process")
    monkeypatch.delenv("NEW_SETTING", raising=False)

    assert load_local_environment(env_file) is True
    assert os.environ["EXISTING"] == "from-process"
    assert os.environ["NEW_SETTING"] == "loaded"

