from core import media_resolver


def test_old_mineru_filename_resolves_to_unique_vlm_renamed_file(tmp_path, monkeypatch):
    from config import settings

    kb = tmp_path / "knowledge_base"
    users = kb / "Users"
    share = kb / "Share"
    image_dir = users / "user-1" / "rag" / "media" / "images"
    image_dir.mkdir(parents=True)
    renamed = image_dir / "基于LLM的多查询生成与检索流程-d0acf041.png"
    renamed.write_bytes(b"image")

    monkeypatch.setattr(settings, "KNOWLEDGE_BASE_DIR", kb)
    monkeypatch.setattr(settings, "USERS_KB_DIR", users)
    monkeypatch.setattr(settings, "SHARE_KB_DIR", share)

    resolved = media_resolver.find_media_file(
        "tmpjjm0b1ox_mineru_0_d0acf041.png", subject="rag", user_id="user-1"
    )

    assert resolved == renamed


def test_hash_fallback_refuses_ambiguous_renamed_files(tmp_path):
    media_dir = tmp_path / "images"
    media_dir.mkdir()
    (media_dir / "first-d0acf041.png").write_bytes(b"one")
    (media_dir / "second-d0acf041.png").write_bytes(b"two")

    assert media_resolver._find_renamed_hash_match(
        media_dir, "tmp_mineru_0_d0acf041.png"
    ) is None


def test_resolved_media_list_deduplicates_old_and_renamed_references(tmp_path, monkeypatch):
    from config import settings

    kb = tmp_path / "knowledge_base"
    users = kb / "Users"
    share = kb / "Share"
    image_dir = users / "user-1" / "rag" / "media" / "images"
    image_dir.mkdir(parents=True)
    renamed = image_dir / "多查询生成-d0acf041.png"
    renamed.write_bytes(b"image")
    monkeypatch.setattr(settings, "KNOWLEDGE_BASE_DIR", kb)
    monkeypatch.setattr(settings, "USERS_KB_DIR", users)
    monkeypatch.setattr(settings, "SHARE_KB_DIR", share)

    resolved = media_resolver.resolve_media_list([
        {"type": "image", "path": "Users/user-1/rag/media/images/tmp_0_d0acf041.png"},
        {"type": "image", "path": "Users/user-1/rag/media/images/多查询生成-d0acf041.png"},
    ], subject="rag", user_id="user-1", deduplicate=True)

    assert len(resolved) == 1
    assert resolved[0]["relative_path"].endswith("多查询生成-d0acf041.png")
