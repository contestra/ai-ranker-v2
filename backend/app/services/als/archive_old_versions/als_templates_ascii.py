# -*- coding: utf-8 -*-
"""
ASCII-safe ALS templates for Windows compatibility.
Uses only ASCII characters to avoid encoding issues.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import random

MAX_CHARS = 350

@dataclass
class CountryTemplate:
    code: str
    country: str
    timezone: Optional[str] = None
    timezone_samples: Optional[List[str]] = None
    utc_offsets: Dict[str, str] = field(default_factory=dict)
    civic_keyword: str = ""
    phrases: List[str] = field(default_factory=list)
    formatting_example: str = ""
    weather_stub_local: str = ""
    notes: List[str] = field(default_factory=list)

class ALSTemplates:
    """
    ASCII-safe templates - no special characters.
    """

    TEMPLATES: Dict[str, CountryTemplate] = {
        # Germany - ASCII-safe version
        "DE": CountryTemplate(
            code="DE",
            country="Germany",
            timezone="Europe/Berlin",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Buergeramt",  # ASCII version of Bürgeramt
            phrases=[
                "Reisepass beantragen Termin",
                "Fuehrerschein umtauschen",  # ASCII version of Führerschein
                "Anmeldung Buergeramt",
                "ELSTER Steuererklaerung",  # ASCII version of Steuererklärung
                "Kindergeld Antrag",
                "Aufenthaltstitel verlaengern",  # ASCII version of verlängern
            ],
            formatting_example="10115 Berlin - +49 30 xxx xx xx - 12,90 EUR",  # Using - and EUR
            weather_stub_local="Nationaler Wetterdienst: Berlin",
            notes=[
                "5-digit postal codes; comma decimals (12,90 EUR); +49 phone",
                "Orthography: Strasse (ss) not sz",
                "Date: DD.MM.YYYY",
            ],
        ),
        # Switzerland - ASCII-safe
        "CH": CountryTemplate(
            code="CH",
            country="Switzerland",
            timezone="Europe/Zurich",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Bundesverwaltung",
            phrases=[
                "Fuehrerausweis verlaengern / renouveler permis",
                "AHV / AVS Nummer",
                "e-Umzug melden",
                "Steuererklaerung einreichen",
                "ID verlaengern",
                "Einwohnerkontrolle",
            ],
            formatting_example="8001 Zuerich - +41 44 xxx xx xx - CHF 12.90",  # ASCII Zürich
            weather_stub_local="Nationaler Wetterdienst: Zuerich",
            notes=[
                "4-digit postal codes; CHF 12.90; +41 phone",
                "Orthography: Strasse (ss)",
                "Multilingual: DE/FR/IT names vary",
            ],
        ),
        # United States
        "US": CountryTemplate(
            code="US",
            country="United States",
            timezone_samples=["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
            utc_offsets={"ET": "-05:00", "CT": "-06:00", "MT": "-07:00", "PT": "-08:00"},
            civic_keyword="state DMV",
            phrases=[
                "driver license renewal appointment",
                "passport application online",
                "Social Security card replacement",
                "voter registration",
                "IRS tax return filing",
                "REAL ID appointment",
                "vehicle registration",
            ],
            formatting_example="New York, NY 10001 - (212) xxx-xxxx - $12.90",
            weather_stub_local="National Weather Service: New York",
            notes=[
                "5-digit ZIP; dollar with period decimals ($12.90); (xxx) xxx-xxxx phone",
                "Date: MM/DD/YYYY",
            ],
        ),
        # United Kingdom
        "GB": CountryTemplate(
            code="GB",
            country="United Kingdom",
            timezone="Europe/London",
            utc_offsets={"summer": "+01:00", "winter": "+00:00"},
            civic_keyword="GOV.UK",
            phrases=[
                "driving licence renewal",
                "passport application",
                "National Insurance number",
                "Council Tax payment",
                "Universal Credit claim",
                "MOT test booking",
                "electoral register",
            ],
            formatting_example="London SW1A 1AA - 020 xxxx xxxx - GBP 12.90",  # Using GBP
            weather_stub_local="Met Office forecast: London",
            notes=[
                "Alphanumeric postcodes; GBP with period decimals; 020 phone",
                "Spelling: licence (not license)",
                "Date: DD/MM/YYYY",
            ],
        ),
        # France
        "FR": CountryTemplate(
            code="FR",
            country="France",
            timezone="Europe/Paris",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Service Public",
            phrases=[
                "Carte d'identite renouvellement",  # ASCII version
                "passeport demande en ligne",
                "permis de conduire",
                "Carte Vitale demande",
                "FranceConnect connexion",
                "impots declaration",  # ASCII version of impôts
                "acte de naissance",
            ],
            formatting_example="75001 Paris - +33 1 xx xx xx xx - 12,90 EUR",
            weather_stub_local="service meteo national : Paris",  # ASCII météo
            notes=[
                "5-digit postal; EUR with comma decimals; +33 phone",
                "Date: DD/MM/YYYY",
            ],
        ),
    }

    @classmethod
    def supported_countries(cls) -> List[str]:
        return list(cls.TEMPLATES.keys())

    @classmethod
    def render_block(
        cls,
        code: str,
        now: Optional[datetime] = None,
        tz_override: Optional[str] = None,
        phrase_idx: Optional[int] = None,
        include_weather: bool = True,
        header_language: Optional[str] = None,
    ) -> str:
        """
        Render an ASCII-safe ALS block for a given country code.
        """
        code = code.upper()
        if code not in cls.TEMPLATES:
            raise KeyError(f"Unsupported country code: {code}")

        tpl = cls.TEMPLATES[code]

        # Timestamp + offset
        if tz_override:
            tz = ZoneInfo(tz_override)
        elif tpl.timezone:
            tz = ZoneInfo(tpl.timezone)
        elif tpl.timezone_samples:
            tz = ZoneInfo(random.choice(tpl.timezone_samples))
        else:
            tz = ZoneInfo("UTC")

        now = now or datetime.now(tz)
        stamp = now.strftime("%Y-%m-%d %H:%M")
        offset_seconds = tz.utcoffset(now)
        total_minutes = int(offset_seconds.total_seconds() // 60) if offset_seconds else 0
        sign = "+" if total_minutes >= 0 else "-"
        hh = abs(total_minutes) // 60
        mm = abs(total_minutes) % 60
        offset_str = f"{sign}{hh:02d}:{mm:02d}"

        # Phrase selection
        if not tpl.phrases:
            raise ValueError(f"No civic phrases configured for {code}")
        idx = (phrase_idx % len(tpl.phrases)) if isinstance(phrase_idx, int) else 0
        phrase = tpl.phrases[idx]

        # ASCII-safe headers
        header = {
            "DE": "Lokaler Kontext (nur zur Lokalisierung; nicht zitieren):",
            "CH": "Lokaler Kontext (nur zur Lokalisierung; nicht zitieren):",
            "IT": "Contesto locale (solo per la localizzazione; non citare):",
            "FR": "Contexte local (uniquement pour la localisation ; ne pas citer) :",
            "GB": "Ambient Context (localisation only; do not cite):",
            "US": "Ambient Context (localization only; do not cite):",
            "AE": "Local context (localization only; do not cite):",  # ASCII version
            "SG": "Ambient Context (localization only; do not cite):",
        }.get(code, "Ambient Context (localization only; do not cite):")

        if header_language:
            header = header_language

        # Use simple dash instead of special characters
        lines = [
            f"{header}",
            f"- {stamp}, {offset_str}",
            f'- {tpl.civic_keyword} - "{phrase}"',
            f"- {tpl.formatting_example}",
        ]
        if include_weather and tpl.weather_stub_local:
            lines.append(f"- {tpl.weather_stub_local}")

        block = "\n".join(lines)

        if len(block) > MAX_CHARS:
            # Try without weather
            if include_weather and tpl.weather_stub_local:
                return cls.render_block(
                    code=code,
                    now=now,
                    tz_override=tz_override,
                    phrase_idx=phrase_idx,
                    include_weather=False,
                    header_language=header_language,
                )
            raise ValueError(f"ALS block for {code} exceeds {MAX_CHARS} chars even without weather")

        return block