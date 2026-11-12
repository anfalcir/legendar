from pathlib import Path

from legendar.infrastructure.config import credentials


def test_gemini_api_key_is_stored_and_retrieved_with_private_permissions(
    monkeypatch, tmp_path: Path
) -> None:
    credentials_dir = tmp_path / "credentials"
    monkeypatch.setattr(credentials, "_credentials_dir", lambda: credentials_dir)

    credentials.save_gemini_api_key("AIza-test-secret")
    assert credentials.load_gemini_api_key() == "AIza-test-secret"

    key_path = credentials_dir / "gemini_api_key"
    assert key_path.read_text(encoding="utf-8").strip() == "AIza-test-secret"
    assert key_path.stat().st_mode & 0o777 == 0o600


def test_delete_gemini_api_key_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(credentials, "_credentials_dir", lambda: tmp_path)
    credentials.save_gemini_api_key("AIza-test-secret")

    credentials.delete_gemini_api_key()
    credentials.delete_gemini_api_key()

    assert credentials.load_gemini_api_key() is None
