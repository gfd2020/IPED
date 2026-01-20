# -*- coding: utf-8 -*-
"""
Task to extract Fiscal Data (NFe/CTe) from PDF text processed by IPED.
Runs after ParsingTask.
"""

import re
import json
import os
try:
    from java.lang import System
except ImportError:
    class MockSystem:
        def getProperty(self, key): return ""
    System = MockSystem()

# Import IPED ExtraProperties for metadata keys
try:
    from iped.properties import ExtraProperties
except:
    # Fallback for testing
    class ExtraProperties:
        FISCAL_DOCTYPE = "fiscal:docType"
        FISCAL_REMET_CNPJ = "fiscal:remetCNPJ"
        FISCAL_REMET_NAME = "fiscal:remetName"
        FISCAL_DEST_CNPJ = "fiscal:destCNPJ"
        FISCAL_DEST_NAME = "fiscal:destName"
        FISCAL_VALUE = "fiscal:value"
        FISCAL_ICMS = "fiscal:icms"
        FISCAL_REMET_CITY = "fiscal:remetCity"
        FISCAL_REMET_UF = "fiscal:remetUF"
        FISCAL_DEST_CITY = "fiscal:destCity"
        FISCAL_DEST_UF = "fiscal:destUF"

class FiscalDataExtractionTask:

    def isEnabled(self):
        return True

    def getConfigurables(self):
        return []

    def init(self, configuration):
        pass

    def finish(self):
        pass

    def _parse_cnpj(self, text):
        if not text: return None
        # Remove spaces and non-digits (except . / -)
        clean = re.sub(r'\s+', '', text)
        m = re.search(r'(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})', clean)
        if m: 
            val = m.group(1)
            # Add mask if missing
            if len(val) == 14 and val.isdigit():
                return f"{val[:2]}.{val[2:5]}.{val[5:8]}/{val[8:12]}-{val[12:]}"
            return val
        
        # Second attempt: handle extra spaces between digits even more aggressively
        raw_digits = re.sub(r'[^\d]', '', text)
        if len(raw_digits) == 14:
            return f"{raw_digits[:2]}.{raw_digits[2:5]}.{raw_digits[5:8]}/{raw_digits[8:12]}-{raw_digits[12:]}"
        
        return None

    def process(self, item):
        # Only process generic PDFs or already typed NFe/CTe
        # We rely on ParsingTask having extracted text
        media_type = str(item.getMediaType())
        if not (media_type == "application/pdf" or \
                media_type == "application/x-nfe+pdf" or \
                media_type == "application/x-cte+pdf"):
            return

        text_cache = item.getParsedTextCache()
        if not text_cache:
            return

        text = str(text_cache) # Get the text string
        
        
        # Try to parse as JSON for positional data
        try:
            if text.strip().startswith("[{"):
                
                json_items = json.loads(text)
                # Reconstruct text for regex compatibility
                # Add spaces between items on same line, newlines for different lines (approx)
                text = self._reconstruct_text_from_json(json_items)
                
                doc_type = self._detect_doc_type(text)
                if doc_type:
                    item.getMetadata().add(ExtraProperties.FISCAL_DOCTYPE, doc_type)
                    if doc_type == "NFe":
                        item.addCategory("Tax Invoices")
                    elif doc_type == "CTe":
                        item.addCategory("Eletronic Transport Documents")
                        
                    data = self._extract_fiscal_data_spatial(json_items, doc_type, text)
                    print("DEBUG_FISCAL_SPATIAL: " + str(data))
                    self._populate_metadata(item, data)
                    return
        except Exception as e:
            print("DEBUG_FISCAL_ERROR: " + str(e))
            pass
            
        doc_type = self._detect_doc_type(text)
        
        if doc_type:
            # Set Doc Type
            item.getMetadata().add(ExtraProperties.FISCAL_DOCTYPE, doc_type)
            
            # Categorize
            if doc_type == "NFe":
                item.addCategory("Tax Invoices")
                # item.getMetadata().set("Generico", "NFe Detected") # Debug
            elif doc_type == "CTe":
                item.addCategory("Eletronic Transport Documents")
                
            # Extract Data
            data = self._extract_fiscal_data(text, doc_type)
            
            # Populate Metadata
            # Populate Metadata
            self._populate_metadata(item, data)

    def _populate_metadata(self, item, data):
        if data.get('remetCNPJ'):
            item.getMetadata().add(ExtraProperties.FISCAL_REMET_CNPJ, data['remetCNPJ'])
        if data.get('remetName'):
            item.getMetadata().add(ExtraProperties.FISCAL_REMET_NAME, data['remetName'])
        if data.get('destCNPJ'):
            item.getMetadata().add(ExtraProperties.FISCAL_DEST_CNPJ, data['destCNPJ'])
        if data.get('destName'):
            item.getMetadata().add(ExtraProperties.FISCAL_DEST_NAME, data['destName'])
        if data.get('value'):
            item.getMetadata().add(ExtraProperties.FISCAL_VALUE, str(data['value']))
        if data.get('icms'):
            item.getMetadata().add(ExtraProperties.FISCAL_ICMS, str(data['icms']))
        if data.get('remetCity'):
            item.getMetadata().add(ExtraProperties.FISCAL_REMET_CITY, data['remetCity'])
        if data.get('remetUF'):
            item.getMetadata().add(ExtraProperties.FISCAL_REMET_UF, data['remetUF'])
        if data.get('destCity'):
            item.getMetadata().add(ExtraProperties.FISCAL_DEST_CITY, data['destCity'])
        if data.get('destUF'):
            item.getMetadata().add(ExtraProperties.FISCAL_DEST_UF, data['destUF'])


    def _detect_doc_type(self, text):
        text_lower = text.lower()
        # Normalize whitespace to single space to handle line breaks in headers
        text_clean = re.sub(r'\s+', ' ', text_lower)
        
        if "documento auxiliar da nota fiscal" in text_clean or \
           ("danfe" in text_clean and "chave de acesso" in text_clean):
            return "NFe"
        elif "documento auxiliar do conhecimento de transporte" in text_clean or \
             ("dacte" in text_clean and "conhecimento de transporte" in text_clean) or \
             "ct-e" in text_clean:
            return "CTe"
        return None

    # Global skip terms for name extraction (Address indicators, Keywords, Modals)
    # Includes accented and unaccented variations
    SKIP_TERMS = ["ENDERE", "RODOVI", "AEREO", "AQUAVI", "FERROVI", "DUTOVI", "MULTIMODAL", 
                  "CNPJ", "CPF", "INSCRI", "INSCRIÇÃO", "INSCRIÇAO", "INSCRICAO", "FONE", "CEP", "MUNICIPIO", "MUNICÍPIO", "MUNICÃPIO", "BAIRRO", "CENTRO", 
                  "ZONA", "RUA", "AVENIDA", "AV.", "AV ", "TRAVESSA", "ALAMEDA", "RODOVIA", "ROD",
                  "ESTRADA", "LOTE", "QUADRA", "SALA", "DATA", "HORA", "EMISSAO", "PROTOCOLO",
                  "ENTRADA", "SAIDA", "PESO", "LIQUIDO", "MARCA", "VOLUMES", "QTD", "ESPECIE",
                  "MERCADORIA", "FRETE", "VALOR", "MOTORISTA", "PLACA", "RNTRC", "BLOCO", "ANDAR", "APTO",
                  "DISTRITO", "INDUSTRIAL", "GLOBALIZADO", "IND.", "CT-E", "CTE", "SERVICO",
                  "GALPAO", "DEVOLUCAO", "TURIAÃ‡U", "TURIAÇU", "HTTP", "HTTPS", "WWW", ".COM", ".BR", ".NET", ".GOV",
                  "DANFE", "SERIE", "CONSELHEIRO", "NATUREZA", "DOCUMENTO", "AUXILIAR", "CONTA",
                  "ESTADUAL", "FEDERAL", "MUNICIPAL", "SUBTRIB", "SUBSTITUICAO", "SUBSTITUIÇÃO", "ENDEREÇO", "ENDERECO"]

    def _is_valid_name_line(self, line):
        if not line or len(line) < 3: return False
        
        # Must contain at least one letter
        if not re.search(r'[A-Za-z]', line):
             return False

        l_upper = line.upper().strip()
        
        # Check for common invalid patterns FIRST (before skip terms)
        # Patterns that indicate this is NOT a company name
        invalid_patterns = [
            r'^S[ÉE]RIE\s*:',           # "Série:"
            r'^NOTA\s+FISCAL',         # "NOTA FISCAL ELETRÔNICA"
            r'^DOCUMENTO',              # "DOCUMENTO AUXILIAR"
            r'^\d+\s*:',                # "123:"
            r'^[A-Z]{2,4}\s*:',         # "Nº Fat:", "UF:"
            r'^\d+\s*-\s*[A-Z]+',       # "1-SAÍDA", "0-ENTRADA"
            r'^N[º°]\s*FAT',            # "Nº Fat:"
            r'^CHAVE\s+DE\s+ACESSO',    # "Chave de acesso"
            r'^PROTOCOLO',              # "Protocolo"
            r'^INSCRI[ÇC][ÃA]O\s+ESTADUAL',  # "INSCRIÇÃO ESTADUAL"
            r'^INSCRI\s+ESTADUAL',      # "INSCRI ESTADUAL"
            r'^INSC\.?\s*EST\.?',       # "INSC. EST." ou "INSC EST"
            r'^IE\s*:',                 # "IE:"
            r'^I\.E\.',                 # "I.E."
        ]
        for pattern in invalid_patterns:
            if re.search(pattern, l_upper):
                return False
        
        # Check against skip terms using word boundaries to avoid false positives
        # Example: "ROD" should match "RODOVIA" but NOT "PRODUTOS"
        for t in self.SKIP_TERMS:
            # Use word boundary regex to match whole words only
            # This prevents "ROD" from matching "PRODUTOS"
            pattern = r'\b' + re.escape(t) + r'\b'
            if re.search(pattern, l_upper):
                return False
        
        # Check against City - UF pattern (e.g., "City - UF")
        if re.search(r'\s-\s[A-Z]{2}\b', line): 
             return False
             
        # Check against City/UF pattern (e.g., "City/UF")
        if re.search(r'/[A-Z]{2}\b', line):
             return False
             
        # Check for Phone number pattern (XX)XXXX or similar
        # Handles (XX), (XXX), (XXXX) common in some prints
        if re.search(r'\(\d{2,4}\)', line): 
             return False
        
        # Additional validation: reject lines that are too short or look like codes
        # Reject lines that are mostly numbers or special characters
        if len(re.sub(r'[A-Za-z\s]', '', l_upper)) > len(re.sub(r'[^A-Za-z\s]', '', l_upper)) * 0.5:
            return False
             
        return True


    def _extract_fiscal_data(self, text, doc_type):
        data = {}
        if doc_type == "NFe":
            data = self._extract_nfe_data(text)
        elif doc_type == "CTe":
            data = self._extract_cte_data(text)
            
        # Swap logic for NFe (tpNF=0 - Entry, tpNF=1 - Exit)
        if doc_type == "NFe":
            is_entry = re.search(r'tpNF\s*:\s*0', text) or \
                       re.search(r'0\s*-\s*Entrada', text, re.IGNORECASE)


            if is_entry:
                 # Swap remetente/destinatario
                 remet_cnpj = data.get('remetCNPJ')
                 remet_name = data.get('remetName')
                 remet_city = data.get('remetCity')
                 remet_uf = data.get('remetUF')
                 dest_cnpj = data.get('destCNPJ')
                 dest_name = data.get('destName')
                 dest_city = data.get('destCity')
                 dest_uf = data.get('destUF')
                 
                 data['remetCNPJ'] = dest_cnpj
                 data['remetName'] = dest_name
                 data['remetCity'] = dest_city
                 data['remetUF'] = dest_uf
                 data['destCNPJ'] = remet_cnpj
                 data['destName'] = remet_name
                 data['destCity'] = remet_city
                 data['destUF'] = remet_uf
                 

        return data

    def _extract_nfe_data(self, text):
        data = {}
        
        cnpj_pattern = r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}'
        cnpjs = re.findall(cnpj_pattern, text)
        
        
        # Name Heuristics for NFe
        # Usually NOME/RAZAO SOCIAL is followed by the name
        # Or look for patterns like "DESTINATARIO/REMETENTE" -> "NOME/RAZAO SOCIAL" -> Name
        
        # Remetente Name (Emitente)
        remet_match = re.search(r'(?:NOME\/RAZ.O SOCIAL|EMITENTE)[\s\S]*?[:\n](.+)', text, re.IGNORECASE)
        # Often Emitente is at the top left, hard to regex without structure.
        # Fallback to lines near the first CNPJ if possible?
        
        # Destinatario Name
        dest_match = re.search(r'(?:DESTINAT.RIO|NOME\/RAZ.O SOCIAL)(?:[\s\S]*?)[:\n](.+)', text, re.IGNORECASE)
        
        # NOTE: NFe plain text is chaotic. We use generic fallbacks if specific headers missed.
        
        # Try to identify emitente and destinatario based on document structure
        # Look for "EMITENTE" or "DESTINATÁRIO" labels near CNPJs
        emitente_cnpj = None
        destinatario_cnpj = None
        
        # Search for CNPJ near "EMITENTE" label
        emitente_match = re.search(r'EMITENTE[^\d]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', text, re.IGNORECASE)
        if emitente_match:
            emitente_cnpj = emitente_match.group(1)
        
        # Search for CNPJ near "DESTINATÁRIO" or "DESTINATARIO" label  
        dest_match = re.search(r'DESTINAT[ÁA]RIO[^\d]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', text, re.IGNORECASE)
        if dest_match:
            destinatario_cnpj = dest_match.group(1)
        
        # Assign CNPJs based on labels if found, otherwise use order
        if emitente_cnpj and emitente_cnpj in cnpjs:
            data['remetCNPJ'] = emitente_cnpj
            if destinatario_cnpj and destinatario_cnpj in cnpjs:
                data['destCNPJ'] = destinatario_cnpj
            elif len(cnpjs) >= 2:
                # Find first CNPJ that's not the emitente
                for cnpj in cnpjs:
                    if cnpj != emitente_cnpj:
                        data['destCNPJ'] = cnpj
                        break
        elif destinatario_cnpj and destinatario_cnpj in cnpjs:
            data['destCNPJ'] = destinatario_cnpj
            if len(cnpjs) >= 1:
                # Find first CNPJ that's not the destinatario
                for cnpj in cnpjs:
                    if cnpj != destinatario_cnpj:
                        data['remetCNPJ'] = cnpj
                        break
        else:
            # Fallback to order-based assignment
            if len(cnpjs) >= 1:
                data['remetCNPJ'] = cnpjs[0]
            if len(cnpjs) >= 2:
                data['destCNPJ'] = cnpjs[1]
            
        # NFe Name Extraction - Improved based on Tika headers
        # Remetente: Often under "Identificação do emitente"
        # Match "Identif... emitente" then skip empty lines to find Name
        remet_header = re.search(r'Identif\s*ica..o\s*do\s*emitente', text, re.IGNORECASE)
        if remet_header:
            # Look ahead for next non-empty line
            start = remet_header.end()
            # Grab next 500 chars to analyze names (limit to avoid going too far)
            chunk = text[start:start+500]
            # Use splitlines() to handle both \n and \r\n
            lines = [x.strip() for x in chunk.splitlines() if x.strip()]
            # Try to find the FIRST valid name line (should be the company name)
            # Limit to first 5 lines to avoid picking up wrong names from other sections
            for l in lines[:5]:
                # Skip common header patterns
                if any(skip in l.upper() for skip in ["DANFE", "DOCUMENTO", "NOTA FISCAL", "IDENTIFICAÇÃO", "EMITENTE", "AV ", "AVENIDA", "RUA", "FONE", "CEP"]):
                    continue
                if self._is_valid_name_line(l):
                    data['remetName'] = l
                    break

        # Dest Name Strategy:
        # 1. Look for specific "NOME/RAZAO SOCIAL" label (Strong Signal)
        # Note: Text may have CRLF or LF line endings
        # Use finditer to find the right occurrence if multiple
        name_matches = list(re.finditer(r'NOME/RAZ[^\r\n]*SOCIAL\s*[\r\n]+\s*([^\r\n]+)', text, re.IGNORECASE))
        # Try to find the one associated with destinatario (usually the second occurrence)
        # First occurrence is usually emitente, second is destinatario
        for i, nm in enumerate(name_matches):
             candidate = nm.group(1).strip()
             # Skip common invalid patterns
             if any(inv in candidate.upper() for inv in ["INSCRI", "ESTADUAL", "FEDERAL", "CNPJ", "CPF", "CEP", "FONE"]):
                 continue
             if self._is_valid_name_line(candidate):
                 # If we have multiple matches, prefer the second one (destinatario)
                 # But if we only have one match and it's valid, use it
                 if len(name_matches) == 1 or i >= 1:
                     data['destName'] = candidate
                     break

        # 2. Fallback: Destinatario Header + 1st line (Weak Signal)
        if 'destName' not in data:
            dest_header = re.search(r'DESTINAT[ÁA]RIO\s*/?\s*REMETENTE', text, re.IGNORECASE)
            if dest_header:
                start = dest_header.end()
                chunk = text[start:start+1000]
                lines = [x.strip() for x in chunk.splitlines() if x.strip()]
                if len(lines) >= 1:
                    # Try first few lines, but skip headers and invalid patterns
                    for i in range(min(5, len(lines))):
                        candidate = lines[i]
                        # Skip if it is a header itself or contains invalid patterns
                        if any(skip in candidate.upper() for skip in ["NOME", "RAZ", "INSCRI", "ESTADUAL", "CNPJ", "CPF", "CEP", "FONE", "ENDERE", "MUNICIPIO"]):
                            continue
                        
                        if self._is_valid_name_line(candidate):
                            data['destName'] = candidate
                            break
                            
        # 3. Fallback: Look for "RECEBEMOS DE" pattern (common in some NFe formats)
        if 'remetName' not in data:
            recebemos_match = re.search(r'RECEBEMOS\s+DE\s+[\'"]?([^\'"\n]+?)[\'"]?\s+(?:OS\s+PRODUTO|OS\s+MERCADORIA)', text, re.IGNORECASE)
            if recebemos_match:
                candidate = recebemos_match.group(1).strip()
                if self._is_valid_name_line(candidate):
                    data['remetName'] = candidate
        
        # 4. Enhanced Fallback: Look for "EMITENTE" or "RAZÃO SOCIAL" patterns
        if 'remetName' not in data:
            # Try to find name after "EMITENTE" label
            emitente_match = re.search(r'EMITENTE\s*[:\n]\s*([^\n]+)', text, re.IGNORECASE)
            if emitente_match:
                candidate = emitente_match.group(1).strip()
                if self._is_valid_name_line(candidate):
                    data['remetName'] = candidate
        
        # 5. Enhanced Fallback: Look for company name patterns near CNPJ
        if 'remetName' not in data:
            # Pattern: CNPJ followed by company name on next line
            for cnpj in cnpjs[:2]:  # Check first 2 CNPJs
                cnpj_idx = text.find(cnpj)
                if cnpj_idx != -1:
                    # Look at lines after CNPJ
                    start = cnpj_idx + len(cnpj)
                    chunk = text[start:start+200]
                    lines = [x.strip() for x in chunk.splitlines() if x.strip()]
                    for line in lines[:3]:
                        if self._is_valid_name_line(line) and len(line) > 5:
                            data['remetName'] = line
                            break
                    if 'remetName' in data:
                        break
        
        # 6. Enhanced Fallback: Look for common company name patterns
        if 'destName' not in data:
            # Pattern: "DESTINATÁRIO" followed by name
            dest_patterns = [
                r'DESTINAT[ÁA]RIO\s*[:\n]\s*([^\n]+)',
                r'DESTINAT[ÁA]RIO\s*/\s*DESTINAT[ÁA]RIO\s*[:\n]\s*([^\n]+)',
                r'NOME\s*[:\n]\s*([^\n]+)',
                r'RAZ[ÃA]O\s+SOCIAL\s*[:\n]\s*([^\n]+)'
            ]
            for pattern in dest_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    if self._is_valid_name_line(candidate) and len(candidate) > 5:
                        data['destName'] = candidate
                        break
        
        # 5. Fallback: Proximity to CNPJ (ONLY if name not found yet)
        # This should be the last resort, as it may pick wrong names from other sections
        if 'remetName' not in data and data.get('remetCNPJ'):
             name_near = self._extract_name_near_cnpj(text, data['remetCNPJ'])
             if name_near:
                 data['remetName'] = name_near
        if 'destName' not in data and data.get('destCNPJ'):
             name_near = self._extract_name_near_cnpj(text, data['destCNPJ'])
             if name_near:
                 data['destName'] = name_near

        # Location: CITY/UF
        # 1. Combined [CITY]/[UF] pattern common in NFe address line
        # Use word boundaries more carefully to avoid matching parts of words
        uf_pattern = r'\b([A-Z][A-Z\s\.\-]{2,38}[A-Z])\s*/\s*([A-Z]{2})\b'
        loc_matches = list(re.finditer(uf_pattern, text))
        valid_cities = []
        for m in loc_matches:
            city = m.group(1).strip()
            uf = m.group(2)
            # Filter invalid cities - must start and end with letter, not be part of a larger word
            skip_words = ["VOLUMES", "DATA", "HORA", "PROTOCOLO", "CHAVE", "ACESSO", "NATUREZA", "OPERACAO", "SOCIAL", "BAIRRO", "DISTRITO"]
            # Check if city looks valid (has spaces or is a known city name pattern)
            if self._is_valid_uf(uf) and len(city) > 3 and not any(sw in city.upper() for sw in skip_words):
                # Additional check: city should have at least one space or be a known city name pattern
                if ' ' in city or len(city.split()) >= 1:
                    valid_cities.append((city, uf))
        
        # 2. Enhanced [CITY] - [UF] pattern
        city_uf_pattern = r'\b([A-Za-z][A-Za-z\s\.\-]{3,40}[A-Za-z])\s*-\s*([A-Z]{2})\b'
        city_uf_matches = list(re.finditer(city_uf_pattern, text))
        for m in city_uf_matches:
            city = m.group(1).strip()
            uf = m.group(2)
            skip_words = ['CFOP', 'ENTRADA', 'PRINCIPA', 'MODAL', 'CT-E', 'CTE', 'SERVICO', 'TIPO', 
                          'ROD', 'BR', 'KM', 'SITIO', 'FAZENDA', 'ESTRADA', 'VOLUMES', 'DATA']
            if self._is_valid_uf(uf) and len(city) > 3 and not any(sw in city.upper() for sw in skip_words):
                valid_cities.append((city, uf))
        
        # Remove duplicates and sort by occurrence order
        seen = set()
        unique_cities = []
        for city, uf in valid_cities:
            key = (city.upper(), uf.upper())
            if key not in seen:
                seen.add(key)
                unique_cities.append((city, uf))
        
        # Assign cities: first is remetente, second is destinatario
        if len(unique_cities) >= 1 and 'remetCity' not in data:
            data['remetCity'] = unique_cities[0][0]
            data['remetUF'] = unique_cities[0][1]
        if len(unique_cities) >= 2 and 'destCity' not in data:
            # Only assign if different from remetente
            if unique_cities[1][0] != data.get('remetCity', ''):
                data['destCity'] = unique_cities[1][0]
                data['destUF'] = unique_cities[1][1]

        # 2. Split Headers: MUNICIPIO \n [CITY] ... UF \n [UF]
        if 'destCity' not in data or 'destUF' not in data:
            # Look for MUNICIPIO near UF
            # This is tricky because there are multiple. 
            # We assume Destinatario block comes after Remetente.
            # Let's try to match pairs
            mun_matches = list(re.finditer(r'MUNIC[ÍI]PIO\s*[:\n]\s*([^\n]+)', text, re.IGNORECASE))
            uf_matches = list(re.finditer(r'\bUF\s*[:\n]\s*([A-Z]{2})\b', text, re.IGNORECASE))
            
            # Filter out invalid cities from MUNICIPIO matches
            valid_mun_cities = []
            for m in mun_matches:
                city = m.group(1).strip()
                # Skip if it's not a valid city name
                if len(city) > 2 and not any(skip in city.upper() for skip in ["DATA", "HORA", "PROTOCOLO", "CHAVE"]):
                    valid_mun_cities.append(city)
            
            # If we have matches, map them. 
            # Usually Match 0 -> Remet (if strictly labeled), Match 1 -> Dest.
            if len(valid_mun_cities) > 0 and 'remetCity' not in data:
                 data['remetCity'] = valid_mun_cities[0]
            if len(valid_mun_cities) > 1 and 'destCity' not in data:
                 data['destCity'] = valid_mun_cities[1]
                 
            if len(uf_matches) > 0 and 'remetUF' not in data:
                 data['remetUF'] = uf_matches[0].group(1).strip()
            if len(uf_matches) > 1 and 'destUF' not in data:
                 data['destUF'] = uf_matches[1].group(1).strip()
        
        # 3. Fallback: Look for city near CNPJ blocks
        if 'remetCity' not in data and data.get('remetCNPJ'):
            city_near = self._extract_city_near_cnpj(text, data['remetCNPJ'])
            if city_near:
                data['remetCity'] = city_near[0]
                data['remetUF'] = city_near[1]
        if 'destCity' not in data and data.get('destCNPJ'):
            city_near = self._extract_city_near_cnpj(text, data['destCNPJ'])
            if city_near:
                data['destCity'] = city_near[0]
                data['destUF'] = city_near[1]

        # Value
        val_match = re.search(r'(?:VALOR TOTAL DA NOTA|V\. TOTAL DA NOTA)[\s\S]*?(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.IGNORECASE)
        if val_match:
            data['value'] = self._parse_money(val_match.group(1))
            
        # ICMS
        icms_match = re.search(r'VALOR DO ICMS[\s\S]*?(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.IGNORECASE)
        if icms_match:
             data['icms'] = self._parse_money(icms_match.group(1))
        
        
        return data

    def _is_valid_uf(self, uf):
        valid = {'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'}
        return uf.upper() in valid

    def _extract_cte_data(self, text):
        data = {}
        
        cnpj_pattern = r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}'
        cnpjs = re.findall(cnpj_pattern, text)
        
        # Regex Blocks - Multi-line safe
        # Remetente - Requires colon or newline delimiter to avoid "Remetente Nao"
        remet_block = re.search(r'REMETENTE[ \t]*(?:[:\r\n]|:\s*)([\s\S]{0,200}?)(?:DEST|EXPED|RECEB|TOMADOR)', text, re.IGNORECASE)
        if remet_block:
            block = remet_block.group(1)
            # Find CNPJ in block
            cnpj_m = re.search(cnpj_pattern, block)
            if cnpj_m: data['remetCNPJ'] = cnpj_m.group(0)
            
            # Find Name (usually first line of block or after label)
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            for l in lines:
                if not re.search(cnpj_pattern, l) and self._is_valid_name_line(l):
                    data['remetName'] = l
                    break
        
        # Destinatario
        dest_block = re.search(r'(?:DESTINAT.RIO|DESTINO)[ \t]*(?:[:\r\n]|:\s*)([\s\S]{0,200}?)(?:EXPED|RECEB|TOMADOR|VALOR)', text, re.IGNORECASE)
        if dest_block:
            block = dest_block.group(1)
            cnpj_m = re.search(cnpj_pattern, block)
            if cnpj_m: data['destCNPJ'] = cnpj_m.group(0)
            
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            for l in lines:
                 if not re.search(cnpj_pattern, l) and self._is_valid_name_line(l):
                    data['destName'] = l
                    break

        # Fallback to indices for CNPJ
        if not data.get('remetCNPJ') and len(cnpjs) >= 2:
             data['remetCNPJ'] = cnpjs[1]
        if not data.get('destCNPJ') and len(cnpjs) >= 3:
             data['destCNPJ'] = cnpjs[2]

        # Value
        val_match = re.search(r'(?:VALOR TOTAL DO SERVI.O|TOTAL DO SERVI.O|FRETE VALOR)[\s\S]*?(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.IGNORECASE)
        if val_match:
            data['value'] = self._parse_money(val_match.group(1))
        
        # ICMS for CTe - pattern: "ICMS [base] [rate%] [value]" - take last number
        # Also check for "ICMS Outra UF [value]"
        icms_match = re.search(r'ICMS\s+(?:Outra\s+UF\s+)?(?:\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\s+)?(?:\d{1,2}[.,]\d{2}\s+)?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', text, re.IGNORECASE)
        if icms_match:
            data['icms'] = self._parse_money(icms_match.group(1))
        
        # City/State for CTe - pattern: "[City] - [UF]" (e.g., "Rio de Janeiro - RJ")
        # CTe documents usually have Origin and Destination cities in this format
        city_uf_pattern = r'\b([A-Za-z][A-Za-z\s\.]+?)\s+-\s+([A-Z]{2})\b'
        city_matches = re.findall(city_uf_pattern, text)
        
        # Filter valid cities (exclude junk like "CFOP - NA", "COM ENTRADA PRINCIPA - TU")
        valid_cities = []
        for city, uf in city_matches:
            city = city.strip()
            if self._is_valid_uf(uf) and len(city) > 3:
                # Filter out common non-city patterns
                skip_words = ['CFOP', 'ENTRADA', 'PRINCIPA', 'MODAL', 'CT-E', 'CTE', 'SERVICO', 'TIPO', 
                              'ROD', 'BR', 'KM', 'SITIO', 'FAZENDA', 'ESTRADA']
                if not any(sw in city.upper() for sw in skip_words):
                    valid_cities.append((city, uf))
        
        # Assign first as remetente, second as destinatario
        if len(valid_cities) >= 1:
            data['remetCity'] = valid_cities[0][0]
            data['remetUF'] = valid_cities[0][1]
        if len(valid_cities) >= 2:
            data['destCity'] = valid_cities[1][0]
            data['destUF'] = valid_cities[1][1]
            
        # Fallback: Find name near CNPJ if missing
        if not data.get('remetName') and data.get('remetCNPJ'):
            data['remetName'] = self._extract_name_near_cnpj(text, data['remetCNPJ'])
        if not data.get('destName') and data.get('destCNPJ'):
            data['destName'] = self._extract_name_near_cnpj(text, data['destCNPJ'])
             
        return data

    def _extract_city_near_cnpj(self, text, cnpj):
        """Finds a potential city/UF near the given CNPJ."""
        try:
            idx = text.find(cnpj)
            if idx == -1: return None
            
            # Look at 300 chars before and after
            start = max(0, idx - 300)
            end = min(len(text), idx + 300)
            chunk = text[start:end]
            
            # Look for CITY/UF pattern
            city_uf_match = re.search(r'\b([A-Z\s\.\-]{3,40})\s*/\s*([A-Z]{2})\b', chunk)
            if city_uf_match:
                city = city_uf_match.group(1).strip()
                uf = city_uf_match.group(2)
                skip_words = ["VOLUMES", "DATA", "HORA", "PROTOCOLO"]
                if self._is_valid_uf(uf) and not any(sw in city.upper() for sw in skip_words) and len(city) > 2:
                    return (city, uf)
            
            # Look for CITY - UF pattern
            city_uf_match2 = re.search(r'\b([A-Z\s\.\-]{3,40})\s+-\s+([A-Z]{2})\b', chunk)
            if city_uf_match2:
                city = city_uf_match2.group(1).strip()
                uf = city_uf_match2.group(2)
                if self._is_valid_uf(uf) and len(city) > 2:
                    return (city, uf)
            
            return None
        except:
            return None

    def _extract_name_near_cnpj(self, text, cnpj):
        """Finds a potential company name near the given CNPJ."""
        try:
            # Find CNPJ index
            idx = text.find(cnpj)
            if idx == -1: return None
            
            # Look at 200 chars before and after
            start = max(0, idx - 200)
            end = min(len(text), idx + 200)
            chunk = text[start:end]
            
            lines = [l.strip() for l in chunk.splitlines() if l.strip()]
            
            # Find the line containing the CNPJ
            cnpj_line_idx = -1
            for i, line in enumerate(lines):
                if cnpj in line:
                    cnpj_line_idx = i
                    break
            
            if cnpj_line_idx != -1:
                # Iterate upwards from CNPJ line to find Name
                # Limit search to 20 lines above (increased for sparse headers)
                candidates = []
                for k in range(1, 20):
                    if cnpj_line_idx - k < 0: break
                    
                    l = lines[cnpj_line_idx - k]
                    
                    # If line contains a CNPJ (likely the Other Party's CNPJ), STOP searching.
                    # This prevents crossing from Destinatario block up into Remetente block.
                    if re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', l): 
                        break
                    
                    candidates.append(l)
                    if self._is_valid_name_line(l):
                        return l
                
                # Also try looking DOWN from CNPJ (sometimes name comes after)
                for k in range(1, min(10, len(lines) - cnpj_line_idx - 1)):
                    l = lines[cnpj_line_idx + k]
                    if re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', l):
                        break
                    if self._is_valid_name_line(l):
                        return l
                
                     
            return None
        except:
            return None

    def _parse_money(self, value_str):
        if not value_str:
            return 0.0
        try:
            clean_str = value_str.replace('.', '').replace(',', '.')
            return float(clean_str)
        except:
            return 0.0

    def _reconstruct_text_from_json(self, json_items):
        # Merge items info somewhat readable text
        # Assuming items are sorted by Y then X or similar from parser
        sb = []
        last_y = -1
        for item in json_items:
            t = item.get('t', '')
            y = item.get('y', 0)
            if last_y != -1 and abs(y - last_y) > 5: # New line threshold
                sb.append('\n')
            elif last_y != -1:
                sb.append(' ')
            sb.append(t)
            last_y = y
        return "".join(sb)

    def _extract_fiscal_data_spatial(self, items, doc_type, full_text):
        # Filter items to Page 1 only to avoid ambiguity
        items = [i for i in items if i.get('p', 1) == 1]
        items.sort(key=lambda x: (x.get('y', 0), x.get('x', 0)))

        # 1. Base extraction (includes Regex Swap)
        data = self._extract_fiscal_data(full_text, doc_type)
        
        # 2. Spatial Extraction (Raw from PDF structure)
        spatial_data = {}
        if doc_type == "NFe":
             spatial_data = self._extract_nfe_spatial_raw(items)
        elif doc_type == "CTe":
             spatial_data = self._extract_cte_spatial_raw(items)
        
        # 3. Apply Swap to Spatial Data if needed
        # IMPORTANT: The swap logic is complex and depends on NFe type (Entrada vs Saída)
        # For now, use direct mapping without swap - the emitente is remetente, dest is dest
        is_entry = False
        if doc_type == "NFe":
             # Look for explicit "1 - ENTRADA" or "0 - ENTRADA" patterns
             # tpNF: 0 = Entrada, 1 = Saída in XML
             # But in DANFE text, we see "0-EMITENTE" which is different!
             entrada_match = re.search(r'ENTRADA', full_text, re.IGNORECASE)
             saida_match = re.search(r'SA[ÍI]DA', full_text, re.IGNORECASE)
             # Only consider entry if explicitly marked and no saida marker
             # Actually, let's just check tpNF in structured data if available
             tpnf_match = re.search(r'tpNF\s*[:\s]\s*(\d)', full_text)
             if tpnf_match and tpnf_match.group(1) == '0':
                 is_entry = True
             # Skip the swap for now as it's causing issues - direct mapping is more reliable
             is_entry = False  # DISABLED - TODO: Fix swap logic properly
        
        
        if is_entry and doc_type == "NFe":
             # Swap spatial: PDF Dest -> Logical Remet, PDF Emit/Remet -> Logical Dest
             # For entry NFe, the DESTINATÁRIO in the PDF is actually the sender (remetente)
             # and the EMITENTE in the PDF is actually the recipient (destinatário)
             if spatial_data.get('destName'):
                  data['remetName'] = spatial_data['destName']
             if spatial_data.get('destCity'):
                  data['remetCity'] = spatial_data['destCity']
             if spatial_data.get('destUF'):
                  data['remetUF'] = spatial_data['destUF']
             if spatial_data.get('destCNPJ'):
                  data['remetCNPJ'] = spatial_data['destCNPJ']
                  
             # Emit/Remet -> Dest (handle both old emitName and new remetName keys)
             emit_name = spatial_data.get('emitName') or spatial_data.get('remetName')
             emit_city = spatial_data.get('emitCity') or spatial_data.get('remetCity')
             emit_uf = spatial_data.get('emitUF') or spatial_data.get('remetUF')
             emit_cnpj = spatial_data.get('emitCNPJ') or spatial_data.get('remetCNPJ')
             
             if emit_name:
                  data['destName'] = emit_name
             if emit_city:
                  data['destCity'] = emit_city
             if emit_uf:
                  data['destUF'] = emit_uf
             if emit_cnpj:
                  data['destCNPJ'] = emit_cnpj

        else:
             # Normal map (NFe or CTe)
             if spatial_data.get('destName'):
                  data['destName'] = spatial_data['destName']
             if spatial_data.get('destCity'):
                  data['destCity'] = spatial_data['destCity']
             if spatial_data.get('destUF'):
                  data['destUF'] = spatial_data['destUF']
             if spatial_data.get('destCNPJ'):
                  data['destCNPJ'] = spatial_data['destCNPJ']

             # Emitente (NFe) -> Remetente (handle both emitName and remetName)
             remet_name = spatial_data.get('emitName') or spatial_data.get('remetName')
             remet_city = spatial_data.get('emitCity') or spatial_data.get('remetCity')
             remet_uf = spatial_data.get('emitUF') or spatial_data.get('remetUF')
             remet_cnpj = spatial_data.get('emitCNPJ') or spatial_data.get('remetCNPJ')
             
             if remet_name:
                  data['remetName'] = remet_name
             if remet_city:
                  data['remetCity'] = remet_city
             if remet_uf:
                  data['remetUF'] = remet_uf
             if remet_cnpj:
                  data['remetCNPJ'] = remet_cnpj
        
        # Merge Values if spatial found them (higher confidence usually? or fallback?)
        if spatial_data.get('value'):
             data['value'] = spatial_data['value']
        if spatial_data.get('icms'):
             data['icms'] = spatial_data['icms']
        
        return data

    def _extract_cte_spatial_raw(self, items):
        spatial_data = {}
        import re
        
        # CTe structure:
        # - ORIGEM DA PRESTAÇÃO / DESTINO DA PRESTAÇÃO contain city-UF info
        # - REMETENTE: / DESTINATÁRIO: contain company names
        # - VALOR TOTAL DA MERCADORIA for goods value
        # - VALOR ICMS label with actual ICMS value to its right (same row y+7)
        
        # 1. Extract ORIGEM (Remetente Location) and DESTINO (Destinatario Location)
        origem_label = self._find_label_rect(items, ["ORIGEM", "PRESTA"], [])
        if origem_label:
            val = self._find_text_below(items, origem_label, type="value", max_offset_y=50)
            if val:
                m = re.match(r'([^-]+)\s*-\s*([A-Z]{2})', val)
                if m:
                    spatial_data['remetCity'] = m.group(1).strip()
                    spatial_data['remetUF'] = m.group(2).strip()
        
        destino_label = self._find_label_rect(items, ["DESTINO", "PRESTA"], [])
        if destino_label:
            val = self._find_text_below(items, destino_label, type="value", max_offset_y=50)
            if val:
                m = re.match(r'([^-]+)\s*-\s*([A-Z]{2})', val)
                if m:
                    spatial_data['destCity'] = m.group(1).strip()
                    spatial_data['destUF'] = m.group(2).strip()
        
        # 2. Find party anchors (REMETENTE: and DESTINATÁRIO:)
        remet_label = self._find_label_rect(items, ["REMETENTE:"], [])
        if not remet_label:
            for item in items:
                t = item.get('t', '').upper()
                if "REMETENTE" in t and item.get('y') > 150:
                    remet_label = item
                    break
        
        all_dest = self._find_all_labels(items, ["DESTINAT"])
        all_dest = [l for l in all_dest if "SUFRAMA" not in l.get('t','').upper() and l.get('y') > 150]
        
        dest_label = None
        if remet_label and all_dest:
            dest_label = min(all_dest, key=lambda l: abs(l.get('y') - remet_label.get('y')))
        elif all_dest:
            dest_label = all_dest[0]

        split_x = 300
        if dest_label:
            split_x = dest_label.get('x') - 10
        elif remet_label:
            split_x = remet_label.get('x') + 250
        
        remet_items = [i for i in items if i.get('x') < split_x]
        dest_items = [i for i in items if i.get('x') >= split_x]
        
        # 3. Extract Names
        # 3. Extract Names and Details (CNPJ, City)
        if remet_label:
            name = self._find_text_right(remet_items, remet_label, type="name")
            if name: spatial_data['remetName'] = name
            
            # CNPJ - search within remet_items to avoid column overlap
            cnpj_label = self._find_label_rect_in_block(remet_items, remet_label, ["CNPJ"], 150, align_x=True)
            if not cnpj_label:
                cnpj_label = self._find_label_rect_in_block(remet_items, remet_label, ["CNPJ"], 250, align_x=False)
            
            if cnpj_label:
                # Check if the label item itself contains the CNPJ (merged case)
                val = self._parse_cnpj(cnpj_label.get('t'))
                if not val:
                    # Try below first
                    val = self._find_text_below(remet_items, cnpj_label, type="cnpj", max_offset_y=50)
                # If not found, try right
                if not val:
                     val = self._find_text_right(remet_items, cnpj_label, type="cnpj")
                if val: spatial_data['remetCNPJ'] = val

            # City (Fallback if ORIGEM not found)
            if 'remetCity' not in spatial_data:
                 mun_label = self._find_label_rect_in_block(items, remet_label, ["MUNIC"], 150, align_x=True)
                 if mun_label:
                      val = self._find_text_below(items, mun_label, type="value", max_offset_y=40)
                      if not val: val = self._find_text_right(items, mun_label, type="value")
                      
                      if val:
                          # Try to parse City - UF
                          m = re.match(r'([^-]+)\s*-\s*([A-Z]{2})', val)
                          if m:
                              spatial_data['remetCity'] = m.group(1).strip()
                              spatial_data['remetUF'] = m.group(2).strip()
                          else:
                              spatial_data['remetCity'] = val

        if dest_label:
            name = self._find_text_right(dest_items, dest_label, type="name")
            if name: spatial_data['destName'] = name
            
            # CNPJ - search within dest_items
            cnpj_label = self._find_label_rect_in_block(dest_items, dest_label, ["CNPJ"], 150, align_x=True)
            if not cnpj_label:
                 cnpj_label = self._find_label_rect_in_block(dest_items, dest_label, ["CNPJ"], 250, align_x=False)
            
            if cnpj_label:
                val = self._parse_cnpj(cnpj_label.get('t'))
                if not val:
                    val = self._find_text_below(dest_items, cnpj_label, type="cnpj", max_offset_y=50)
                if not val:
                     val = self._find_text_right(dest_items, cnpj_label, type="cnpj")
                if val: spatial_data['destCNPJ'] = val

            # City (Fallback if DESTINO not found)
            if 'destCity' not in spatial_data:
                 mun_label = self._find_label_rect_in_block(items, dest_label, ["MUNIC"], 150, align_x=True)
                 if mun_label:
                      val = self._find_text_below(items, mun_label, type="value", max_offset_y=40)
                      if not val: val = self._find_text_right(items, mun_label, type="value")
                      
                      if val:
                          m = re.match(r'([^-]+)\s*-\s*([A-Z]{2})', val)
                          if m:
                              spatial_data['destCity'] = m.group(1).strip()
                              spatial_data['destUF'] = m.group(2).strip()
                          else:
                              spatial_data['destCity'] = val

        # 4. Extract VALOR TOTAL DA MERCADORIA (goods value)
        val_label = None
        for item in items:
            t = item.get('t', '').upper()
            if "VALOR" in t and "TOTAL" in t and ("MERCADORIA" in t or "CARGA" in t):
                val_label = item
                break
        
        if val_label:
            val = self._find_text_below(items, val_label, type="money", max_offset_y=50)
            if val: spatial_data['value'] = self._parse_money(val)

        # 5. Extract ICMS - Look for "VALOR ICMS" or "ICMS Outra UF" with money value
        icms_label = None
        icms_from_same_line = None
        
        for item in items:
            t = item.get('t', '').upper()
            # Check for "VALOR ICMS" pattern
            if "VALOR" in t and "ICMS" in t and "BASE" not in t:
                icms_label = item
                break
            # Check for "ICMS Outra UF [value]" pattern - value on same line
            if "ICMS" in t and "OUTRA" in t:
                # Try to extract money value from the same text
                m = re.search(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', t)
                if m:
                    icms_from_same_line = m.group(1)
                else:
                    icms_label = item
                break
        
        if icms_from_same_line:
            spatial_data['icms'] = self._parse_money(icms_from_same_line)
        elif icms_label:
            lx = icms_label.get('x')
            ly = icms_label.get('y')
            lp = icms_label.get('p')
            
            # Strategy A: Find money values on same row (y within 10) and to the right of label
            candidates = []
            for item in items:
                if item.get('p') != lp: continue
                ix = item.get('x')
                iy = item.get('y')
                t = item.get('t', '')
                
                # Must be to the right, on same row (or slightly below), and within reasonable distance
                if ix > lx and abs(iy - ly) < 15 and (ix - lx) < 300:
                    # Check if it's a money value
                    if re.search(r'^[\d.,\s]+$', t) and len(t) > 2:
                        candidates.append((ix, item))
            
            if candidates:
                candidates.sort(key=lambda x: x[0])
                val = candidates[0][1].get('t', '').strip()
                spatial_data['icms'] = self._parse_money(val)
            else:
                # Strategy B: Look below the label if no value to the right
                val = self._find_text_below(items, icms_label, type="money", max_offset_y=30)
                if val:
                    spatial_data['icms'] = self._parse_money(val)

        return spatial_data
    def _extract_nfe_spatial_raw(self, items):
        spatial_data = {}
        import re
        
        # 1. EMITENTE (Sender/Remetente) - Top block
        # Look for "Identificação do emitente" or similar in the header area
        emit_label_rect = None
        
        # First try to find specific emitente identification label
        for item in items:
            t = item.get('t','').upper()
            y = item.get('y', 0)
            x = item.get('x', 0)
            # Skip receipt area labels
            if "RECEBEDOR" in t or "ASSINATURA" in t: continue
            # Look for emitente identification in header (y < 100)
            if y < 100 and x > 100 and x < 400:
                if "IDENTIF" in t and ("EMITENTE" in t or y < 50):
                    emit_label_rect = item
                    break
        
        # Fallback: look for CNPJ or company name
        if not emit_label_rect:
             for item in items:
                 t = item.get('t','').upper()
                 y = item.get('y',0)
                 x = item.get('x',0)
                 if y < 80 and "RECEBEMOS" in t: continue
                 if y < 300 and x < 300:
                     if "CNPJ" in t or "EMITENTE" in t or (len(t) > 10 and "NOTA" not in t and "RECEBEDOR" not in t):
                         emit_label_rect = item
                         break
        
        if emit_label_rect:
            emit_y = emit_label_rect.get('y')
            emit_x = emit_label_rect.get('x')
            t_upper = emit_label_rect.get('t','').upper()
            
            # Name - look for company name below "Identificação do emitente"
            name = None
            if "IDENTIF" in t_upper:
                # Look for the first valid name below this label
                candidates = []
                for item in items:
                    iy = item.get('y', 0)
                    ix = item.get('x', 0)
                    # Must be below the label, within reasonable distance, aligned X
                    if iy > emit_y and iy < emit_y + 50 and abs(ix - emit_x) < 50:
                        txt = item.get('t', '')
                        if len(txt) > 5 and "RECEBEMOS" not in txt.upper() and "CNPJ" not in txt.upper():
                            if not any(skip in txt.upper() for skip in ["ENDERECO", "BAIRRO", "CEP", "FONE", "FAX", "HTTP", "WWW"]):
                                candidates.append((iy, txt))
                if candidates:
                    candidates.sort(key=lambda c: c[0])
                    name = candidates[0][1]
            elif "CNPJ" in t_upper:
                 candidates = [i for i in items if i.get('y') < emit_y and i.get('y') > emit_y - 50 and i.get('x') < 300]
                 if candidates: name = candidates[-1].get('t')
            else:
                 name = emit_label_rect.get('t')
                 if len(name) < 5 or "CNPJ" in name.upper():
                      name = self._find_text_below(items, emit_label_rect, type="name", max_offset_y=60)
            if name and "RECEBEMOS" not in name.upper(): spatial_data['remetName'] = name
            
            # CNPJ
            # CNPJ - increased depth for sparse DANFEs
            emit_cnpj = self._find_label_rect_in_block(items, emit_label_rect, ["CNPJ"], 250, align_x=False)
            if not emit_cnpj and "CNPJ" in t_upper: emit_cnpj = emit_label_rect
            if emit_cnpj:
                cnpj = self._find_text_below(items, emit_cnpj, type="cnpj", max_offset_y=30)
                if not cnpj: cnpj = self._find_text_right(items, emit_cnpj, type="cnpj") # Fallback
                if cnpj: spatial_data['remetCNPJ'] = cnpj

            # City - Search in emitente header area (relative to emit_label, not hardcoded)
            found_city = False
            
            # Strategy 1: Look for "City/UF" or "City - UF" pattern below emitente name
            for item in items:
                if item.get('p') != 1: continue
                iy = item.get('y', 0)
                ix = item.get('x', 0)
                # Search from emit_y to emit_y + 100, aligned with emit block (x near emit_x)
                if iy > emit_y and iy < emit_y + 100 and abs(ix - emit_x) < 100:
                    t = item.get('t', '')
                    m = re.search(r'([A-Za-z\s]+)[/-]\s*([A-Z]{2})\b', t)
                    if m and len(m.group(1).strip()) > 2:
                        city = m.group(1).strip()
                        uf = m.group(2)
                        if "CEP" in t.upper() or "FOLHA" in t.upper(): continue
                        if re.match(r'^[\d]+$', city): continue
                        spatial_data['remetCity'] = city
                        spatial_data['remetUF'] = uf
                        found_city = True
                        break
            
            # Strategy 2: Look for known city names in emitente block if no pattern match
            if not found_city:
                # Map known cities to their states
                known_cities = {
                    "GOVERNADOR VALADARES": "MG", "SAO PAULO": "SP", "RIO DE JANEIRO": "RJ", 
                    "BELO HORIZONTE": "MG", "DIADEMA": "SP", "SERRA": "ES", "MARACANAU": "CE",
                    "EUSEBIO": "CE", "DUQUE DE CAXIAS": "RJ", "BELFORD ROXO": "RJ"
                }
                for item in items:
                    if item.get('p') != 1: continue
                    iy = item.get('y', 0)
                    ix = item.get('x', 0)
                    if iy > emit_y and iy < emit_y + 100 and abs(ix - emit_x) < 100:
                        t = item.get('t', '').upper()
                        for kc, uf in known_cities.items():
                            if kc in t:
                                spatial_data['remetCity'] = kc
                                spatial_data['remetUF'] = uf
                                found_city = True
                                break
                    if found_city: break
            if not found_city:
                  # Look for MUNIC label only in emitente area (y < 200)
                  mun_label = None
                  for item in items:
                      it = item.get('t', '').upper()
                      iy = item.get('y', 0)
                      if 'MUNIC' in it and iy > emit_y and iy < 200:
                          mun_label = item
                          break
                  if mun_label:
                      city = self._find_text_below(items, mun_label, type="value", max_offset_y=40)
                      if city: spatial_data['remetCity'] = city
                      
                      # UF Fallback
                      uf_label = self._find_label_rect_in_block(items, mun_label, ["UF"], 50, align_x=False)
                      if not uf_label:
                           # Try searching globally near emit block
                           uf_label = self._find_label_rect_in_block(items, emit_label_rect, ["UF"], 300, align_x=False)
                      
                      if uf_label:
                           uf = self._find_text_below(items, uf_label, type="value", max_offset_y=40)
                           if uf and len(uf.strip()) == 2: spatial_data['remetUF'] = uf.strip()

        # Global fallback for remetCity if not found via emit_label_rect
        if not spatial_data.get('remetCity'):
            # Search in top header area (y < 180) for known cities
            known_cities = {
                "GOVERNADOR VALADARES": "MG", "SAO PAULO": "SP", "RIO DE JANEIRO": "RJ", 
                "BELO HORIZONTE": "MG", "DIADEMA": "SP", "SERRA": "ES", "MARACANAU": "CE",
                "EUSEBIO": "CE", "DUQUE DE CAXIAS": "RJ", "BELFORD ROXO": "RJ"
            }
            for item in items:
                if item.get('p') != 1: continue
                iy = item.get('y', 0)
                ix = item.get('x', 0)
                # Header area (y < 180) and left side of page
                if iy < 180 and iy > 50 and ix < 300:
                    t = item.get('t', '').upper()
                    for kc, uf in known_cities.items():
                        if kc in t:
                            spatial_data['remetCity'] = kc
                            spatial_data['remetUF'] = uf
                            break
                if spatial_data.get('remetCity'): break

        # 2. DESTINATÁRIO block (Recipient)
        dest_label_rect = self._find_label_rect(items, ["DESTINAT"], ["DESTINATÁRIO", "DESTINATARIO"])
        
        if dest_label_rect:
            dest_y = dest_label_rect.get('y')
            
            # Name
            name_label = self._find_label_rect_in_block(items, dest_label_rect, ["NOME", "RAZ"], 100, align_x=False)
            if name_label:
                name = self._find_text_below(items, name_label, type="name")
                if name: spatial_data['destName'] = name
            else:
                name = self._find_text_below(items, dest_label_rect, type="name", max_offset_y=100)
                if name: spatial_data['destName'] = name

            # CNPJ - Fix: Search strictly relative to NAME LABEL if present
            # The Name Label is usually on the same row as CNPJ Label
            ref_y = name_label.get('y') if name_label else dest_y
            
            dest_cnpj_found = False
            for item in items:
                it = item.get('t','').upper()
                if "CNPJ" in it or "CPF" in it:
                    # Must be at or below the reference Y
                    # Tolerance: -5 to +80
                    y_diff = item.get('y') - ref_y
                    if y_diff >= -5 and y_diff < 80:
                         # Must be clearly to the right of the Dest label block start
                         if item.get('x') > dest_label_rect.get('x') + 100:
                             val = self._find_text_below(items, item, type="cnpj", max_offset_y=20)
                             if val:
                                 spatial_data['destCNPJ'] = val
                                 dest_cnpj_found = True
                                 break
            
            if not dest_cnpj_found:
                 cnpj_label = self._find_label_rect_in_block(items, dest_label_rect, ["CNPJ", "CPF"], 60, align_x=True)
                 if cnpj_label:
                    val = self._find_text_below(items, cnpj_label, type="cnpj", max_offset_y=30)
                    if val: spatial_data['destCNPJ'] = val
            
            # City
            found_dest_city = False
            
            # Fallback 1: MUNICIPIO Label (Prioritize this as it's cleaner)
            mun_labels = [i for i in items if "MUNIC" in i.get('t','').upper() 
                          and i.get('y') > dest_y and i.get('y') < dest_y + 150]
            if mun_labels:
                mun_lbl = mun_labels[0]
                city = self._find_text_below(items, mun_lbl, type="value", max_offset_y=40)
                if city:
                     spatial_data['destCity'] = city
                     found_dest_city = True

            # Regex Fallback
            if not found_dest_city:
                for item in items:
                    if item.get('p') != 1: continue
                    iy = item.get('y', 0)
                    if iy > dest_y + 10 and iy < dest_y + 120:
                        t = item.get('t', '')
                        m = re.search(r'([A-Za-z\s]+)[/-]\s*([A-Z]{2})\b', t)
                        if m and len(m.group(1).strip()) > 2:
                            city = m.group(1).strip()
                            uf = m.group(2)
                            if city == spatial_data.get('remetCity'): continue
                            if "CEP" in t.upper() or "FOLHA" in t.upper(): continue
                            if re.match(r'^[\d]+$', city): continue
                            spatial_data['destCity'] = city
                            spatial_data['destUF'] = uf
                            found_dest_city = True
                            break
            
            # Fallback UF
            if not spatial_data.get('destUF'):
                 # Try finding "UF" label near Mun label or in block
                 # Using find_label_rect is risky if it picks header. 
                 # Search manually near bottom of block
                 uf_labels = [i for i in items if i.get('t') == "UF" and i.get('y') > dest_y and i.get('y') < dest_y + 150]
                 if uf_labels:
                      # use rightmost or one aligned with Mun?
                      uf_lbl = uf_labels[0] 
                      uf = self._find_text_below(items, uf_lbl, type="value", max_offset_y=40)
                      if uf: spatial_data['destUF'] = uf

        # 3. VALUES (Same as before)
        total_label = self._find_label_rect(items, ["VALOR", "TOTAL", "NOTA"], ["V. TOTAL", "PRODUTOS"])
        if total_label:
            val = self._find_text_below(items, total_label, type="money", max_offset_y=60)
            if val: spatial_data['value'] = self._parse_money(val)
             
        icms_labels = self._find_all_labels(items, ["VALOR", "ICMS"])
        for lbl in icms_labels:
            if "SUBST" in lbl.get('t','').upper(): continue
            val = self._find_text_below(items, lbl, type="money", max_offset_y=60)
            if val: 
                spatial_data['icms'] = self._parse_money(val)
                break

        return spatial_data
    def _find_label_check_top(self, items):
        # Specific search for Emitente which might be implicitly at top
        # Check "IDENTIFICAÇÃO DO EMITENTE"
        l = self._find_label_rect(items, ["IDENTIFICA", "EMITENTE"], [])
        if l: return l
        # Check for simple "EMITENTE" label near top of page 1
        return self._find_label_rect(items, ["EMITENTE"], [], max_y=300)

    def _find_label_rect(self, items, keywords, simple_keywords, max_y=9999):
        # Find item containing all keywords
        for item in items:
            if item.get('y') > max_y: continue
            t = item.get('t', '').upper()
            if all(k in t for k in keywords):
                return item
        # Fallback
        if simple_keywords:
            for item in items:
                if item.get('y') > max_y: continue
                t = item.get('t', '').upper()
                if any(k in t for k in simple_keywords):
                    return item
        return None

    def _find_all_labels(self, items, keywords):
        res = []
        for item in items:
            t = item.get('t', '').upper()
            if all(k in t for k in keywords):
                res.append(item)
        return res

    def _find_label_rect_in_block(self, items, parent_rect, keywords, search_depth, align_x=True):
        px = parent_rect.get('x')
        py = parent_rect.get('y')
        pp = parent_rect.get('p')
        
        best = None
        min_dist = 9999
        
        for item in items:
            if item.get('p') != pp: continue
            iy = item.get('y')
            ix = item.get('x')
            
            if iy > py and iy < py + search_depth:
                t = item.get('t', '').upper()
                if all(k in t for k in keywords):
                    if align_x:
                        # Stricter X check
                        if abs(ix - px) < 100:
                             best = item
                             break # Assume first aligned match
                    else:
                        # Just closest in Y
                        if (iy - py) < min_dist:
                            min_dist = iy - py
                            best = item
        return best

    def _find_text_below(self, items, label_rect, type="name", max_offset_y=150):
         label_x = label_rect.get('x')
         label_y = label_rect.get('y')
         label_p = label_rect.get('p')
         label_w = label_rect.get('w')
         
         candidates = []
         for item in items:
             if item.get('p') != label_p: continue
             iy = item.get('y')
             ix = item.get('x')
             
             # Look below (with small tolerance for same-line items slightly above)
             if iy > label_y - 5 and iy < label_y + max_offset_y: 
                 # Skip the label itself
                 if item == label_rect: continue
                 if ix >= label_x - 30 and ix < label_x + label_w + 200: 
                     candidates.append(item)
         
         candidates.sort(key=lambda i: i.get('y'))
         
         for cand in candidates:
             t = cand.get('t', '').strip()
             if not t: continue
             
             if type == "name":
                  if any(skip in t.upper() for skip in ["ENDERE", "CNPJ", "CPF", "BAIRRO", "CEP", "DATA", "FONE", "INSCRI", "MUNIC", "UF", "FONE/FAX"]):
                      continue
                  if self._is_valid_name_line(t):
                      return t
             elif type == "value":
                  if any(skip in t.upper() for skip in ["MUNIC", "UF", "FONE", "INSCRI", "CNPJ", "CPF", ":"]):
                       continue
                  return t
             elif type == "money":
                  if re.search(r'\d', t) and any(c in t for c in ",."):
                       return t
             elif type == "cnpj":
                  res = self._parse_cnpj(t)
                  if res: return res
                  
         return None

    def _find_text_right(self, items, label_rect, max_dist_x=500, type="any"):
        lx = label_rect.get('x')
        ly = label_rect.get('y')
        lp = label_rect.get('p')
        
        best = None
        min_dist = 9999
        
        for item in items:
            if item.get('p') != lp: continue
            ix = item.get('x')
            iy = item.get('y')
            
            # Check Y alignment (same line, loose tolerance)
            if abs(iy - ly) > 5: continue 
            
            # Check X (to the right)
            if ix > lx and (ix - lx) < max_dist_x:
                dist = ix - lx
                if dist < min_dist:
                     t = item.get('t', '').strip()
                     if not t or len(t) < 2: continue
                     
                     # Validations based on type
                     if type == "name":
                         if len(t) < 3: continue
                         if ".." in t: continue
                         if self._is_garbage(t): continue
                     elif type == "cnpj":
                         res = self._parse_cnpj(t)
                         if res: return res
                     elif type == "value":
                         # More lenient garbage check for values
                         if self._is_garbage(t, strict=False): continue
                     elif type == "money":
                         if not (re.search(r'\d', t) and any(c in t for c in ",.")): continue

                     min_dist = dist
                     best = item
        
        if best:
             val = best.get('t', '').strip()
             if type == "cnpj":
                 m = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', val)
                 if m: return m.group(0)
             return val
        return None

    def _is_garbage(self, text, strict=True):
        """Check if text is garbage (URLs, email, field labels, etc.)"""
        if not text or len(text) < 2:
            return True
        t = text.upper()
        # Skip URLs, emails
        if "HTTP" in t or "WWW." in t or "@" in t:
            return True
        # Skip common field labels
        garbage_keywords = ["ENDERECO", "ENDEREÇO", "CNPJ", "CPF", "BAIRRO", "CEP", 
                           "FONE", "FAX", "INSCRI", "MUNICIPIO", "MUNICÍPIO", 
                           "DATA", "HORA", "NUMERO", "NÚMERO", "SERIE", "SÉRIE",
                           "MODELO", "CHAVE", "PROTOCOLO", "CFOP", "NATUREZA"]
        if any(kw in t for kw in garbage_keywords):
            # Check if it also contains valid values (like "CNPJ: 123...")
            # If so, it's not garbage if we are parsing values, but it IS garbage if looking for a clean name/value separate from label.
            # Usually we extract value separately. So keep as garbage.
            return True

        if strict:
            # Skip if mostly numbers/punctuation
            alpha_count = sum(1 for c in text if c.isalpha())
            # For strict mode (names), ensure enough letters
            # But CNPJ/Money will fail this.
            if len(text) > 5 and alpha_count < len(text) * 0.3:
                return True
        else:
            # Less strict (for values/codes which might be alphanumeric)
            pass
            
        return False
