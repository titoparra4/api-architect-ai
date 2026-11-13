# Revisión de seguridad de API — claims-service

> **Sistema:** claims-service 0.3.0 · **Alcance:** `sample-app/src/*.js`, `openapi.yaml`, `package.json`
> · **Fecha:** 2026-11-13 · **Método:** revisión estática, solo lectura. No se ejecutó código ni se
> realizaron pruebas dinámicas (no hay entorno aprobado). **No es un pentest ni una certificación.**

## 1. Resumen

> ⚠️ Hallazgo crítico sin resolver: **SEC-001** (inyección SQL en `GET /claims`).

| Severidad | Nº |
|---|---:|
| Critical | 1 |
| High | 4 |
| Medium | 3 |
| Low | 0 |
| Informational | 1 |

La API autentica con JWT, pero la validación del token es incompleta y la autorización a nivel de
objeto y de propiedad falla en dos de las cuatro operaciones. Combinados, los hallazgos permiten a
cualquier usuario autenticado leer y crear reclamaciones de otros tenants. No se puede afirmar que
la API sea segura; ver alcance y limitaciones.

## 2. Alcance, evidencias y limitaciones

| Elemento | Ubicación | Revisado |
|---|---|---|
| Middleware de autenticación | `src/auth.js` | completo |
| Rutas y acceso a datos | `src/routes/claims.js` | completo |
| Configuración HTTP (CORS, body, errores) | `src/app.js` | completo |
| Contrato | `openapi.yaml` | completo |

No revisado: configuración del IdP, variables de entorno, gateway, infraestructura, logs, versión
instalada de dependencias (no hay lockfile).

## 3. Modelo de autenticación

| Tipo de consumidor | Mecanismo | Validación | Evidencia | Valoración |
|---|---|---|---|---|
| Todos | JWT con secreto compartido (`jsonwebtoken`) | Firma sí; `exp` ignorado; `iss`/`aud` no comprobados | `src/auth.js:10` | Insuficiente |

Checklist JWT:

| Control | Estado | Evidencia |
|---|---|---|
| Firma verificada | Verified present | `jwt.verify(...)` en `src/auth.js:10` |
| Algoritmos fijados explícitamente | Verified missing (mitigado parcialmente) | Sin opción `algorithms`. `jsonwebtoken` ≥ 9 restringe por defecto a HS* con secretos y rechaza `none`; **versión instalada no verificada** → Requires validation |
| `iss` | Verified missing | Sin opción `issuer` |
| `aud` | Verified missing | Sin opción `audience` |
| `exp` | Verified missing | `ignoreExpiration: true` |
| Origen de la clave | Riesgo | Secreto de respaldo literal en `src/auth.js:3` (valor omitido) |
| Token solo en cabecera | Verified missing | También acepta `?token=` (`src/auth.js:7`) |

## 4. Modelo de autorización

| Nivel | Mecanismo | Evidencia | Brechas |
|---|---|---|---|
| Objeto (BOLA) | Filtro `tenant_id` manual por handler | `DELETE` filtra (`claims.js:34`); `GET /:id` no (`claims.js:18`) | SEC-002 |
| Propiedad | Ninguno: el body completo se vuelca a columnas | `claims.js:24-29` | SEC-003 |
| Función | No hay funciones administrativas | — | No aplicable en el alcance |
| Aislamiento de tenant | `tenantId` del token, excepto en `POST` (acepta `tenant_id` del body) | `claims.js:24` | SEC-003 |

## 5. Cobertura OWASP API Security Top 10 (2023)

| ID | Riesgo | Resultado | Notas |
|---|---|---|---|
| API1 | Broken Object Level Authorization | SEC-002 | |
| API2 | Broken Authentication | SEC-004, SEC-005, SEC-006 | |
| API3 | Broken Object Property Level Authorization | SEC-003 | Mass assignment |
| API4 | Unrestricted Resource Consumption | SEC-009 (Informational aquí; detallado como SCL-001 en la evaluación de arquitectura) | Sin paginación; body de 50 MB |
| API5 | Broken Function Level Authorization | Sin hallazgos en el alcance | No existen rutas administrativas |
| API6 | Unrestricted Access to Sensitive Business Flows | No evaluado | Requiere conocer los flujos de negocio |
| API7 | Server-Side Request Forgery | Sin hallazgos en el alcance | No hay peticiones salientes a URLs del cliente |
| API8 | Security Misconfiguration | SEC-007, SEC-008 | CORS, trazas de error |
| API9 | Improper Inventory Management | Ver DOC-001 (evaluación de arquitectura) | `DELETE` no documentado |
| API10 | Unsafe Consumption of APIs | No aplicable | No se consumen APIs de terceros |

