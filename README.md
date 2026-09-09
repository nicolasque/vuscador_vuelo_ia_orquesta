# ✈️ Vusca Vuelos Orquesta

**Buscador inteligente de vuelos multidestino con orquestación de Agentes de IA, optimizador de vacaciones laborales (PTO) y generador de escalas estratégicas de 1 o más días.**

> 📖 **Documentación para Agentes y Desarrolladores:** Consulta el manual de arquitectura completa y flujo de datos en [AGENTS_HANDBOOK.md](AGENTS_HANDBOOK.md).

---

## 🌟 Características Principales

1. **Optimizador de Vacaciones Laborales (PTO)**:
   - Detección automática de festivos nacionales y autonómicos (usando `holidays`).
   - Cálculo de ratio de eficiencia: maximiza los días continuos de viaje consumiendo el mínimo de días de vacaciones de trabajo (aprovechando puentes y fines de semana).

2. **Especialista en Stopovers de 1+ días**:
   - Diseñado específicamente para rutas multidestino que hacen paradas intermedias de 1 a 3+ días en hubs estratégicos con programas de escala (Turkish Airlines en Estambul, Qatar Airways en Doha, Emirates en Dubái, TAP en Lisboa, etc.).
   - Abarata el precio frente a billetes directos y convierte las escalas en visitas turísticas completas.

3. **Orquestación de Agentes de Inteligencia Artificial**:
   - **Agente PTO & Calendario**: Analiza el calendario laboral y propone las ventanas de viaje más eficientes.
   - **Agente Estratega de Rutas**: Idea y filtra los mejores aeropuertos intermedios según el origen y destino.
   - **Agente Sintetizador & Analista**: Evalúa todos los itinerarios encontrados, los puntúa (0-100), selecciona la mejor opción global, la más barata y la de mayor rendimiento de vacaciones, y genera un informe ejecutivo en Markdown con consejos turísticos y logísticos.
   - Soporte nativo para **Google Gemini** (`gemini-2.5-flash` / `gemini-3.7-flash` con el SDK `google-genai`), con motor heurístico de respaldo automático si se ejecuta sin conexión o sin clave API.

4. **Motor Combinatorio Determinista en Python**:
   - Genera permutaciones estructuradas (ida con stopover, regreso con stopover, ruta base directa).
   - Aplica **poda algorítmica** para unificar tramos atómicos idénticos, reduciendo drásticamente el número de peticiones a las APIs.

5. **Resiliente ante Búsquedas Largas y Limitaciones de APIs**:
   - **Persistencia en SQLite (`vusca_cache.db`)**: Cada tramo consultado queda almacenado en caché con tiempo de vida (TTL).
   - **Pausa y Reanudación de Búsquedas**: Si un proceso largo se cancela o interrumpe, se puede reanudar en cualquier momento con `python -m vusca resume <job_id>` sin repetir llamadas ya realizadas.
   - **Control de Ritmo (Rate Limiter) & Backoff**: Evita sobrepasar las cuotas de las APIs gratuitas y reintenta con retroceso exponencial.

6. **Conectores de APIs y Pool Multi-Proveedor**:
   - **Kiwi / Tequila**: La mejor API gratuita para vuelos multidestino, low-cost y combinaciones de stopovers.
   - **RapidAPI (SkyScrapper / Skyscanner)**: Acceso a motores de Skyscanner a través de RapidAPI.
   - **Duffel Flights API**: Conector directo a la API de aerolíneas con credenciales de prueba gratuitas.
   - **MultiProviderPool**: Agrupa múltiples APIs para rotar peticiones en round-robin, acelerar búsquedas y contar con conmutación por error automática (*failover*) si una API se satura.
   - **Mock Provider Realista**: Simulador incorporado con aerolíneas reales (Iberia, Turkish, Emirates, ANA, etc.) y cálculo dinámico de tarifas para operar 100% offline.

---

## 🚀 Instalación y Puesta en Marcha

### 1. Requisitos Previos
- Python 3.10 o superior.

### 2. Configurar el Entorno Virtual
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno (Opcional)
Copia la plantilla `.env.example` a `.env`:
```bash
cp .env.example .env
```
Edita `.env` para añadir las claves de las APIs que prefieras:
```ini
# Kiwi / Tequila (Recomendada para stopovers y multidestino)
KIWI_API_KEY=tu_api_key_de_kiwi

# RapidAPI - SkyScrapper / Skyscanner API
RAPIDAPI_KEY=tu_api_key_de_rapidapi
RAPIDAPI_HOST=flights-sky.p.rapidapi.com

# RapidAPI - Google Flights API
GOOGLE_FLIGHTS_API_KEY=tu_api_key_de_rapidapi
GOOGLE_FLIGHTS_HOST=google-flights2.p.rapidapi.com

# Kiwi / Tequila
KIWI_API_KEY=tu_api_key_de_kiwi

# Duffel API (token de pruebas)
DUFFEL_API_KEY=duffel_test_...

# Modo de proveedor: "auto", "pool", "google", "rapidapi", "kiwi", "duffel", o "mock"
FLIGHT_PROVIDER=google
```

