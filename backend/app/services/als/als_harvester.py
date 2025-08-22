"""
ALS Harvester - Uses Exa to bootstrap/refresh civic terms
Run quarterly or when adding new countries
"""

import asyncio
import httpx
import json
from typing import Dict, List, Set
from datetime import datetime
from app.config import settings

class ALSHarvester:
    """
    Harvests authentic civic terms and patterns using Exa.
    This runs OFFLINE to build/refresh templates, NOT during testing.
    """
    
    # Government/civic domains ONLY - no commercial sites
    CIVIC_DOMAINS = {
        'DE': [
            'bund.de', 'bundesregierung.de', 'bundestag.de',
            'arbeitsagentur.de', 'deutsche-rentenversicherung.de',
            'elster.de', 'bamf.de', 'dwd.de'  # German weather service
        ],
        'CH': [
            'admin.ch', 'ch.ch', 'gov.swiss',
            'ahv-iv.ch', 'sbb.ch',  # Swiss trains are civic
            'meteoschweiz.admin.ch'  # Swiss weather
        ],
        'US': [
            'usa.gov', 'irs.gov', 'ssa.gov', 'state.gov',
            'dmv.gov', 'usps.com',  # USPS is quasi-government
            'weather.gov', 'noaa.gov'
        ],
        'GB': [
            'gov.uk', 'nhs.uk', 'parliament.uk',
            'dvla.gov.uk', 'hmrc.gov.uk',
            'metoffice.gov.uk'  # UK weather
        ],
        'AE': [
            'u.ae', 'government.ae', 'mohap.gov.ae',
            'ica.gov.ae', 'rta.ae', 'dewa.gov.ae',
            'ncm.ae'  # UAE weather
        ],
        'SG': [
            'gov.sg', 'singpass.gov.sg', 'ica.gov.sg',
            'cpf.gov.sg', 'hdb.gov.sg', 'mom.gov.sg',
            'weather.gov.sg'
        ],
        'IT': [
            'gov.it', 'italia.it', 'inps.it',
            'agenziaentrate.gov.it', 'interno.gov.it',
            'salute.gov.it', 'poste.it',  # Poste is quasi-government
            'meteo.it'  # Italian weather
        ],
        'FR': [
            'gouv.fr', 'service-public.fr', 'ameli.fr',
            'ants.gouv.fr', 'impots.gouv.fr',
            'interieur.gouv.fr', 'diplomatie.gouv.fr',
            'meteofrance.fr'  # French weather
        ]
    }
    
    # Search queries to find civic terms (NOT brand-related!)
    HARVEST_QUERIES = {
        'DE': [
            'Personalausweis online beantragen',
            'Führerschein umtauschen Frist',
            'Bürgeramt Termin online',
            'ELSTER Steuererklärung Anleitung'
        ],
        'CH': [
            'Führerausweis erneuern online',
            'AHV Nummer beantragen',
            'Halbtax verlängern SBB',
            'Steuererklärung Kanton Zürich'
        ],
        'US': [
            'renew driver license online DMV',
            'passport application form DS-11',
            'IRS tax return status check',
            'REAL ID requirements deadline'
        ],
        'GB': [
            'renew driving licence online DVLA',
            'council tax payment online',
            'NHS GP registration form',
            'passport renewal UK gov'
        ],
        'AE': [
            'Emirates ID renewal online',
            'Dubai visa status check',
            'Salik tag registration RTA',
            'DEWA bill payment online'
        ],
        'SG': [
            'SingPass setup guide',
            'passport renewal ICA online',
            'CPF contribution statement',
            'HDB BTO application process'
        ],
        'IT': [
            'carta identità elettronica CIE online',
            'passaporto rinnovo appuntamento',
            'SPID registrazione guida',
            'ISEE compilazione online'
        ],
        'FR': [
            'carte identité renouvellement en ligne',
            'passeport demande ANTS',
            'FranceConnect inscription',
            'déclaration impôts en ligne'
        ]
    }
    
    def __init__(self):
        self.exa_api_key = getattr(settings, 'exa_api_key', None)
        
    async def harvest_country(self, country: str) -> Dict:
        """
        Harvest civic terms and patterns for a country.
        Returns structured data to update templates.
        """
        
        if not self.exa_api_key:
            print(f"No Exa API key configured, using existing templates")
            return {}
        
        if country not in self.CIVIC_DOMAINS:
            print(f"Country {country} not configured for harvesting")
            return {}
        
        print(f"\n{'='*60}")
        print(f"Harvesting civic terms for {country}")
        print(f"{'='*60}")
        
        # Collect all civic terms found
        civic_terms = set()
        agencies = set()
        formatting_samples = {
            'postal': set(),
            'phone': set(),
            'currency': set()
        }
        
        # Run searches
        for query in self.HARVEST_QUERIES.get(country, []):
            print(f"\nSearching: {query}")
            
            results = await self._search_civic_sites(query, country)
            
            # Extract terms from results
            extracted = self._extract_civic_data(results, country)
            
            civic_terms.update(extracted['terms'])
            agencies.update(extracted['agencies'])
            formatting_samples['postal'].update(extracted['postal'])
            formatting_samples['phone'].update(extracted['phone'])
            formatting_samples['currency'].update(extracted['currency'])
        
        # Convert sets to lists for JSON serialization
        harvested_data = {
            'country': country,
            'harvest_date': datetime.now().isoformat(),
            'civic_terms': list(civic_terms)[:20],  # Keep top 20
            'agencies': list(agencies)[:10],
            'formatting': {
                'postal': list(formatting_samples['postal'])[:5],
                'phone': list(formatting_samples['phone'])[:3],
                'currency': list(formatting_samples['currency'])[:5]
            }
        }
        
        print(f"\n{'='*60}")
        print(f"Harvested {len(civic_terms)} civic terms for {country}")
        print(f"Top terms: {list(civic_terms)[:5]}")
        print(f"{'='*60}\n")
        
        return harvested_data
    
    async def _search_civic_sites(self, query: str, country: str) -> List[Dict]:
        """Search only civic/government sites using Exa."""
        
        async with httpx.AsyncClient() as client:
            # Use only civic domains for this country
            include_domains = self.CIVIC_DOMAINS.get(country, [])
            
            try:
                response = await client.post(
                    'https://api.exa.ai/search',
                    headers={'x-api-key': self.exa_api_key},
                    json={
                        'query': query,
                        'num_results': 5,
                        'include_domains': include_domains,
                        'use_autoprompt': False,  # Keep query exact
                        'type': 'neural',
                        'contents': {
                            'text': True,
                            'highlights': True
                        }
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get('results', [])
                else:
                    print(f"Exa error: {response.status_code}")
                    return []
                    
            except Exception as e:
                print(f"Search failed: {e}")
                return []
    
    def _extract_civic_data(self, results: List[Dict], country: str) -> Dict:
        """Extract civic terms and patterns from search results."""
        
        extracted = {
            'terms': set(),
            'agencies': set(),
            'postal': set(),
            'phone': set(),
            'currency': set()
        }
        
        for result in results:
            # Get text content
            text = ''
            if result.get('highlights'):
                text = ' '.join(result['highlights'])
            elif result.get('text'):
                text = result['text'][:1000]
            
            if not text:
                continue
            
            # Extract civic terms (2-4 word phrases)
            words = text.split()
            for i in range(len(words) - 1):
                # Look for civic keywords
                if any(civic in words[i].lower() for civic in 
                      ['ausweis', 'führerschein', 'passport', 'license', 
                       'termin', 'antrag', 'application', 'renewal',
                       'steuer', 'tax', 'registration', 'permit']):
                    
                    # Extract 2-4 word phrase
                    phrase = ' '.join(words[i:min(i+4, len(words))])
                    # Clean up
                    phrase = phrase.strip('.,;:!?')[:50]
                    
                    if len(phrase) > 5 and len(phrase) < 50:
                        extracted['terms'].add(phrase)
            
            # Extract domain as agency
            if result.get('url'):
                from urllib.parse import urlparse
                domain = urlparse(result['url']).netloc
                domain = domain.replace('www.', '')
                if domain in self.CIVIC_DOMAINS.get(country, []):
                    extracted['agencies'].add(domain)
            
            # Look for formatting patterns
            extracted.update(self._extract_formatting(text, country))
        
        return extracted
    
    def _extract_formatting(self, text: str, country: str) -> Dict:
        """Extract postal codes, phone numbers, currency from text."""
        
        import re
        
        formatting = {
            'postal': set(),
            'phone': set(),
            'currency': set()
        }
        
        # Country-specific patterns
        if country == 'DE':
            # German postal: 5 digits + city
            postal_pattern = r'\b\d{5}\s+[A-Z][a-zäöüß]+\b'
            phone_pattern = r'\+49\s+\d{2,3}\s+[\d\s]+'
            currency_pattern = r'\d+[,\.]\d{2}\s*€'
            
        elif country == 'CH':
            # Swiss postal: 4 digits + city
            postal_pattern = r'\b\d{4}\s+[A-Z][a-zäöü]+\b'
            phone_pattern = r'\+41\s+\d{2}\s+[\d\s]+'
            currency_pattern = r'CHF\s*\d+[\.]\d{2}'
            
        elif country == 'US':
            # US: City, State ZIP
            postal_pattern = r'[A-Z][a-z]+,\s+[A-Z]{2}\s+\d{5}'
            phone_pattern = r'\(\d{3}\)\s*\d{3}-\d{4}'
            currency_pattern = r'\$\d+\.\d{2}'
            
        elif country == 'GB':
            # UK postcodes
            postal_pattern = r'[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}'
            phone_pattern = r'0\d{2,4}\s+\d{3,4}\s+\d{4}'
            currency_pattern = r'£\d+\.\d{2}'
            
        else:
            return formatting
        
        # Find patterns
        postals = re.findall(postal_pattern, text)
        formatting['postal'].update(postals[:3])
        
        phones = re.findall(phone_pattern, text)
        formatting['phone'].update(phones[:2])
        
        currencies = re.findall(currency_pattern, text)
        formatting['currency'].update(currencies[:3])
        
        return formatting
    
    async def refresh_all_templates(self, save_to_file: str = None):
        """
        Refresh templates for all countries.
        Optionally save to file for manual review.
        """
        
        all_harvested = {}
        
        for country in self.CIVIC_DOMAINS.keys():
            harvested = await self.harvest_country(country)
            if harvested:
                all_harvested[country] = harvested
            
            # Rate limit
            await asyncio.sleep(2)
        
        if save_to_file:
            with open(save_to_file, 'w', encoding='utf-8') as f:
                json.dump(all_harvested, f, indent=2, ensure_ascii=False)
            print(f"\nHarvested data saved to {save_to_file}")
        
        return all_harvested