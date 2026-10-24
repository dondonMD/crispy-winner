"""Audit deleted history too; synthetic credentials never leave temporary fixtures."""

import subprocess

from scripts.audit_public_history import audit, sensitive_path


def repository(path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], stderr=subprocess.DEVNULL)

    git("init")
    git("config", "user.name", "Synthetic Audit")
    git("config", "user.email", "synthetic@example.invalid")
    return git


def test_deleted_secret_and_database_remain_in_audit_scope(tmp_path):
    git = repository(tmp_path)
    token = "ghp_" + "a" * 36
    (tmp_path / ".env.local").write_text("TOKEN=" + token)
    (tmp_path / "private.sqlite3").write_bytes(b"SQLite format 3\0" + b"\xff" * 8)
    git("add", "-f", ".")
    git("commit", "-m", "Synthetic unsafe fixture")
    git("rm", ".env.local", "private.sqlite3")
    git("commit", "-m", "Delete synthetic fixture")
    result = audit(tmp_path)
    assert result["commits"] == 2
    assert result["verdict"] == "REVIEW_REQUIRED"
    assert ".env.local" in result["sensitive_paths"]
    assert "private.sqlite3" in result["sensitive_paths"]
    assert {"github_token", "sqlite_database"} <= {r["category"] for r in result["findings"]}
    assert token not in str(result)


def test_clean_history_and_example_contents_are_still_scanned(tmp_path):
    git = repository(tmp_path)
    (tmp_path / "README.md").write_text("Synthetic public documentation")
    (tmp_path / ".env.example").write_text("TOKEN=\nRPC=https://example.invalid\n")
    git("add", "-f", ".")
    git("commit", "-m", "Synthetic public fixture")
    assert audit(tmp_path)["verdict"] == "PATTERN_AND_PATH_SCAN_CLEAR"
    (tmp_path / ".env.example").write_text("TOKEN=" + "ghp_" + "b" * 36)
    git("add", "-f", ".")
    git("commit", "-m", "Synthetic unsafe example")
    assert audit(tmp_path)["verdict"] == "REVIEW_REQUIRED"


def test_sensitive_path_rules_cover_private_variants():
    for path in [
        ".env",
        ".env.production",
        "data/raw.json",
        "logs/run.log",
        "x.db-wal",
        "x.sqlite",
        "x.sqlite3",
        ".aws/credentials",
        "keypair.json",
    ]:
        assert sensitive_path(path)
    for path in [
        ".env.example",
        "data/.gitkeep",
        "logs/.gitkeep",
        "backend/app/db.py",
        "backend/tests/fixtures/early_edge/sdk_quotes.json",
    ]:
        assert not sensitive_path(path)
