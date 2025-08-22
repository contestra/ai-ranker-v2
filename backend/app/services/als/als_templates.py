# -*- coding: utf-8 -*-
"""
Ambient Location Signals (ALS) templates with Unicode-safe encoding.

This version uses explicit Unicode escape sequences to ensure special characters
are preserved regardless of file encoding or system locale.

- Brand-neutral civic signals only (no URLs/news/retailers).
- Rendered as a compact 3–5 bullet block (≤ 350 characters).
- The ALS block MUST be sent as its own message BEFORE the naked user prompt.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import random

MAX_CHARS = 350

# Unicode character map for reference
UNICODE_CHARS = {
    'umlaut_u': '\u00fc',  # ü
    'umlaut_U': '\u00dc',  # Ü
    'umlaut_a': '\u00e4',  # ä
    'umlaut_A': '\u00c4',  # Ä
    'umlaut_o': '\u00f6',  # ö
    'umlaut_O': '\u00d6',  # Ö
    'sharp_s': '\u00df',   # ß
    'euro': '\u20ac',       # €
    'pound': '\u00a3',      # £
    'middot': '\u00b7',     # ·
    'emdash': '\u2014',     # —
    'accent_e': '\u00e9',   # é
    'accent_o': '\u00f4',   # ô
    'arabic_س': '\u0633',   # س
    'arabic_ي': '\u064a',   # ي
    'arabic_ا': '\u0627',   # ا
    'arabic_ق': '\u0642',   # ق
}

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
    Static library of Ambient Blocks with a renderer.
    Unicode-safe version - Last updated: 2025-08-13
    """

    TEMPLATES: Dict[str, CountryTemplate] = {
        # Germany - Using Unicode escapes for special characters
        "DE": CountryTemplate(
            code="DE",
            country="Germany",
            timezone="Europe/Berlin",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Bundesportal",
            phrases=[
                "Reisepass beantragen Termin",
                "F\u00fchrerschein umtauschen",  # Führerschein
                "Anmeldung B\u00fcrgeramt",  # Bürgeramt
                "ELSTER Steuererkl\u00e4rung",  # Steuererklärung
                "Kindergeld Antrag",
                "Aufenthaltstitel verl\u00e4ngern",  # verlängern
            ],
            formatting_example="10115 Berlin \u2022 +49 30 xxx xx xx \u2022 12,90 \u20ac",  # • and €
            weather_stub_local="MwSt. \u2014 allgemeine Ausk\u00fcnfte",  # Now regulatory cue instead of weather
            notes=[
                "5-digit postal codes; comma decimals (12,90 \u20ac); +49 phone",
                "Date: DD.MM.YYYY",
                "Regulatory cue: MwSt. (VAT) instead of weather",
            ],
        ),
        # Switzerland - Using Unicode escapes
        "CH": CountryTemplate(
            code="CH",
            country="Switzerland",
            timezone="Europe/Zurich",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Gemeinde",
            phrases=[
                "F\u00fchrerausweis verl\u00e4ngern",  # Führerausweis verlängern
                "e-Umzug melden",
                "Steuererkl\u00e4rung einreichen",  # Steuererklärung
                "ID verl\u00e4ngern",  # verlängern
                "Einwohnerkontrolle",
                "AHV-Nummer",
            ],
            formatting_example="8001 Z\u00fcrich \u2022 +41 44 xxx xx xx \u2022 CHF 12.90",  # Zürich, •
            weather_stub_local="MWST \u2014 allgemeine Ausk\u00fcnfte",  # Regulatory cue
            notes=[
                "4-digit postal codes; CHF 12.90; +41 phone",
                "Date: DD.MM.YYYY",
                "One language per run (DE/FR/IT)",
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
                "passport application",
                "Social Security card",
                "voter registration",
                "IRS tax return",
                "REAL ID appointment",
                "vehicle registration",
            ],
            formatting_example="New York, NY 10001 \u2022 (212) xxx-xxxx \u2022 $12.90",  # •
            weather_stub_local="state sales tax \u2014 general info",  # Regulatory cue
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
                "passport renewal",
                "National Insurance number",
                "council tax payment",
                "Universal Credit claim",
                "NHS GP registration",
                "MOT test booking",
            ],
            formatting_example="London SW1A 1AA \u2022 +44 20 xxxx xxxx \u2022 \u00a312.90",  # • and £
            weather_stub_local="VAT \u2014 general info",  # Regulatory cue
            notes=[
                "Alphanumeric postcodes; \u00a3 with period decimals; +44 phone",  # £
                "Spelling: licence (not license), localisation",
                "Date: DD/MM/YYYY",
            ],
        ),
        # United Arab Emirates
        "AE": CountryTemplate(
            code="AE",
            country="United Arab Emirates",
            timezone="Asia/Dubai",
            utc_offsets={"year_round": "+04:00"},
            civic_keyword="\u0627\u0644\u0647\u0648\u064a\u0629 \u0648\u0627\u0644\u062c\u0646\u0633\u064a\u0629 (ICP)",  # الهوية والجنسية
            phrases=[
                "\u062a\u062c\u062f\u064a\u062f \u0628\u0637\u0627\u0642\u0629 \u0627\u0644\u0647\u0648\u064a\u0629 \u0627\u0644\u0625\u0645\u0627\u0631\u0627\u062a\u064a\u0629",  # تجديد بطاقة الهوية الإماراتية
                "\u062d\u0627\u0644\u0629 \u062a\u0623\u0634\u064a\u0631\u0629 \u0627\u0644\u0625\u0642\u0627\u0645\u0629",  # حالة تأشيرة الإقامة
                "\u0633\u062f\u0627\u062f \u0627\u0644\u0645\u062e\u0627\u0644\u0641\u0627\u062a \u0627\u0644\u0645\u0631\u0648\u0631\u064a\u0629",  # سداد المخالفات المرورية
                "\u062a\u0633\u062c\u064a\u0644 \u0639\u0642\u062f \u0627\u0644\u0625\u064a\u062c\u0627\u0631",  # تسجيل عقد الإيجار
                "\u062a\u062c\u062f\u064a\u062f \u0627\u0644\u0631\u062e\u0635\u0629 \u0627\u0644\u062a\u062c\u0627\u0631\u064a\u0629",  # تجديد الرخصة التجارية
                "\u0641\u062d\u0635 \u0627\u0644\u0644\u064a\u0627\u0642\u0629 \u0627\u0644\u0637\u0628\u064a\u0629",  # فحص اللياقة الطبية
                "\u062a\u062c\u062f\u064a\u062f \u0631\u062e\u0635\u0629 \u0627\u0644\u0642\u064a\u0627\u062f\u0629",  # تجديد رخصة القيادة
            ],
            formatting_example="\u062f\u0628\u064a \u0635.\u0628. \u2022 +971 4 xxx xxxx \u2022 49.00 \u062f.\u0625",  # دبي ص.ب. • د.إ
            weather_stub_local="\u0636\u0631\u064a\u0628\u0629 \u0627\u0644\u0642\u064a\u0645\u0629 \u0627\u0644\u0645\u0636\u0627\u0641\u0629 \u2014 \u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0639\u0627\u0645\u0629",  # ضريبة القيمة المضافة — معلومات عامة
            notes=[
                "No postal codes; AED currency; +971 phone",
                "Working week: Sunday-Thursday",
                "Date: DD/MM/YYYY",
                "Arabic civic phrases with English header",
            ],
        ),
        # Singapore
        "SG": CountryTemplate(
            code="SG",
            country="Singapore",
            timezone="Asia/Singapore",
            utc_offsets={"year_round": "+08:00"},
            civic_keyword="ICA",
            phrases=[
                "passport appointment online",
                "Singpass login",
                "CPF statement",
                "HDB BTO application",
                "FIN card renewal",
                "MOM work pass status",
                "road tax renewal",
            ],
            formatting_example="Singapore 049315 \u2022 +65 6xxx xxxx \u2022 S$12.90",  # •
            weather_stub_local="GST \u2014 general info",  # Regulatory cue
            notes=[
                "6-digit postal codes; S$ currency; +65 phone",
                "Date: DD MMM YYYY or DD/MM/YYYY",
            ],
        ),
        # Italy
        "IT": CountryTemplate(
            code="IT",
            country="Italy",
            timezone="Europe/Rome",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Comune",
            phrases=[
                "carta d'identit\u00e0 rinnovo",  # identità
                "patente rinnovo",
                "codice fiscale richiesta",
                "SPID attivazione",
                "ISEE compilazione",
                "certificato di residenza",
                "carta d'identit\u00e0 elettronica",
            ],
            formatting_example="00100 Roma \u2022 +39 06 xxxx xxxx \u2022 12,90 \u20ac",  # • and €
            weather_stub_local="IVA \u2014 informazioni generali",  # Regulatory cue
            notes=[
                "5-digit CAP codes; \u20ac with comma decimals; +39 phone",  # €
                "Date: DD/MM/YYYY",
            ],
        ),
        # France
        "FR": CountryTemplate(
            code="FR",
            country="France",
            timezone="Europe/Paris",
            utc_offsets={"summer": "+02:00", "winter": "+01:00"},
            civic_keyword="Portail national",
            phrases=[
                "Carte d'identit\u00e9 renouvellement",  # identité
                "passeport demande",
                "permis de conduire",
                "Carte Vitale demande",
                "FranceConnect connexion",
                "imp\u00f4ts d\u00e9claration",  # impôts déclaration
                "acte de naissance",
            ],
            formatting_example="75001 Paris \u2022 +33 1 xx xx xx xx \u2022 12,90 \u20ac",  # • and €
            weather_stub_local="TVA \u2014 informations g\u00e9n\u00e9rales",  # TVA — informations générales
            notes=[
                "5-digit postal; \u20ac with comma decimals; +33 phone",  # €
                "Date: DD/MM/YYYY",
            ],
        ),
    }

    @classmethod
    def validate_encoding(cls) -> bool:
        """
        Validate that all special characters are properly encoded.
        Returns True if all checks pass, raises AssertionError otherwise.
        """
        # Check German template
        de = cls.TEMPLATES["DE"]
        assert '\u00fc' in de.civic_keyword, f"Missing ü in Bürgeramt: {repr(de.civic_keyword)}"
        assert '\u20ac' in de.formatting_example, f"Missing € in formatting: {repr(de.formatting_example)}"
        assert '\u00b7' in de.formatting_example, f"Missing · in formatting: {repr(de.formatting_example)}"
        
        # Check Swiss template
        ch = cls.TEMPLATES["CH"]
        assert '\u00fc' in ch.phrases[0], f"Missing ü in Führerausweis: {repr(ch.phrases[0])}"
        assert '\u00fc' in ch.formatting_example, f"Missing ü in Zürich: {repr(ch.formatting_example)}"
        
        # Check UK template
        gb = cls.TEMPLATES["GB"]
        assert '\u00a3' in gb.formatting_example, f"Missing £ in formatting: {repr(gb.formatting_example)}"
        
        # Check French template
        fr = cls.TEMPLATES["FR"]
        assert '\u00e9' in fr.phrases[0], f"Missing é in identité: {repr(fr.phrases[0])}"
        assert '\u00f4' in fr.phrases[5], f"Missing ô in impôts: {repr(fr.phrases[5])}"
        
        print("OK: All encoding validations passed")
        return True

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
        Render a leak-resistant ALS block for a given country code.
        - Chooses timestamp and UTC offset using the country tz (or a sample tz).
        - Picks a civic phrase (deterministic if phrase_idx provided).
        - Returns a 3–5 line block ≤ 350 chars; raises ValueError if it cannot fit.
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
        # Format date based on country conventions
        date_formats = {
            "US": "%m/%d/%Y",  # MM/DD/YYYY
            "GB": "%d/%m/%Y",  # DD/MM/YYYY
            "DE": "%d.%m.%Y",  # DD.MM.YYYY
            "CH": "%d.%m.%Y",  # DD.MM.YYYY
            "FR": "%d/%m/%Y",  # DD/MM/YYYY
            "IT": "%d/%m/%Y",  # DD/MM/YYYY
            "AE": "%d/%m/%Y",  # DD/MM/YYYY
            "SG": "%d %b %Y",  # DD MMM YYYY
        }
        date_format = date_formats.get(code, "%Y-%m-%d")
        stamp = now.strftime(f"{date_format} %H:%M")
        offset_seconds = tz.utcoffset(now)
        # offset like UTC+HH:MM or UTC-HH:MM
        total_minutes = int(offset_seconds.total_seconds() // 60) if offset_seconds else 0
        sign = "+" if total_minutes >= 0 else "-"
        hh = abs(total_minutes) // 60
        mm = abs(total_minutes) % 60
        offset_str = f"UTC{sign}{hh:02d}:{mm:02d}"

        # Phrase selection
        if not tpl.phrases:
            raise ValueError(f"No civic phrases configured for {code}")
        idx = (phrase_idx % len(tpl.phrases)) if isinstance(phrase_idx, int) else 0
        phrase = tpl.phrases[idx]

        # Use English headers for consistent English output
        # GB uses 'localisation' (British spelling), others use 'localization' (American spelling)
        header = {
            "GB": "Ambient Context (localisation only; do not cite):",
        }.get(code, "Ambient Context (localization only; do not cite):")

        if header_language:
            header = header_language

        # Use em-dash for better Unicode compatibility
        emdash = "\u2014"  # —
        
        # Build the block with regulatory cue instead of weather
        # weather_stub_local now contains the regulatory cue (e.g., "VAT — general info")
        lines = [
            f"{header}",
            f"- {stamp}, {offset_str}",
            f"- {tpl.civic_keyword} {emdash} \"{phrase}\"",
            f"- {tpl.formatting_example}",
            f"- {tpl.weather_stub_local}",  # This is now the regulatory cue
        ]

        block = "\n".join(lines)

        if len(block) > MAX_CHARS:
            # Try without regulatory cue (last line)
            lines_without_reg = lines[:-1]
            block = "\n".join(lines_without_reg)
            if len(block) > MAX_CHARS:
                raise ValueError(f"ALS block for {code} exceeds {MAX_CHARS} chars even without regulatory cue")

        return block


# Run validation when module is imported
if __name__ == "__main__":
    ALSTemplates.validate_encoding()
    
    # Test rendering
    print("\nTest rendering for DE:")
    de_block = ALSTemplates.render_block("DE", phrase_idx=0, include_weather=True)
    print(de_block)
    print(f"Length: {len(de_block)} chars")
    
    print("\nTest rendering for CH:")
    ch_block = ALSTemplates.render_block("CH", phrase_idx=0, include_weather=True)
    print(ch_block)
    print(f"Length: {len(ch_block)} chars")