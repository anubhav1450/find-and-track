"""Bounded resume text extraction; does not persist files or infer new facts."""
import base64,io,zipfile
from pathlib import Path
from xml.etree import ElementTree

def extract_resume(body):
    name=body.get('name','');encoded=body.get('content','')
    if not isinstance(name,str) or not isinstance(encoded,str):raise ValueError('Choose a PDF, DOCX or text resume.')
    try:raw=base64.b64decode(encoded,validate=True)
    except Exception:raise ValueError('The uploaded file could not be read.') from None
    if not raw or len(raw)>3_000_000:raise ValueError('Use a resume under 3 MB.')
    ext=Path(name).suffix.lower()
    if ext=='.pdf':
        try:
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(raw),strict=True)
            if reader.is_encrypted:raise ValueError('Use an unlocked PDF resume.')
            if len(reader.pages)>10:raise ValueError('Use a resume of 10 pages or fewer.')
            text='\n'.join(page.extract_text() or '' for page in reader.pages)
        except ImportError:raise ValueError('PDF import is unavailable on this server. Use DOCX or paste your resume text.') from None
        except ValueError:raise
        except Exception:raise ValueError('This PDF could not be read. Try a text-based PDF or DOCX.') from None
    elif ext=='.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(i.file_size for i in archive.infolist())>10_000_000:raise ValueError('This document is too large to unpack safely.')
                xml=archive.read('word/document.xml')
            if b'<!DOCTYPE' in xml:raise ValueError('Use a standard DOCX resume.')
            root=ElementTree.fromstring(xml);ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text='\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p',ns))
        except ValueError:raise
        except Exception:raise ValueError('This DOCX could not be read. Try exporting it again.') from None
    elif ext=='.txt':
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:raise ValueError('Save the text file with UTF-8 encoding.') from None
    else:raise ValueError('Choose a PDF, DOCX or TXT resume.')
    if not text.strip():raise ValueError('No selectable text was found. Paste your resume text instead of an image scan.')
    if len(text)>100_000:raise ValueError('This resume contains too much text.')
    return {'text':text.strip(),'name':Path(name).name,'characters':len(text.strip())}
