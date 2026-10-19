# Portal de Proveedores CFR

Prototipo funcional basado en el alcance del 19 de octubre de 2026. Requiere Python 3.11 o posterior, sin dependencias externas.

## Ejecutar

Desde el checkout:

```bash
export PORTAL_DEMO_PASSWORD='una-contraseña-local-de-al-menos-10-caracteres'
python server.py
```

La contraseña se requiere solo para inicializar `.data/portal.json`. No guardar contraseñas reales en el repositorio. Cuentas iniciales: `proveedor@demo.local`, `finanzas@demo.local`, `administrador@demo.local`, `auditor@demo.local`. Todas reciben la contraseña indicada. El servidor escucha en la interfaz local, puerto 8000; `HOST`, `PORT` y `PORTAL_DATA` son configurables. Detener con Ctrl+C. Los datos JSON permanecen entre reinicios y las sesiones expiran tras ocho horas o al reiniciar.

## Validar

```bash
python -m unittest discover -s tests -v
```

Incluye permisos en servidor, aislamiento por proveedor, validaciones, transiciones, historial, pagos, administración y auditoría. Navegación mediante rutas de fragmento con soporte del historial del navegador y preferencia de movimiento reducido.

## Límites

Es un prototipo local, no desplegar públicamente sin endurecimiento de seguridad y HTTPS. SAP está simulado; la acción de sincronización registra una comprobación sobre las órdenes semilla, sin intercambio real. Los estados ERP y pago son registros manuales. No ejecuta transferencias, validación SUNAT, adjuntos, correos ni recuperación de contraseña. Los importes y tipos de cambio semilla son ficticios. No permite editar documentos observados; pueden reenviarse con comentario.

Antes de producción: base de datos transaccional, integración SAP, custodia de adjuntos, gestión completa de credenciales, limitación de intentos de acceso, monitoreo, respaldos y pruebas de seguridad. Confirmar tipos de documento, impuestos, responsables y fuente oficial de pagos con el negocio.
