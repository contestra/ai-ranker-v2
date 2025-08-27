"""
Pre-built Ambient Blocks for each country
These are distilled from Exa harvesting - NOT live snippets
Updated quarterly or when adding new countries
"""

from datetime import datetime
from typing import Dict, List

class ALSTemplates:
    """
    Static Ambient Blocks of civic signals for each country.
    These are carefully curated, neutral, and minimal.
    """
    
    # Last updated: August 12, 2025
    # Next refresh: November 2025
    
    TEMPLATES = {
        'DE': {
            'timezone': 'Europe/Berlin',
            'utc_offset': {'summer': '+02:00', 'winter': '+01:00'},
            'civic_terms': [
                'Reisepass beantragen',
                'Personalausweis verlängern',
                'Führerschein umtauschen',
                'Anmeldung Bürgeramt',
                'ELSTER Steuererklärung',
                'Kindergeld Antrag',
                'Aufenthaltstitel verlängern'
            ],
            'agencies': ['bund.de', 'Bürgeramt', 'Finanzamt', 'Kfz-Zulassungsstelle'],
            'formatting': {
                'postal': ['10115 Berlin', '80331 München', '20095 Hamburg'],
                'phone': '+49 30 xxx xx xx',
                'currency': ['12,90 €', '89,00 €', '234,50 €'],
                'date': 'DD.MM.YYYY'
            },
            'weather_cities': ['Berlin', 'München', 'Hamburg', 'Frankfurt']
        },
        
        'CH': {
            'timezone': 'Europe/Zurich',
            'utc_offset': {'summer': '+02:00', 'winter': '+01:00'},
            'civic_terms': [
                'Führerausweis / permis de conduire',
                'AHV / AVS Nummer',
                'Niederlassungsbewilligung',
                'Steuererklärung einreichen',
                'ID verlängern',
                'e-Umzug melden',
                'Einwohnerkontrolle'
            ],
            'agencies': ['ch.ch', 'admin.ch', 'Gemeinde', 'Kanton', 'Einwohnerkontrolle'],
            'formatting': {
                'postal': ['8001 Zürich', '3011 Bern', '1200 Genève'],
                'phone': '+41 44 xxx xx xx',
                'currency': ['CHF 12.90', 'CHF 89.00', 'CHF 234.50']
            },
            'weather_cities': ['Zürich', 'Bern', 'Genève', 'Basel']
        },
        
        'US': {
            'timezone_samples': ['America/New_York', 'America/Los_Angeles', 'America/Chicago', 'America/Denver'],
            'utc_offset': {'ET': '-05:00', 'CT': '-06:00', 'MT': '-07:00', 'PT': '-08:00'},
            'civic_terms': [
                'driver license renewal DMV',
                'passport application',
                'Social Security card',
                'voter registration',
                'IRS tax return',
                'REAL ID appointment',
                'vehicle registration'
            ],
            'agencies': ['state DMV', 'state DOT', 'IRS', 'SSA', 'USPS'],
            'formatting': {
                'postal': ['New York, NY 10001', 'Los Angeles, CA 90001', 'Chicago, IL 60601'],
                'phone': '(212) xxx-xxxx',
                'phone_intl': '+1 212 xxx xxxx',
                'currency': ['$12.90', '$89.00', '$234.50']
            },
            'weather_cities': ['New York', 'Los Angeles', 'Chicago', 'Houston']
        },
        
        'GB': {
            'timezone': 'Europe/London',
            'utc_offset': {'summer': '+01:00', 'winter': '+00:00'},
            'civic_terms': [
                'driving licence renewal',
                'passport renewal',
                'council tax payment',
                'GP registration NHS',
                'National Insurance number',
                'Universal Credit claim',
                'MOT test booking'
            ],
            'agencies': ['GOV.UK', 'DVLA', 'HMRC', 'NHS', 'DWP'],
            'formatting': {
                'postal': ['London SW1A 1AA', 'Manchester M1 1AE', 'Birmingham B1 1BB'],
                'phone': '+44 20 xxxx xxxx',
                'currency': ['£12.90', '£89.00', '£234.50'],
                'date': 'DD/MM/YYYY'
            },
            'weather_cities': ['London', 'Manchester', 'Birmingham', 'Edinburgh']
        },
        
        'AE': {
            'timezone': 'Asia/Dubai',
            'utc_offset': {'year_round': '+04:00'},
            'civic_terms': [
                'Emirates ID renewal',
                'residence visa status',
                'traffic fines payment',
                'tenancy registration',
                'trade license renewal',
                'medical fitness test',
                'driving license renewal'
            ],
            'agencies': ['u.ae', 'ICP', 'MOI', 'MOHRE', 'DED'],
            'formatting': {
                'postal': ['Dubai P.O. Box', 'Abu Dhabi P.O. Box', 'Sharjah P.O. Box'],
                'phone': '+971 4 xxx xxxx',
                'currency': ['AED 49.00', 'AED 325.00', 'AED 890.00']
            },
            'weather_cities': ['Dubai', 'Abu Dhabi', 'Sharjah', 'Ajman']
        },
        
        'SG': {
            'timezone': 'Asia/Singapore',
            'utc_offset': {'year_round': '+08:00'},
            'civic_terms': [
                'passport appointment online',
                'Singpass login',
                'CPF statement',
                'FIN card renewal',
                'HDB BTO application',
                'MOM work pass status',
                'road tax renewal'
            ],
            'agencies': ['ICA', 'gov.sg', 'CPF', 'HDB', 'LTA', 'MOM'],
            'formatting': {
                'postal': ['Singapore 049315', 'Singapore 018956', 'Singapore 608526'],
                'phone': '+65 6xxx xxxx',
                'currency': ['S$12.90', 'S$89.00', 'S$234.50']
            },
            'weather_cities': ['Singapore', 'Jurong', 'Tampines', 'Woodlands']
        },
        
        'IT': {
            'timezone': 'Europe/Rome',
            'utc_offset': {'summer': '+02:00', 'winter': '+01:00'},
            'civic_terms': [
                "Carta d'identità elettronica CIE",
                'passaporto rinnovo online',
                'codice fiscale richiesta',
                'patente rinnovo',
                'SPID attivazione',
                'ISEE compilazione',
                'certificato residenza'
            ],
            'agencies': ['gov.it', 'INPS', 'Agenzia delle Entrate', 'Comune', 'Poste Italiane'],
            'formatting': {
                'postal': ['00100 Roma', '20100 Milano', '80100 Napoli'],
                'phone': '+39 06 xxxx xxxx',
                'currency': ['12,90 €', '89,00 €', '234,50 €'],
                'date': 'DD/MM/YYYY'
            },
            'weather_cities': ['Roma', 'Milano', 'Napoli', 'Torino']
        },
        
        'FR': {
            'timezone': 'Europe/Paris',
            'utc_offset': {'summer': '+02:00', 'winter': '+01:00'},
            'civic_terms': [
                "Carte d'identité renouvellement",
                'passeport demande en ligne',
                'permis de conduire',
                'Carte Vitale demande',
                'FranceConnect connexion',
                'impôts déclaration',
                'acte de naissance'
            ],
            'agencies': ['service-public.fr', 'ameli.fr', 'ants.gouv.fr', 'impots.gouv.fr', 'Mairie'],
            'formatting': {
                'postal': ['75001 Paris', '69001 Lyon', '13001 Marseille'],
                'phone': '+33 1 xx xx xx xx',
                'currency': ['12,90 €', '89,00 €', '234,50 €'],
                'date': 'DD/MM/YYYY'
            },
            'weather_cities': ['Paris', 'Lyon', 'Marseille', 'Toulouse']
        }
    }
    
    @classmethod
    def get_template(cls, country: str) -> Dict:
        """Get the Ambient Block for a specific country."""
        return cls.TEMPLATES.get(country, {})
    
    @classmethod
    def list_countries(cls) -> List[str]:
        """List all supported countries."""
        return list(cls.TEMPLATES.keys())
    
    @classmethod
    def get_last_update(cls) -> str:
        """Get the last update date for templates."""
        return "2025-08-12"
    
    @classmethod
    def needs_refresh(cls) -> bool:
        """Check if Ambient Blocks are due for refresh (quarterly)."""
        from datetime import datetime, timedelta
        last_update = datetime.strptime(cls.get_last_update(), "%Y-%m-%d")
        three_months_ago = datetime.now() - timedelta(days=90)
        return last_update < three_months_ago