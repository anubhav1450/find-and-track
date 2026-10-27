import base64,io,zipfile,unittest
from resume_import import extract_resume

def payload(name,raw):return {'name':name,'content':base64.b64encode(raw).decode()}
def pdf():
    stream=b'BT /F1 12 Tf 72 720 Td (Python Backend Engineer) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    raw=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(raw));raw+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start=len(raw);raw+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets[1:]);raw+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode()
    return raw
class ResumeImportTests(unittest.TestCase):
    def test_pdf_extracts_text_without_modifying_a_workspace(self):self.assertIn('Python Backend Engineer',extract_resume(payload('resume.pdf',pdf()))['text'])
    def test_docx_and_unicode_text(self):
        doc=io.BytesIO()
        with zipfile.ZipFile(doc,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Python APIs</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(extract_resume(payload('r.docx',doc.getvalue()))['text'],'Python APIs')
        self.assertEqual(extract_resume(payload('r.txt','Developer — Python'.encode()))['text'],'Developer — Python')
    def test_bad_empty_and_executable_files_are_rejected(self):
        for body in ({'name':'r.txt','content':'not-base64'},payload('r.exe',b'hello'),payload('r.txt',b'   '),payload('r.pdf',b'not a pdf')):
            with self.assertRaises(ValueError):extract_resume(body)
    def test_zip_bomb_is_rejected(self):
        doc=io.BytesIO()
        with zipfile.ZipFile(doc,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('word/document.xml',b'a'*10_000_001)
        with self.assertRaisesRegex(ValueError,'unpack safely'):extract_resume(payload('r.docx',doc.getvalue()))
