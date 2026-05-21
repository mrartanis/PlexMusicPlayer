from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemePalette:
    window_bg: str
    dialog_bg: str
    top_bar_bg: str
    sidebar_bg: str
    text_primary: str
    text_title: str
    text_secondary: str
    text_muted: str
    text_tech: str
    auth_text: str
    section_text: str
    album_art_bg: str
    album_art_text: str
    art_thumb_bg: str
    list_bg: str
    list_alt_bg: str
    button_bg: str
    button_hover_bg: str
    button_border: str
    button_text: str
    button_disabled_text: str
    button_disabled_border: str
    input_bg: str
    input_border: str
    queue_separator: str
    popup_bg: str
    window_control_hover_bg: str
    window_close_hover_bg: str
    slider_groove: str
    slider_handle_bg: str
    volume_track_bg: str
    play_button_outer: str
    my_wave_trailing: str


def build_main_window_stylesheet(
    *,
    accent: str,
    accent_text: str,
    theme: str,
    corner_style: str,
) -> str:
    palette = _palette_for_theme(theme)
    active_row_bg = _rgba(accent, 0.18 if theme == "light" else 0.22)
    rounded = corner_style == "rounded"
    window_radius = 18 if rounded else 0
    top_bar_radius = 10 if rounded else 0
    panel_radius = 14 if rounded else 0
    art_radius = 16 if rounded else 0
    thumb_radius = 6 if rounded else 0
    row_radius = 8 if rounded else 0
    settings_popup_radius = 12 if rounded else 0
    volume_popup_radius = 14 if rounded else 0
    menu_radius = 12 if rounded else 0
    button_radius = 9 if rounded else 0
    play_button_radius = 16 if rounded else 0
    icon_button_radius = 10 if rounded else 0
    input_radius = 8 if rounded else 0
    list_radius = 10 if rounded else 0
    list_item_radius = 7 if rounded else 0
    menu_item_radius = 8 if rounded else 0
    tab_radius = 9 if rounded else 0
    slider_radius = 3 if rounded else 0
    slider_handle_radius = 7 if rounded else 0
    volume_track_radius = 4 if rounded else 0
    volume_handle_radius = 9 if rounded else 0

    return f"""
            QMainWindow {{
                background: transparent;
                color: {palette.text_primary};
                font-family: "Avenir Next", "Segoe UI", sans-serif;
                font-size: 12px;
            }}
            QWidget {{
                background: {palette.window_bg};
                color: {palette.text_primary};
                font-family: "Avenir Next", "Segoe UI", sans-serif;
                font-size: 12px;
            }}
            QWidget#window-root {{
                background: {palette.window_bg};
                border-radius: {window_radius}px;
            }}
            QDialog {{
                background: {palette.dialog_bg};
                border-radius: {window_radius}px;
            }}
            QFrame#top-bar {{
                background: {palette.top_bar_bg};
                border: 0;
                border-radius: {top_bar_radius}px;
            }}
            QWidget#title-drag-handle {{
                background: transparent;
            }}
            QFrame {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QFrame#sidebar {{
                background: {palette.sidebar_bg};
                border-radius: {panel_radius}px;
            }}
            QLabel {{
                border: 0;
                background: transparent;
            }}
            QLabel#now-playing {{
                color: {palette.text_secondary};
                font-weight: 600;
            }}
            QLabel#track-title {{
                color: {palette.text_title};
                font-size: 28px;
                font-weight: 800;
            }}
            QLabel#track-version {{
                color: {palette.text_secondary};
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#track-artist {{
                color: {palette.text_primary};
                font-size: 16px;
                font-weight: 600;
            }}
            QLabel#track-album, QLabel#track-tech, QLabel#playback-state,
            QLabel#inline-status, QLabel#queue-summary {{
                color: {palette.text_secondary};
            }}
            QLabel#track-tech {{
                font-size: 11px;
                font-weight: 650;
                color: {palette.text_tech};
                font-family: "Menlo", "Monaco", "Courier New", monospace;
            }}
            QLabel#queue-audio-info, QLabel#seek-label {{
                color: {palette.text_primary};
                font-family: "Menlo", "Monaco", "Courier New", monospace;
                font-size: 11px;
            }}
            QLabel#queue-audio-info {{
                color: {palette.text_secondary};
            }}
            QLabel#auth-label {{
                color: {palette.auth_text};
                font-size: 11px;
                font-weight: 650;
            }}
            QLabel#browser-title {{
                color: {palette.text_title};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#nav-section {{
                color: {palette.section_text};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QLabel#settings-section {{
                color: {palette.section_text};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
                text-transform: uppercase;
                padding-top: 2px;
            }}
            QLabel#album-art {{
                background: {palette.album_art_bg};
                border: 0;
                border-radius: {art_radius}px;
                color: {palette.album_art_text};
            }}
            QLabel#art-thumb {{
                background: {palette.art_thumb_bg};
                border-radius: {thumb_radius}px;
                color: {palette.album_art_text};
            }}
            QLabel#queue-title, QLabel#browser-art-title {{
                color: {palette.text_title};
                font-weight: 650;
            }}
            QLabel#queue-title {{
                qproperty-wordWrap: false;
            }}
            QLabel#queue-subtitle, QLabel#browser-art-subtitle {{
                color: {palette.text_secondary};
                font-size: 11px;
            }}
            QLabel#queue-subtitle {{
                qproperty-wordWrap: false;
            }}
            QLabel#queue-duration {{
                color: {palette.text_primary};
                font-family: "Menlo", "Monaco", "Courier New", monospace;
                font-size: 11px;
            }}
            QWidget#queue-row-active {{
                background: {active_row_bg};
                border-radius: {row_radius}px;
            }}
            QWidget#queue-row-selected {{
                background: {accent};
                border-radius: {row_radius}px;
            }}
            QWidget#queue-row-selected QLabel#queue-title,
            QWidget#queue-row-selected QLabel#queue-subtitle,
            QWidget#queue-row-selected QLabel#queue-duration {{
                color: {accent_text};
            }}
            QWidget#queue-now-playing {{
                color: {accent};
            }}
            QWidget#queue-row-selected QWidget#queue-now-playing {{
                color: {accent_text};
            }}
            QWidget#queue-row {{
                background: transparent;
            }}
            QWidget#queue-text, QWidget#browser-art-text {{
                background: transparent;
            }}
            QFrame#queue-separator {{
                background: {palette.queue_separator};
                border: 0;
            }}
            QFrame#settings-popup, QFrame#volume-popup {{
                background: {palette.popup_bg};
                border: 0;
                border-radius: {settings_popup_radius}px;
            }}
            QFrame#settings-popup {{
                border: 1px solid {accent};
                border-radius: {settings_popup_radius}px;
            }}
            QFrame#volume-popup {{
                border: 1px solid {accent};
                border-radius: {volume_popup_radius}px;
            }}
            QMenu {{
                background: {palette.popup_bg};
                border: 1px solid {accent};
                border-radius: {menu_radius}px;
                padding: 6px;
            }}
            QMenu::item {{
                background: transparent;
                color: {palette.text_primary};
                border-radius: {menu_item_radius}px;
                padding: 6px 10px;
                margin: 1px 0;
            }}
            QMenu::item:selected {{
                background: {accent};
                color: {accent_text};
            }}
            QMenu::item:disabled {{
                color: {palette.button_disabled_text};
            }}
            QMenu::separator {{
                height: 1px;
                background: {palette.queue_separator};
                margin: 6px 4px;
            }}
            QPushButton {{
                background: {palette.button_bg};
                border: 1px solid {palette.button_border};
                border-radius: {button_radius}px;
                color: {palette.button_text};
                padding: 4px 8px;
                font-weight: 650;
            }}
            QPushButton:hover {{
                border-color: {accent};
                background: {palette.button_hover_bg};
            }}
            QPushButton:checked {{
                background: {accent};
                color: {accent_text};
            }}
            QPushButton#play-button {{
                background: qradialgradient(cx:0.5, cy:0.45, radius:0.8,
                    fx:0.5, fy:0.4, stop:0 {accent}, stop:1 {palette.play_button_outer});
                border: 1px solid {accent};
                border-radius: {play_button_radius}px;
            }}
            QPushButton#my-wave-button {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 {palette.my_wave_trailing});
                border-color: {accent};
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton#panel-close-button {{
                padding: 0;
                border-radius: {icon_button_radius}px;
                font-size: 18px;
            }}
            QPushButton#window-control-button,
            QPushButton#window-close-button,
            QPushButton#settings-toggle-button {{
                background: transparent;
                border: 0;
                border-radius: {button_radius}px;
                padding: 0;
            }}
            QPushButton#window-control-button:hover, QPushButton#settings-toggle-button:hover {{
                background: {palette.window_control_hover_bg};
                border: 0;
            }}
            QPushButton#window-close-button:hover {{
                background: {palette.window_close_hover_bg};
                border: 0;
            }}
            QPushButton#queue-icon-button {{
                padding: 0;
                border-radius: {icon_button_radius}px;
                font-size: 16px;
            }}
            QPushButton#quality-option {{
                background: {palette.button_bg};
                border: 1px solid {palette.button_border};
                color: {palette.button_text};
                padding: 6px 11px;
                border-radius: {icon_button_radius}px;
                min-width: 38px;
            }}
            QPushButton#quality-option:hover {{
                border-color: {accent};
                background: {palette.button_hover_bg};
            }}
            QPushButton#quality-option:checked {{
                background: {accent};
                border-color: {accent};
                color: {accent_text};
            }}
            QPushButton#settings-action {{
                background: {palette.button_bg};
                border: 1px solid {palette.button_border};
                border-radius: {button_radius}px;
                color: {palette.button_text};
                padding: 6px 10px;
                text-align: left;
            }}
            QPushButton#settings-action:hover {{
                background: {palette.button_hover_bg};
            }}
            QPushButton#settings-action:disabled {{
                color: {palette.button_disabled_text};
                border-color: {palette.button_disabled_border};
            }}
            QLineEdit, QComboBox {{
                background: {palette.input_bg};
                border: 1px solid {palette.input_border};
                border-radius: {input_radius}px;
                color: {palette.text_primary};
                padding: 4px 7px;
            }}
            QComboBox QAbstractItemView {{
                background: {palette.popup_bg};
                border: 1px solid {accent};
                border-radius: {menu_radius}px;
                padding: 4px;
                outline: 0;
                selection-background-color: {accent};
                selection-color: {accent_text};
            }}
            QListWidget, QListView {{
                background: {palette.list_bg};
                border: 0;
                border-radius: {list_radius}px;
                alternate-background-color: {palette.list_alt_bg};
                padding: 4px;
            }}
            QListWidget::item, QListView::item {{
                border-radius: {list_item_radius}px;
                padding: 5px;
            }}
            QListWidget#queue-list::item, QListView#queue-list::item {{
                padding: 0px;
            }}
            QListWidget::item:selected, QListView::item:selected {{
                background: {accent};
                color: {accent_text};
            }}
            QTabWidget::pane {{
                border: 0;
                border-radius: {input_radius}px;
            }}
            QTabBar::tab {{
                background: {palette.button_bg};
                color: {palette.text_secondary};
                padding: 5px 9px;
                border-top-left-radius: {tab_radius}px;
                border-top-right-radius: {tab_radius}px;
            }}
            QTabBar::tab:selected {{
                color: {accent_text};
                background: {accent};
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {palette.slider_groove};
                border-radius: {slider_radius}px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: {slider_radius}px;
            }}
            QSlider::handle:horizontal {{
                background: {palette.slider_handle_bg};
                border: 2px solid {accent};
                width: 14px;
                margin: -5px 0;
                border-radius: {slider_handle_radius}px;
            }}
            QSlider#volume-slider {{
                background: transparent;
                border: 0;
            }}
            QSlider#volume-slider:hover {{
                background: transparent;
                border: 0;
            }}
            QSlider#volume-slider::groove:vertical {{
                width: 8px;
                background: {palette.volume_track_bg};
                border-radius: {volume_track_radius}px;
            }}
            QSlider#volume-slider::sub-page:vertical {{
                background: {palette.volume_track_bg};
                border-radius: {volume_track_radius}px;
            }}
            QSlider#volume-slider::add-page:vertical {{
                background: {accent};
                border-radius: {volume_track_radius}px;
            }}
            QSlider#volume-slider::handle:vertical {{
                background: {accent};
                border: 2px solid {palette.window_bg};
                height: 16px;
                margin: 0 -7px;
                border-radius: {volume_handle_radius}px;
            }}
            QSlider#volume-slider:focus {{
                outline: 0;
                border: 0;
                background: transparent;
            }}
            QScrollBar {{
                width: 0;
                height: 0;
                background: transparent;
            }}
            """


