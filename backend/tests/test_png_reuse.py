"""쪽 이미지 다시 쓰기: 같은 화질(dpi)로 그린 이미지가 이미 있으면 다시 그리지 않는다 (render.png_matches)."""
import pymupdf

from msds.preprocess.render import png_matches


def test_png_matches_size_for_dpi(tmp_path):
    page = pymupdf.open().new_page()
    png = tmp_path / "p001.png"
    assert not png_matches(png, page, 150)          # 없음
    page.get_pixmap(dpi=150).save(png)
    assert png_matches(png, page, 150)
    assert not png_matches(png, page, 200)          # 화질이 다르면 다시 그린다
    png.write_bytes(b"broken")
    assert not png_matches(png, page, 150)          # 깨진 파일
