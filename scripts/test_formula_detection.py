#!/usr/bin/env python3
"""
LA-035-P21 公式图片检测测试脚本
验证 ImageConceptExtractor._is_formula_image 的宽高比检测逻辑
"""

import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from pathlib import Path
from PIL import Image
from core.image_concept_extractor import ImageConceptExtractor

extractor = ImageConceptExtractor()
TEST_DIR = Path(r"D:\MyCS\AI\Project\LearnAnything\scripts\test_images")
TEST_DIR.mkdir(exist_ok=True)

# 创建测试图片: (width, height, expected_is_formula, description)
test_cases = [
    (300, 40, True,  "宽而矮的公式图片 (300x40, 宽高比=7.5)"),
    (200, 60, True,  "中等公式图片 (200x60, 宽高比=3.3)"),
    (150, 80, True,  "边界公式图片 (150x80, 宽高比=1.875)"),
    (120, 100, False, "接近正方形 (120x100, 宽高比=1.2)"),
    (100, 200, False, "高而窄的图片 (100x200, 宽高比=0.5)"),
    (400, 150, False, "太高的公式 (400x150, 宽高比=2.7 但高度>120)"),
    (30, 40, False,  "太小的图片 (30x40, 宽高比=0.75)"),
]

print("=" * 60)
print("公式图片检测测试")
print("=" * 60)

all_pass = True
for width, height, expected, desc in test_cases:
    img_path = TEST_DIR / f"test_{width}x{height}.png"
    
    # 创建测试图片
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    img.save(img_path)
    
    # 检测
    result = extractor._is_formula_image(img_path)
    status = "PASS" if result == expected else "FAIL"
    
    if result != expected:
        all_pass = False
    
    print(f"[{status}] {desc}")
    print(f"       预期: {expected}, 实际: {result}")
    
    # 清理
    img_path.unlink()

print("=" * 60)
if all_pass:
    print("[OK] 所有测试通过！")
else:
    print("[FAIL] 部分测试失败，请检查阈值设置。")
    sys.exit(1)