def _palette_for_theme(theme: str) -> ThemePalette:
    if theme == "light":
        return ThemePalette(
            window_bg="#f5f7fb",
            dialog_bg="#f5f7fb",
            top_bar_bg="#eef2f8",
            sidebar_bg="#e7edf7",
            text_primary="#1f2736",
            text_title="#0f1724",
            text_secondary="#5e6b86",
            text_muted="#7b87a0",
            text_tech="#64708a",
            auth_text="#64708a",
            section_text="#73809a",
            album_art_bg="#e7ecf5",
            album_art_text="#7a879e",
            art_thumb_bg="#dee6f2",
            list_bg="#ffffff",
            list_alt_bg="#f4f7fb",
            button_bg="#f2f5fa",
            button_hover_bg="#e7edf7",
            button_border="#d4deec",
            button_text="#1b2432",
            button_disabled_text="#8c97ad",
            button_disabled_border="#d9e1ee",
            input_bg="#ffffff",
            input_border="#d4deec",
            queue_separator="#d6deea",
            popup_bg="#fbfcfe",
            window_control_hover_bg="#e5ebf5",
            window_close_hover_bg="#db6475",
            slider_groove="#d7dfec",
            slider_handle_bg="#ffffff",
            volume_track_bg="#d7dfec",
            play_button_outer="#dbe4f6",
            my_wave_trailing="#efd9a8",
        )
    return ThemePalette(
        window_bg="#1f1f1f",
        dialog_bg="#1f1f1f",
        top_bar_bg="#1a1a1a",
        sidebar_bg="#242424",
        text_primary="#d8dceb",
        text_title="#ffffff",
        text_secondary="#9ba4c2",
        text_muted="#8f98b5",
        text_tech="#7f88a8",
        auth_text="#aeb6d6",
        section_text="#7f88a8",
        album_art_bg="#181818",
        album_art_text="#737b99",
        art_thumb_bg="#292929",
        list_bg="#242424",
        list_alt_bg="#2a2a2a",
        button_bg="#303030",
        button_hover_bg="#383838",
        button_border="#474747",
        button_text="#eef1fb",
        button_disabled_text="#6f7896",
        button_disabled_border="#2c2c2c",
        input_bg="#242424",
        input_border="#494949",
            queue_separator="#3a3a3a",
            popup_bg="#1f1f1f",
            window_control_hover_bg="#2f2f2f",
            window_close_hover_bg="#8f2d3f",
            slider_groove="#3a3a3a",
            slider_handle_bg="#ffffff",
            volume_track_bg="#303030",
            play_button_outer="#353535",
            my_wave_trailing="#5d4921",
    )


def _rgba(hex_color: str, alpha: float) -> str:
    rgb = _hex_to_rgb(hex_color)
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha:.3f})"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return (82, 110, 232)
    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))