---

## 💻 Uso desde la Consola

### Modo Asistente Interactivo
Simplemente ejecuta:
```bash
.venv/bin/python -m vusca
```
El asistente interactivo te guiará preguntando origen, destino, días de vacaciones y mes preferido.

### Modo Comando Directo
```bash
# Ejemplo: Búsqueda con Google Flights desde Madrid a Tokio
.venv/bin/python -m vusca search \
  --origin MAD \
  --destination TYO \
  --return-destinations TYO,OSA \
  --days-pto 3 \
  --month 2026-12 \
  --provider google

# O usando el grupo Multi-API (balanceo automático entre Google Flights y Skyscanner):
.venv/bin/python -m vusca search \
  --origin MAD \
  --destination TYO \
  --days-pto 5 \
  --month 2026-10 \
  --provider pool
```

### Opciones de la Línea de Comandos
- `--origins`: Códigos IATA de salida separados por comas (ej. `MAD,BCN`).
- `--destinations`: Códigos IATA de llegada separados por comas (ej. `TYO,OSA`).
- `--origin, -o` / `--destination, -d`: Código IATA único de salida o llegada (retrocompatibilidad).
- `--return-destinations, -rd`: Aeropuertos de regreso alternativos para Open-Jaw (ej. `TYO,OSA`).
- `--stopover-preset`: Presets de escalas recomendadas por IA (`asia_top`, `asia_full`, `gulf`, `europe`, `all_asia`).
- `--date-flexibility, -df`: Margen de flexibilidad en días ($\pm 1$ o $\pm 2$ días) sobre los festivos base sin salirse del límite de días de vacaciones.
- `--dry-run`: Simulación previa que muestra la matriz combinatoria de rutas, consultas atómicas y presupuesto de llamadas a la API sin consumir cuota de red.
- `--days-pto, -p`: Máximo de días laborables de vacaciones a solicitar (ej. `5`).
- `--trip-days, -td`: Duración deseada del viaje en días (ej. `20`).
- `--month, -m`: Mes preferido en formato `AAAA-MM` (ej. `2027-03`).
- `--country`: País para cálculo de festivos (ej. `ES`, `MX`, `US`, etc.).
- `--subdiv`: Región o comunidad autónoma (ej. `MD` para Madrid, `CT` para Cataluña).
- `--min-stopover` / `--max-stopover`: Rango de días de estancia en la ciudad intermedia (por defecto 1 a 3 días).
- `--provider`: `google`, `rapidapi`, `pool`, `kiwi`, `duffel`, `amadeus`, `auto`, `mock`.
- `--output, -out`: Archivo donde exportar el informe final en Markdown.

### Simulación Previa (Dry-Run)
Antes de realizar búsquedas masivas, puedes inspeccionar el presupuesto y las combinaciones con `--dry-run`:
```bash
.venv/bin/python -m vusca search \
  --origins MAD,BCN \
  --destinations TYO,OSA \
  --return-destinations TYO,OSA \
  --stopover-preset asia_top \
  --date-flexibility 1 \
  --month 2027-03 \
  --trip-days 22 \
  --dry-run
```

### Rotación de Claves (Multi-Key)
Para multiplicar tus cuotas mensuales gratuitas, puedes configurar múltiples claves de RapidAPI separadas por comas en tu archivo `.env`:
```ini
GOOGLE_FLIGHTS_API_KEYS=clave1,clave2,clave3
RAPIDAPI_KEYS=clave1,clave2,clave3
```
El motor rotará automáticamente a la siguiente clave si alguna alcanza su límite mensual o recibe un código HTTP 429.

### Reanudar Búsquedas Largas o Interrumpidas
Si detienes una búsqueda o se produce un corte de red, puedes listar los trabajos y reanudarlos al instante:
```bash
# Ver historial de trabajos
.venv/bin/python -m vusca list

# Reanudar un trabajo específico
.venv/bin/python -m vusca resume job_b61e8680

# Ver el informe generado de un trabajo ya completado
.venv/bin/python -m vusca report job_b61e8680
```

---

## 🧪 Ejecutar Tests Automatizados

La suite de pruebas incluye tests para el motor de festivos, la combinatoria de rutas y la persistencia en SQLite:
```bash
.venv/bin/pytest tests/
```
