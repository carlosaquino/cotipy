# Guía de despliegue en Coolify — Cotipy API

Despliegue mediante imagen Docker Hub en un servidor Coolify existente.

---

## Requisitos previos

- Cuenta en [Docker Hub](https://hub.docker.com) con usuario `carlosaquino`
- Servidor Coolify operativo con dominio configurado
- Docker instalado localmente

---

## Paso 1 — Build y push de la imagen a Docker Hub

Desde la raíz del proyecto:

```bash
# Login en Docker Hub
docker login

# Build de la imagen
docker build -t carlosaquino/cotipy:latest .

# Push al registro
docker push carlosaquino/cotipy:latest
```

Para actualizaciones futuras, repetir los mismos tres comandos.

---

## Paso 2 — Crear el recurso en Coolify

1. En Coolify, ir a tu proyecto → **+ New Resource**
2. Seleccionar **Application**
3. En la sección **Docker**, elegir **Docker Image**
4. Completar:
   - **Docker Image**: `carlosaquino/cotipy`  ← sin `:latest`
   - **Docker Image Tag or Hash**: `latest`

> **Importante**: no incluir `:latest` en el campo de imagen. Coolify tiene un campo separado para el tag. Si se pone `carlosaquino/cotipy:latest` en el campo de imagen, el tag queda duplicado como `latest:latest` y falla el deploy.

---

## Paso 3 — General

En **Configuration → General**:

- **Name**: `cotipy`
- **Domains**: `https://cotipy.tu-dominio.com`

---

## Paso 4 — Network (crítico)

En **Configuration → General → Network**:

| Campo | Valor |
|---|---|
| **Ports Exposes** | `8000` |
| **Port Mappings** | *(vacío)* |
| **Network Aliases** | *(vacío)* |

> **Este es el campo más crítico.** Coolify lo pone en `80` por defecto. Si queda en `80`, Traefik intenta conectarse al contenedor por el puerto 80 pero la app escucha en el 8000, causando "Bad Gateway". Debe ser `8000`.

---

## Paso 5 — Variables de entorno

En **Configuration → Environment Variables**, pegar en el área de texto:

```
DATABASE_URL=sqlite+aiosqlite:///./data/cotipy.db
CACHE_TTL_SECONDS=300
ALLOWED_ORIGINS=*
REFRESH_INTERVAL_SECONDS=300
ENABLE_BCP=true
ENABLE_MAXICAMBIOS=true
ENABLE_CAMBIOS_CHACO=true
DEBUG=false
```

Hacer click en **Save All Environment Variables**.

---

## Paso 6 — Almacenamiento persistente

En **Configuration → Persistent Storage → + Add → Volume Mount**:

| Campo | Valor |
|---|---|
| **Name** | `cotipy-data` |
| **Destination Path** | `/app/data` |

> Sin este volumen, la base de datos SQLite se pierde en cada redeploy.

---

## Paso 7 — Deploy

Hacer click en **Redeploy** (o **Deploy** si es la primera vez).

Coolify descarga la imagen de Docker Hub, crea el contenedor con las variables y el volumen configurados, y lo conecta al proxy Traefik automáticamente.

---

## Verificación

Una vez desplegado, verificar en el navegador:

| URL | Resultado esperado |
|---|---|
| `https://cotipy.tu-dominio.com/` | Página de documentación web |
| `https://cotipy.tu-dominio.com/health` | `{"estado":"ok",...}` |
| `https://cotipy.tu-dominio.com/api/v1/cotizaciones` | Cotizaciones en JSON |
| `https://cotipy.tu-dominio.com/docs` | Swagger UI |

---

## Actualizar la imagen en producción

Cada vez que haya cambios en el código:

```bash
# Rebuildar y pushear la nueva imagen
docker build -t carlosaquino/cotipy:latest .
docker push carlosaquino/cotipy:latest
```

Luego en Coolify hacer click en **Redeploy** para que descargue la nueva imagen.

---

## Solución de problemas frecuentes

### Bad Gateway
- Verificar que **Ports Exposes** sea `8000` (no `80`)
- Hacer **Redeploy** completo (no solo Restart)

### Imagen no encontrada (`latest:latest`)
- El campo **Docker Image** debe ser `carlosaquino/cotipy` sin el tag
- El tag va en el campo separado **Docker Image Tag**: `latest`

### La app arranca pero la DB falla
- Verificar que el Volume Mount apunte a `/app/data`
- Verificar que `DATABASE_URL` tenga la ruta `///./data/cotipy.db`

### Logs del contenedor
En Coolify → **Logs** se puede ver la salida de uvicorn en tiempo real.
Para diagnóstico avanzado, desde el servidor via SSH:

```bash
# Ver contenedores corriendo
docker ps

# Ver logs del contenedor
docker logs <nombre-contenedor> --tail 50

# Verificar redes del contenedor
docker inspect <nombre-contenedor> --format '{{json .Config.Labels}}' | tr ',' '\n' | grep "loadbalancer.server.port"
```

El valor de `loadbalancer.server.port` debe ser `8000`.
