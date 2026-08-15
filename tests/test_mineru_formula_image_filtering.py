from pathlib import Path

from core.image_concept_extractor import ImageConceptExtractor
from core.mineru_client import MinerUClient


def test_mineru_only_keeps_images_referenced_by_markdown():
    markdown = """公式已经被识别为文本：

$$E = mc^2$$

![时空图](images/space%20time.jpg)
"""
    images = [
        Path("images/formula_crop.jpg"),
        Path("images/space time.jpg"),
        Path("images/another_formula_crop.png"),
    ]

    selected = MinerUClient._filter_markdown_referenced_images(markdown, images)

    assert selected == [Path("images/space time.jpg")]


def test_markdown_image_rename_updates_only_matching_path():
    old_path = "Users/u/physics/media/images/original.png"
    new_path = "Users/u/physics/media/images/时空图-a1b2c3d4.png"
    markdown = f"![图]({old_path})\n\n$$E=mc^2$$"

    updated = MinerUClient._apply_image_renames(
        markdown,
        {old_path: new_path},
    )

    assert new_path in updated
    assert old_path not in updated
    assert "$$E=mc^2$$" in updated


def test_chunk_text_and_metadata_are_updated_after_image_rename():
    old_path = "Users/u/physics/media/images/original.png"
    new_path = "Users/u/physics/media/images/diagram-a1b2c3d4.png"
    chunks = [
        {
            "text": f"before\n![图]({old_path})\nafter",
            "metadata": {
                "image_refs": [
                    {
                        "type": "image",
                        "relative_path": old_path,
                        "path": f"D:/kb/{old_path}",
                    }
                ],
                "media_refs": [],
            },
        }
    ]
    extractor = object.__new__(ImageConceptExtractor)

    extractor._update_all_media_refs(chunks, {old_path: new_path})

    assert new_path in chunks[0]["text"]
    assert chunks[0]["metadata"]["image_refs"][0]["relative_path"] == new_path
    assert chunks[0]["metadata"]["image_refs"][0]["path"].endswith(
        "diagram-a1b2c3d4.png"
    )


def test_paragraph_media_ref_with_path_only_is_updated_after_image_rename():
    old_path = "Users/u/rag/media/images/tmp_mineru_0_d0acf041.png"
    new_path = "Users/u/rag/media/images/多查询生成-d0acf041.png"
    chunks = [{
        "text": f"![图]({old_path})",
        "metadata": {
            "image_refs": [{"path": old_path}],
            "media_refs": [{"type": "image", "path": old_path}],
            "concepts": [{"media_refs": [{"type": "image", "path": old_path}]}],
        },
    }]
    extractor = object.__new__(ImageConceptExtractor)

    extractor._update_all_media_refs(chunks, {old_path: new_path})

    assert new_path in chunks[0]["text"]
    assert chunks[0]["metadata"]["image_refs"][0]["relative_path"] == new_path
    assert chunks[0]["metadata"]["media_refs"][0]["path"] == new_path
    assert chunks[0]["metadata"]["concepts"][0]["media_refs"][0]["path"] == new_path
