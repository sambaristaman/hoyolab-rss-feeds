from datetime import datetime
from enum import Enum
from enum import IntEnum, unique
from pathlib import Path
from typing import List
from typing import Optional
from typing import Type
from typing import TypeVar
import re

from pydantic import BaseModel
from pydantic import HttpUrl
from pydantic import validator

_IC = TypeVar("_IC", bound="FeedItemCategory")
_G = TypeVar("_G", bound="Game")


# --- ENUMS ---


@unique
class FeedItemCategory(IntEnum):
    NOTICES = 1
    EVENTS = 2
    INFO = 3

    @classmethod
    def from_str(cls: Type[_IC], category_str: str) -> _IC:
        try:
            return cls[category_str.upper()]
        except KeyError as err:
            raise ValueError('Unknown category "{}"!'.format(category_str)) from err


@unique
class Game(IntEnum):
    # 3 = unused, 5 = hoyolab, 7 = unused
    HONKAI = 1
    GENSHIN = 2
    THEMIS = 4
    STARRAIL = 6
    ZENLESS = 8
    NEXUS = 9

    @classmethod
    def from_str(cls: Type[_G], game_str: str) -> _G:
        try:
            return cls[game_str.upper()]
        except KeyError as err:
            raise ValueError('Unknown game "{}"!'.format(game_str)) from err


@unique
class FeedType(str, Enum):
    JSON = "json"
    ATOM = "atom"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


@unique
class Language(str, Enum):
    GERMAN = "de-de"
    ENGLISH = "en-us"
    SPANISH = "es-es"
    FRENCH = "fr-fr"
    INDONESIAN = "id-id"
    ITALIAN = "it-it"
    JAPANESE = "ja-jp"
    KOREAN = "ko-kr"
    PORTUGUESE = "pt-pt"
    RUSSIAN = "ru-ru"
    THAI = "th-th"
    TURKISH = "tr-tr"
    VIETNAMESE = "vi-vn"
    CHINESE_CN = "zh-cn"
    CHINESE_TW = "zh-tw"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


# --- PYDANTIC MODELS ---


class MyBaseModel(BaseModel):
    # https://docs.pydantic.dev/usage/model_config/#options
    class Config:
        extra = "forbid"
        anystr_strip_whitespace = True
        min_anystr_length = 1


class FeedMeta(MyBaseModel):
    game: Game
    category_size: int = 5
    categories: List[FeedItemCategory] = [c for c in FeedItemCategory]
    language: Language = Language.ENGLISH
    title: Optional[str] = None
    icon: Optional[HttpUrl] = None
    home_page_url: Optional[HttpUrl] = None


class FeedItem(MyBaseModel):
    id: int
    title: str
    author: str
    content: str
    category: FeedItemCategory
    published: datetime
    updated: Optional[datetime] = None
    image: Optional[HttpUrl] = None
    summary: Optional[str] = None
    game: Optional[Game] = None

    # --- normalization helpers for MonitorRSS rendering ---
    @staticmethod
    def _normalize_text(text: Optional[str]) -> Optional[str]:
        if text is None:
            return None

        # Unescape common HTML entities
        text = (text
                .replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">"))

        # <br> variants → newline
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)

        # Paragraphs: </p><p> → blank line; drop remaining <p> tags
        text = re.sub(r"(?i)</p>\s*<p>", "\n\n", text)
        text = re.sub(r"(?i)</?p[^>]*>", "", text)

        # Lists: <li>…</li>, drop <ul>/<ol>
        text = re.sub(r"(?i)<li[^>]*>\s*", "• ", text)
        text = re.sub(r"(?i)</li>\s*", "\n", text)
        text = re.sub(r"(?i)</?(ul|ol)[^>]*>", "", text)

        # Strip any remaining tags
        text = re.sub(r"<[^>]+>", "", text)

        # Hoyolab glyph bullets → newline bullets
        text = text.replace("▌", "\n• ").replace("■", "\n• ")

        # INSERT MISSING SPACE after punctuation when next char is a letter/number
        # e.g., "Destiny.After" → "Destiny. After"
        text = re.sub(r"([.!?;:])(?!\s)(?=[A-Za-z0-9])", r"\1 ", text)

        # Normalize whitespace: collapse 3+ newlines to 2; collapse 2+ spaces to 1
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # Tidy bullets: avoid lines that start with "•" immediately followed by punctuation
        text = re.sub(r"\n•\s*([.;,:])", r"\n\1", text)

        return text.strip()
    @validator("content", pre=True)
    def _content_to_newlines(cls, v: Optional[str]) -> Optional[str]:
        return cls._normalize_text(v)

    @validator("summary", pre=True)
    def _summary_to_newlines(cls, v: Optional[str]) -> Optional[str]:
        return cls._normalize_text(v)

class FeedItemMeta(MyBaseModel):
    id: int
    last_modified: datetime


class FeedFileConfig(MyBaseModel):
    feed_type: FeedType
    path: Path


class FeedFileWriterConfig(FeedFileConfig):
    url: Optional[HttpUrl] = None


class FeedConfig(MyBaseModel):
    feed_meta: FeedMeta
    writer_configs: List[FeedFileWriterConfig]
    loader_config: Optional[FeedFileConfig] = None
