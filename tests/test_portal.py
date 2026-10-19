import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
import server

class PortalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); server.DATA=Path(cls.tmp.name)
        os.environ['PORTAL_DEMO_PASSWORD']='test-only-password-123'
        server.initialize()
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.url='http://127.0.0.1:'+str(cls.http.server_port)+'/api/'
    @classmethod
    def tearDownClass(cls): cls.http.shutdown(); cls.http.server_close(); cls.tmp.cleanup()
    def client(self,role):
        c=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call(c,'login',dict(email=role+'@demo.local',password='test-only-password-123'))
        return c
    def call(self,c,path,data=None,status=200):
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        try:
            with c.open(req) as r: result=json.load(r); code=r.status
        except urllib.error.HTTPError as e: result=json.load(e); code=e.code
        self.assertEqual(code,status,result)
        return result
    def test_full_workflow_and_access(self):
        p=self.client('proveedor'); f=self.client('finanzas'); a=self.client('administrador'); auditor=self.client('auditor')
        self.assertEqual([x['id'] for x in self.call(p,'state')['orders']],['OC-1001'])
        doc=dict(order='OC-1001',type='Factura',series='F001',number='1',date='2026-10-19',currency='PEN',subtotal=100,tax=18)
        for change in [dict(currency='USD'),dict(subtotal=-1),dict(series=''),dict(date='bad')]: self.call(p,'documents',doc|change,400)
        self.call(p,'documents',doc|dict(order='OC-1002'),403)
        self.call(p,'documents',doc)
        self.call(p,'documents',doc,409)
        d=self.call(p,'state')['documents'][0]; identifier=d['id']
        def transition(c,status,expected=200): return self.call(c,'transition',dict(id=identifier,status=status,comment='Referencia de validación'),expected)
        transition(p,'Aprobado',403); transition(auditor,'Aprobado',403); transition(f,'Pagado',409)
        transition(f,'Observado'); transition(p,'Pendiente de revisión'); transition(f,'Aprobado'); transition(f,'Enviado al ERP'); transition(f,'Programado'); transition(f,'Pagado'); transition(f,'Rechazado',409)
        result=self.call(p,'state'); self.assertEqual(len(result['documents'][0]['history']),7); self.assertEqual(len(result['payments']),1)
        self.call(p,'users',dict(),403)
        self.call(a,'users',dict(name='Otro proveedor',email='otro@demo.local',password='test-only-password-123',role='Proveedor',supplier='P002'))
        other=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call(other,'login',dict(email='otro@demo.local',password='test-only-password-123'))
        self.assertEqual(self.call(other,'state')['documents'],[])
        transition(other,'Rechazado',404)
        self.call(f,'sync',{},403); self.call(a,'sync',{})
        self.assertTrue(self.call(auditor,'state')['audit'])
        self.call(p,'logout',{}); self.call(p,'state',status=401)
    def test_unauthenticated_and_login(self):
        c=urllib.request.build_opener(); self.call(c,'state',status=401)
        self.call(c,'login',dict(email='proveedor@demo.local',password='incorrect'),401)
    def test_html_routes(self):
        with urllib.request.urlopen(self.url.replace('/api/','/')) as r:
            text=r.read().decode(); self.assertIn('Portal de proveedores',text); self.assertIn('prefers-reduced-motion',text)
if __name__=='__main__': unittest.main()