Inyección (fuera del Top 10 de API pero crítica): SEC-001.

## 6. Otros controles

| Control | Estado |
|---|---|
| CORS | Refleja cualquier origen con `credentials: true` (SEC-007) |
| TLS | No evaluable (terminación fuera del código) |
| Rate limiting | No localizado en código; puede existir en gateway → Requires validation |
| Validación de entrada | Inexistente (SEC-001, SEC-003) |
| Gestión de secretos | Secreto de respaldo literal (SEC-005) |
| Auditoría | No localizada |
| Errores | Devuelven `stack` (SEC-008) |

## 7. Hallazgos

```text
Finding ID:            SEC-001
Category:              Injection (SQL)
Title:                 Inyección SQL en el filtro status de GET /claims
Severity:              Critical
Confidence:            High
Location:              src/routes/claims.js:11
Evidence:              "... AND status = '" + status + "'" con status = req.query.status
Technical impact:      Cualquier usuario autenticado altera la consulta y evita el filtro de tenant.
Business impact:       Exposición de reclamaciones de todos los clientes; posible manipulación de datos.
Recommended solution:  Parámetro enlazado ($2) + lista blanca de valores de status.
Alternative solutions: ORM/query builder; validación por esquema previa al handler.
Estimated effort:      Small
Verification method:   Test unitario con "OPEN' OR '1'='1" → 400; regla estática en CI.
Status:                Confirmed
```

```text
Finding ID:            SEC-002
Category:              Authorization — OWASP API1:2023
Title:                 GET /claims/{id} no comprueba el tenant
Severity:              High
Confidence:            High
Location:              src/routes/claims.js:18
Evidence:              SELECT * FROM claims WHERE id = $1 (sin tenant_id)
Technical impact:      Lectura de reclamaciones de otros tenants conociendo el ID.
Business impact:       Fuga de datos personales entre clientes.
Recommended solution:  AND tenant_id = $2 con el tenant del token; 404 si no existe.
Alternative solutions: Row-level security en PostgreSQL.
Estimated effort:      Small
Verification method:   Token del tenant B pide reclamación del tenant A → 404 sin datos.
Status:                Confirmed
```

```text
Finding ID:            SEC-003
Category:              Authorization — OWASP API3:2023 (mass assignment)
Title:                 POST /claims acepta tenant_id y columnas arbitrarias del body
Severity:              High
Confidence:            High
Location:              src/routes/claims.js:24
Evidence:              { ...req.body, tenant_id: req.body.tenant_id || req.user.tenantId }
Technical impact:      Creación de registros en otros tenants y escritura de campos protegidos.
Business impact:       Integridad de datos comprometida.
Recommended solution:  DTO con campos permitidos; tenant siempre desde el token.
Alternative solutions: JSON Schema con additionalProperties: false.
Estimated effort:      Small
Verification method:   POST con tenant_id ajeno → 400/422; nada persistido.
Status:                Confirmed
```

```text
Finding ID:            SEC-004
Category:              Authentication — OWASP API2:2023
Title:                 Expiración ignorada; iss y aud sin validar
Severity:              High
Confidence:            High
Location:              src/auth.js:10
Evidence:              jwt.verify(token, JWT_SECRET, { ignoreExpiration: true })
Technical impact:      Tokens robados o antiguos válidos indefinidamente.
Business impact:       Ventana de secuestro de cuentas ilimitada.
Recommended solution:  Quitar ignoreExpiration; fijar issuer, audience y algorithms; claves asimétricas (JWKS).
Alternative solutions: Validación en gateway + autorización en el servicio.
Estimated effort:      Small
Verification method:   Tokens caducados / iss o aud erróneos → 401.
Status:                Confirmed
```

```text
Finding ID:            SEC-005
Category:              Secrets management
Title:                 Secreto JWT de respaldo codificado en el fuente
Severity:              High
Confidence:            Medium
Location:              src/auth.js:3
Evidence:              Valor literal usado si falta JWT_SECRET (valor omitido en este informe).
Technical impact:      Falsificación de tokens en cualquier entorno sin la variable.
Business impact:       Bypass total de autenticación en ese entorno.
Recommended solution:  Fallar al arrancar si falta la clave; gestor de secretos; rotación.
Alternative solutions: Verificación con claves públicas del IdP.
Estimated effort:      Small
Verification method:   Confirmar configuración por entorno con el responsable; test de arranque sin variable.
Status:                Requires validation
```

