"""Разбор `.env`. Настоящий файл с кредами здесь не читается — только временные."""

from pathlib import Path

from hr_agent.config import load_dotenv, load_settings


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_plain_pairs(tmp_path, monkeypatch):
    monkeypatch.delenv("HR_MAX_ITEMS", raising=False)
    path = _write(tmp_path, "HR_MAX_ITEMS=7\n")
    assert load_dotenv(path) == ["HR_MAX_ITEMS"]
    assert load_settings(use_dotenv=False).max_items == 7


def test_skips_comments_and_blanks(tmp_path, monkeypatch):
    monkeypatch.delenv("A_KEY", raising=False)
    path = _write(tmp_path, "\n# комментарий\n\nA_KEY=value\n   \n")
    assert load_dotenv(path) == ["A_KEY"]


def test_strips_quotes_and_export_prefix(tmp_path, monkeypatch):
    for name in ("Q_KEY", "S_KEY", "E_KEY"):
        monkeypatch.delenv(name, raising=False)
    path = _write(tmp_path, "Q_KEY=\"в кавычках\"\nS_KEY='одинарные'\nexport E_KEY=exported\n")
    load_dotenv(path)
    import os

    assert os.environ["Q_KEY"] == "в кавычках"
    assert os.environ["S_KEY"] == "одинарные"
    assert os.environ["E_KEY"] == "exported"


def test_keeps_hash_inside_value(tmp_path, monkeypatch):
    """Секрет может содержать `#` — обрезать «инлайн-комментарий» нельзя."""
    monkeypatch.delenv("H_KEY", raising=False)
    path = _write(tmp_path, "H_KEY=abc#def==\n")
    load_dotenv(path)
    import os

    assert os.environ["H_KEY"] == "abc#def=="


def test_existing_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("W_KEY", "из окружения")
    path = _write(tmp_path, "W_KEY=из файла\n")
    assert load_dotenv(path) == []

    import os

    assert os.environ["W_KEY"] == "из окружения"
    assert load_dotenv(path, override=True) == ["W_KEY"]
    assert os.environ["W_KEY"] == "из файла"


def test_missing_file_is_not_an_error(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == []


def test_returns_names_not_values(tmp_path, monkeypatch):
    """Функция отдаёт только имена: значения не должны утекать в логи."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    path = _write(tmp_path, "SECRET_KEY=super-secret-token\n")
    assert load_dotenv(path) == ["SECRET_KEY"]
