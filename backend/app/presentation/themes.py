from dataclasses import dataclass
from typing import Tuple


@dataclass
class ThemeColor:
    primary: Tuple[int, int, int]
    secondary: Tuple[int, int, int]
    accent: Tuple[int, int, int]
    background: Tuple[int, int, int]
    text: Tuple[int, int, int]
    card_bg: Tuple[int, int, int]


@dataclass
class PresentationTheme:
    name: str
    colors: ThemeColor
    primary_font: str
    secondary_font: str
    title_size: int
    subtitle_size: int
    heading_size: int
    body_size: int


THEMES = {
    "Professional": PresentationTheme(
        name="Professional",
        colors=ThemeColor(
            primary=(15, 44, 89),       # Deep Navy
            secondary=(53, 89, 143),    # Slate Blue
            accent=(217, 119, 6),       # Warm Amber
            background=(255, 255, 255), # Pure White
            text=(30, 41, 59),          # Dark Charcoal
            card_bg=(241, 245, 249)     # Soft Gray
        ),
        primary_font="Arial",
        secondary_font="Calibri",
        title_size=36,
        subtitle_size=20,
        heading_size=24,
        body_size=14,
    ),
    "Minimal": PresentationTheme(
        name="Minimal",
        colors=ThemeColor(
            primary=(17, 24, 39),       # Dark Slate
            secondary=(75, 85, 99),     # Neutral Gray
            accent=(99, 102, 241),      # Indigo Accent
            background=(250, 250, 250), # Off White
            text=(17, 24, 39),
            card_bg=(243, 244, 246)
        ),
        primary_font="Helvetica",
        secondary_font="Arial",
        title_size=34,
        subtitle_size=18,
        heading_size=22,
        body_size=14,
    ),
    "Dark": PresentationTheme(
        name="Dark",
        colors=ThemeColor(
            primary=(244, 244, 245),    # Near White Title
            secondary=(161, 161, 170),  # Muted Text
            accent=(59, 130, 246),      # Electric Blue
            background=(18, 24, 38),    # Dark Obsidian
            text=(226, 232, 240),       # Light Text
            card_bg=(30, 41, 59)        # Dark Card
        ),
        primary_font="Trebuchet MS",
        secondary_font="Calibri",
        title_size=36,
        subtitle_size=20,
        heading_size=24,
        body_size=14,
    ),
    "Corporate": PresentationTheme(
        name="Corporate",
        colors=ThemeColor(
            primary=(0, 64, 128),       # Royal Blue
            secondary=(0, 102, 204),
            accent=(0, 153, 76),        # Corporate Emerald
            background=(255, 255, 255),
            text=(33, 37, 41),
            card_bg=(238, 242, 246)
        ),
        primary_font="Georgia",
        secondary_font="Calibri",
        title_size=36,
        subtitle_size=20,
        heading_size=24,
        body_size=14,
    ),
    "Modern": PresentationTheme(
        name="Modern",
        colors=ThemeColor(
            primary=(13, 148, 136),     # Teal Primary
            secondary=(45, 212, 191),   # Soft Teal
            accent=(244, 63, 94),       # Modern Rose
            background=(255, 255, 255),
            text=(15, 23, 42),
            card_bg=(240, 253, 250)
        ),
        primary_font="Segoe UI",
        secondary_font="Segoe UI",
        title_size=36,
        subtitle_size=20,
        heading_size=24,
        body_size=14,
    ),
}


def get_theme(theme_name: str) -> PresentationTheme:
    return THEMES.get(theme_name, THEMES["Professional"])
