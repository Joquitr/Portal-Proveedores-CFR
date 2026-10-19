import hashlib, hmac, json, os, secrets, threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('PORTAL_DATA', str(ROOT / '.data')))
LOCK = threading.RLock()
SESSIONS = {}
FLOW = {'Pendiente de revisión': ['Aprobado', 'Observado', 'Rechazado'], 'Observado': ['Pendiente de revisión', 'Rechazado'], 'Aprobado': ['Enviado al ERP'], 'Enviado al ERP': ['Programado', 'Rechazado'], 'Programado': ['Pagado']}
ROLES = ['Proveedor', 'Finanzas', 'Administrador', 'Auditor']
def now(): return datetime.now(timezone.utc).isoformat()
def password(value, salt): return hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
def user(name, email, role, supplier, secret):
    salt = secrets.token_hex(16)
    return dict(id=secrets.token_hex(8), name=name, email=email.lower(), role=role, supplier=supplier, salt=salt, password=password(secret, salt))
def save(db):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / 'portal.tmp'
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2))
    tmp.replace(DATA / 'portal.json')
def load(): return json.loads((DATA / 'portal.json').read_text())
def initialize():
    if (DATA / 'portal.json').exists(): return
    secret = os.environ.get('PORTAL_DEMO_PASSWORD')
    if not secret or len(secret) < 10: raise RuntimeError('Define PORTAL_DEMO_PASSWORD con al menos 10 caracteres para inicializar las cuentas de demostración.')
    save(dict(users=[user(r, r.lower()+'@demo.local', r, 'P001' if r == 'Proveedor' else None, secret) for r in ROLES], suppliers=[dict(id='P001', name='Suministros del Pacífico SAC'), dict(id='P002', name='Servicios Andinos SAC')], orders=[dict(id='OC-1001', supplier='P001', date='2026-10-19', currency='PEN', total=1180, warehouse='Almacén central', status='Abierta', items=[dict(name='Material de oficina', quantity=10, price=100)]), dict(id='OC-1002', supplier='P002', date='2026-10-19', currency='USD', total=590, warehouse='Almacén central', status='Abierta', items=[dict(name='Servicio de mantenimiento', quantity=1, price=500)])], documents=[], payments=[], announcements=[dict(id='1', title='Bienvenidos al portal', body='Registre sus documentos y consulte el avance de su revisión.')], rates=[dict(date='2026-10-19', currency='USD/PEN', value=3.75, source='Dato de demostración')], audit=[], sync=[]))
def audit(db, u, action, entity, detail=''):
    db['audit'].append(dict(date=now(), user=u['email'], action=action, entity=entity, detail=detail))