```text
Finding ID:            SEC-006
Category:              Authentication
Title:                 Token aceptado en query string
Severity:              Medium
Confidence:            High
Location:              src/auth.js:7
Evidence:              header.replace('Bearer ', '') || req.query.token
Technical impact:      Tokens en logs de acceso y proxies.
Business impact:       Exposición de credenciales.
Recommended solution:  Solo cabecera Authorization.
Alternative solutions: —
Estimated effort:      Small
Verification method:   Petición con ?token= → 401.
Status:                Confirmed
```

```text
Finding ID:            SEC-007
Category:              Security misconfiguration — CORS
Title:                 CORS refleja cualquier origen con credenciales
Severity:              Medium
Confidence:            High
Location:              src/app.js:7
Evidence:              cors({ origin: true, credentials: true })
Technical impact:      Impacto limitado hoy (auth por cabecera, no cookies); alto si se introducen cookies.
Business impact:       Riesgo latente.
Recommended solution:  Lista blanca de orígenes por entorno.
Alternative solutions: Desactivar CORS si no hay clientes de navegador.
Estimated effort:      Small
Verification method:   Preflight desde origen no permitido sin Access-Control-Allow-Origin.
Status:                Confirmed
```

```text
Finding ID:            SEC-008
Category:              Security misconfiguration — error handling
Title:                 Trazas de pila devueltas al cliente
Severity:              Medium
Confidence:            High
Location:              src/app.js:14
Evidence:              res.status(500).json({ message: err.message, stack: err.stack })
Technical impact:      Revela rutas, versiones y errores SQL (facilita SEC-001).
Business impact:       Facilita ataques.
Recommended solution:  Problem Details (RFC 9457) con traceId; detalle solo en logs.
Alternative solutions: —
Estimated effort:      Small
Verification method:   Error 500 forzado en test sin stack en la respuesta.
Status:                Confirmed
```

```text
Finding ID:            SEC-009
Category:              Unrestricted resource consumption — OWASP API4:2023
Title:                 Listado sin límite y body de 50 MB (ver SCL-001)
Severity:              Informational
Confidence:            High
Location:              src/routes/claims.js:8-15; src/app.js:8
Evidence:              SELECT * sin LIMIT; express.json({ limit: '50mb' })
Technical impact:      Agotamiento de memoria/latencia (detallado en la evaluación de escalabilidad).
Business impact:       Degradación para todos los tenants.
Recommended solution:  Paginación con límite máximo; límite de body acorde al payload real.
Alternative solutions: —
Estimated effort:      Medium
Verification method:   limit=101 → 400; body > límite → 413.
Status:                Confirmed
```

## 8. Plan de remediación

| Prioridad | Hallazgo | Acción | Esfuerzo | Verificación | Rol responsable |
|---|---|---|---|---|---|
| Ahora | SEC-001 | Parametrizar SQL + lista blanca | Small | Tests de inyección | Backend |
| Ahora | SEC-002, SEC-003 | Scoping por tenant + DTO | Small | Tests cross-tenant | Backend |
| Ahora | SEC-004, SEC-005, SEC-006 | Endurecer validación JWT y gestión de clave | Small | Tests de token | Backend + Plataforma |
| Siguiente | SEC-007, SEC-008 | CORS restringido; Problem Details | Small | Tests de contrato | Backend |

## 9. Pruebas de regresión de seguridad

| Test ID | Hallazgo | Escenario | Resultado esperado | Entorno |
|---|---|---|---|---|
| TC-SEC-001 | SEC-001 | `status=OPEN' OR '1'='1` | 400, sin datos | CI (componente) |
| TC-SEC-002 | SEC-002 | Tenant B lee reclamación de A | 404 | CI |
| TC-SEC-003 | SEC-003 | POST con `tenant_id` ajeno | 400/422, nada persistido | CI |
| TC-SEC-004 | SEC-004 | Token caducado / `aud` erróneo / `iss` erróneo | 401 | CI |
| TC-SEC-005 | SEC-006 | Token en `?token=` | 401 | CI |
| TC-SEC-006 | SEC-008 | Error forzado | 500 sin `stack` | CI |

## 10. Supuestos y riesgos remanentes

- ASM-001: las reclamaciones contienen datos personales.
- Riesgo remanente: controles en gateway/infraestructura no revisados (rate limiting, TLS, WAF).
- No ejecutado: pruebas dinámicas (sin entorno aprobado); `npm install` / scripts del repositorio.
