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
    content: str  # keep original HTML here (unchanged)
    category: FeedItemCategory
    published: datetime
    updated: Optional[datetime] = None
    image: Optional[HttpUrl] = None
    summary: Optional[str] = None
    game: Optional[Game] = None

    # -------- Plain-text helper (does NOT mutate content) --------
    @staticmethod
    def _html_to_plaintext(text: Optional[str]) -> Optional[str]:
        """
        Convert HTML to a readable plain-text snapshot for consumers like MonitorRSS,
        without altering the original HTML stored in `content`.
        - Convert <br> to newlines
        - Convert paragraphs and list items into line breaks/bullets
        - Drop most tags but keep link text with URL in parentheses, and keep
          image alt/src as a short marker.
        """
        if text is None:
            return None

        # Normalise NBSP and basic entities first
        txt = (text
               .replace("&nbsp;", " ")
               .replace("&amp;", "&")
               .replace("&lt;", "<")
               .replace("&gt;", ">"))

        # <br> variants → newline
        txt = re.sub(r"(?is)<br\s*/?>", "\n", txt)

        # Paragraphs: close tags -> blank line; remove opening <p ...>
        txt = re.sub(r"(?is)</p\s*>", "\n\n", txt)
        txt = re.sub(r"(?is)<p[^>]*>", "", txt)

        # Lists: <li>…</li> → bullets; drop list containers
        txt = re.sub(r"(?is)<li[^>]*>\s*", "• ", txt)
        txt = re.sub(r"(?is)</li\s*>", "\n", txt)
        txt = re.sub(r"(?is)</?(ul|ol)[^>]*>", "", txt)

        # Links: keep anchor text + URL in parentheses
        def _a_sub(m):
            href = m.group(1) or ""
            inner = m.group(2) or ""
            inner = re.sub(r"\s+", " ", inner).strip()
            href = href.strip()
            if inner and href:
                return f"{inner} ({href})"
            return inner or href

        txt = re.sub(r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a\s*>', _a_sub, txt)

        # Images: show a lightweight marker with alt/src
        def _img_sub(m):
            alt = (m.group(1) or "").strip()
            src = (m.group(2) or "").strip()
            if alt and src:
                return f"[img: {alt} — {src}]"
            if src:
                return f"[img: {src}]"
            return "[img]"

        txt = re.sub(r'(?is)<img[^>]*alt="([^"]*)"[^>]*src="([^"]+)"[^>]*>', _img_sub, txt)
        txt = re.sub(r'(?is)<img[^>]*src="([^"]+)"[^>]*>', lambda m: f"[img: {m.group(1).strip()}]", txt)

        # Strip any remaining tags
        txt = re.sub(r"(?is)<[^>]+>", "", txt)

        # Tidy whitespace
        txt = re.sub(r"\r\n|\r", "\n", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        txt = re.sub(r"[ \t]{2,}", " ", txt)

        return txt.strip()

    # If a summary comes from upstream HTML, normalize it to a plain-text snippet.
    @validator("summary", pre=True)
    def _summary_to_plaintext(cls, v: Optional[str]) -> Optional[str]:
        return cls._html_to_plaintext(v)

    # Convenience: produce a plain-text snapshot of the HTML content
    def content_plaintext(self) -> str:
        return self._html_to_plaintext(self.content) or ""

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
