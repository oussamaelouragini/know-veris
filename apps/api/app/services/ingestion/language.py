"""Language detection (FR / EN / AR) and Postgres FTS config mapping.

The three supported languages match the project scope. Detection drives two
things: the language stored on documents/chunks, and which Postgres text-search
configuration builds `content_tsv` for keyword search. All three configs
(french, english, arabic) exist in PG16 — verified in Week 0 — so no language
falls back to `simple` in practice.
"""

from functools import lru_cache

from lingua import Language, LanguageDetectorBuilder

_ISO = {
    Language.FRENCH: "fr",
    Language.ENGLISH: "en",
    Language.ARABIC: "ar",
}

# Short ISO code -> Postgres text-search config name.
_FTS_CONFIG = {
    "fr": "french",
    "en": "english",
    "ar": "arabic",
}


@lru_cache(maxsize=1)
def _detector():
    # Restricting to the 3 in-scope languages keeps the model small and the
    # decision sharp (no spurious 100+ language candidates on short text).
    return LanguageDetectorBuilder.from_languages(*_ISO.keys()).build()


def detect_language(text: str) -> str | None:
    """Return 'fr' | 'en' | 'ar', or None if undetermined (e.g. empty text)."""
    if not text or not text.strip():
        return None
    language = _detector().detect_language_of(text)
    return _ISO.get(language) if language else None


def fts_config_for(language: str | None) -> str:
    """Postgres regconfig name for a language code; 'simple' when unknown."""
    return _FTS_CONFIG.get(language or "", "simple")
