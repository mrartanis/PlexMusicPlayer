from __future__ import annotations

from app.presentation.qt.icon_utils import _read_icon_svg, _recolor_svg


def test_icon_svg_resources_are_available() -> None:
    assert "<svg" in _read_icon_svg("play.svg")


def test_recolor_svg_preserves_none_fill() -> None:
    svg = (
        '<svg><rect fill="none"/><path d="M0 0" fill="#000000"/>'
        '<path d="M1 1" stroke="#000000"/><path d="M2 2"/></svg>'
    )

    recolored = _recolor_svg(svg, "#ffffff")

    assert 'fill="none"' in recolored
    assert 'fill="#000000"' not in recolored
    assert 'stroke="#000000"' not in recolored
    assert 'stroke="#ffffff"' in recolored
    assert recolored.count('fill="#ffffff"') == 3
    assert "/>" in recolored