def public(u): return {k:v for k,v in u.items() if k not in ('password','salt')}
class Error(Exception):
    def __init__(self, message, status=400): self.message, self.status = message, status
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, obj, status=200, cookie=None):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path.startswith('/api/'):
            return self.api()
        data = (ROOT / 'web/index.html').read_bytes()
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
    def do_POST(self): self.api()
    def api(self):
        try:
            with LOCK:
                self.dispatch()
        except Error as e: self.reply(dict(error=e.message), e.status)
        except (ValueError, KeyError, TypeError, InvalidOperation): self.reply(dict(error='Solicitud no válida'),400)
    def dispatch(self):
        db = load(); path = self.path.split('?')[0]
        body = {}
        if self.command == 'POST':
            if self.headers.get('Sec-Fetch-Site') == 'cross-site': raise Error('Origen no permitido',403)
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json': raise Error('Se requiere JSON',415)
            size = int(self.headers.get('Content-Length','0'))
            if size > 65536: raise Error('Solicitud demasiado grande',413)
            body = json.loads(self.rfile.read(size))
        if path == '/api/login' and self.command == 'POST':
            u = next((u for u in db['users'] if u['email'] == str(body.get('email','')).lower()),None)
            if not u or not hmac.compare_digest(u['password'],password(str(body.get('password','')),u['salt'])): raise Error('Credenciales incorrectas',401)
            token=secrets.token_urlsafe(32); SESSIONS[token]=(u['id'],datetime.now().timestamp())
            return self.reply(public(u),cookie='session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
        token = next((v[8:] for v in self.headers.get('Cookie','').split('; ') if v.startswith('session=')), '')
        session = SESSIONS.get(token)
        u = next((u for u in db['users'] if session and u['id']==session[0] and datetime.now().timestamp()-session[1]<28800),None)
        if not u: raise Error('Inicie sesión',401)
        if path == '/api/logout':
            SESSIONS.pop(token,None); return self.reply({},cookie='session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        def allowed(roles):
            if u['role'] not in roles: raise Error('No tiene permiso para esta operación',403)
        def visible(row): return u['role'] != 'Proveedor' or row['supplier']==u['supplier']
        if path == '/api/state' and self.command == 'GET':
            return self.reply(dict(user=public(u), orders=[r for r in db['orders'] if visible(r)], documents=[r for r in db['documents'] if visible(r)], payments=[r for r in db['payments'] if visible(r)], announcements=db['announcements'], suppliers=db['suppliers'] if u['role']=='Administrador' else [], users=[public(x) for x in db['users']] if u['role']=='Administrador' else [], rates=db['rates'] if u['role']!='Proveedor' else [], audit=db['audit'] if u['role'] in ['Auditor','Administrador'] else [], sync=db['sync'] if u['role'] in ['Auditor','Administrador'] else [], flow=FLOW))
        if self.command != 'POST': raise Error('Ruta no encontrada',404)
        if path == '/api/documents':
            allowed(['Proveedor','Finanzas','Administrador'])
            order=next((o for o in db['orders'] if o['id']==body.get('order') and visible(o)),None)
            if not order: raise Error('Orden no disponible',403)
            fields=['type','series','number','date','currency']
            if any(not isinstance(body.get(f),str) or not body[f].strip() for f in fields): raise Error('Complete todos los campos obligatorios')
            if body['type'] not in ['Factura','Boleta','Nota de crédito','Nota de débito']: raise Error('Tipo de documento no válido')
            try: datetime.strptime(body['date'],'%Y-%m-%d')
            except ValueError: raise Error('Fecha no válida')
            subtotal=Decimal(str(body.get('subtotal'))); tax=Decimal(str(body.get('tax')))
            if not subtotal.is_finite() or not tax.is_finite() or subtotal<0 or tax<0 or subtotal+tax<=0: raise Error('Importes no válidos')
            if body['currency']!=order['currency']: raise Error('La moneda debe coincidir con la orden')
            if any(d['supplier']==order['supplier'] and all(d[f].casefold()==body[f].strip().casefold() for f in ['type','series','number']) for d in db['documents']): raise Error('Documento duplicado',409)
            d={f:body[f].strip() for f in fields}; d.update(id=secrets.token_hex(8),order=order['id'],supplier=order['supplier'],subtotal=float(subtotal),tax=float(tax),total=float(subtotal+tax),notes=str(body.get('notes','')),status='Pendiente de revisión',history=[dict(date=now(),user=u['email'],status='Pendiente de revisión',comment='Registro inicial')])
            db['documents'].append(d); audit(db,u,'Registro de documento',d['id'])
        elif path == '/api/transition':
            d=next((d for d in db['documents'] if d['id']==body.get('id') and visible(d)),None)
            if not d: raise Error('Documento no disponible',404)
            target=body.get('status'); comment=str(body.get('comment','')).strip()
            if u['role']=='Proveedor':
                if not (d['status']=='Observado' and target=='Pendiente de revisión'): raise Error('Acción no permitida',403)
            else: allowed(['Finanzas','Administrador'])
            if target not in FLOW.get(d['status'],[]): raise Error('Transición no permitida',409)
            if target in ['Observado','Rechazado','Programado','Pagado','Enviado al ERP'] and not comment: raise Error('Registre un comentario o referencia de sustento')
            d['status']=target; d['history'].append(dict(date=now(),user=u['email'],status=target,comment=comment)); audit(db,u,'Cambio de estado',d['id'],target)
            if target=='Pagado': db['payments'].append(dict(id=secrets.token_hex(8),document=d['id'],supplier=d['supplier'],date=now(),currency=d['currency'],total=d['total'],reference=comment))
        elif path == '/api/users':
            allowed(['Administrador'])
            role=body.get('role'); email=str(body.get('email','')).lower().strip(); name=str(body.get('name','')).strip(); secret=str(body.get('password','')); supplier=body.get('supplier') if role=='Proveedor' else None
            if role not in ROLES or not name or '@' not in email or len(secret)<10: raise Error('Datos de usuario inválidos; contraseña mínima de 10 caracteres')
            if role=='Proveedor' and supplier not in [s['id'] for s in db['suppliers']]: raise Error('Seleccione un proveedor')
            if any(x['email']==email for x in db['users']): raise Error('Usuario duplicado',409)
            db['users'].append(user(name,email,role,supplier,secret)); audit(db,u,'Creación de usuario',email)
        elif path == '/api/sync':
            allowed(['Administrador']); db['sync'].append(dict(date=now(),user=u['email'],result='Simulación completada: órdenes de demostración disponibles. Sin conexión con SAP.')); audit(db,u,'Sincronización simulada','SAP')
        else: raise Error('Ruta no encontrada',404)
        save(db); self.reply(dict(ok=True))
if __name__ == '__main__':
    initialize()
    ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ.get('PORT','8000'))),Handler).serve_forever()
