# 📘 Vusca Flights Orchestra: Manual de Arquitectura y Guía para Agentes de IA

> **Propósito de este documento:** Este manual está diseñado para que cualquier **Agente de Inteligencia Artificial** o desarrollador que tome el control de este repositorio en cualquier entorno comprenda la arquitectura completa, el flujo de datos de extremo a extremo, la responsabilidad de cada componente y las reglas inviolables del sistema.

---

## 🧭 1. Visión Conceptual de Alto Nivel

Vusca es un **metabuscador inteligente de vuelos** diseñado para resolver el problema de viajar más lejos y más tiempo gastando menos dinero y menos días de vacaciones de trabajo.

### La analogía de la orquesta:
Imagina un equipo de especialistas humanos trabajando juntos:
1. **El Gestor de Recursos Humanos (Agente PTO):** Mira el calendario laboral oficial, encuentra puentes y festivos (ej. 12 de Octubre, Semana Santa) y dice: *"Si pides estos 9 días de vacaciones, en realidad tendrás 16 días seguidos libres"*.
2. **El Estratega de Rutas (Agente de Rutas):** Mira el mapa del mundo y dice: *"En vez de hacer un vuelo de 15 horas directo carísimo, hagamos escala en Santo Domingo (o Estambul, Doha, Bangkok) 2 días. La aerolínea puente abarata el billete, rompemos el cansancio del viaje y conocemos dos países por el precio de uno. Y para no deshacer camino, entraremos por una ciudad y volveremos por otra (Open-Jaw)"*.
3. **El Ingeniero Matemático (Motor Combinatorio):** Genera todas las combinaciones posibles (24.000+ combinaciones) pero se da cuenta de que muchas comparten los mismos vuelos individuales. En vez de hacer 24.000 llamadas a la API (lo que costaría una fortuna y agotaría las cuotas), **poda y deduplica** las consultas en apenas ~500 consultas atómicas únicas de vuelo.
4. **El Operador de Telecomunicaciones (Search Engine & Pool de APIs):** Consulta las APIs de vuelos reales (Google Flights, Skyscanner, etc.) de forma concurrente, con sesiones HTTP persistentes y guardando cada resultado en una **Base de Datos SQLite local**. Si un vuelo ya se consultó, no gasta cuota y responde en 0,001 segundos.
5. **El Analista y Crítico de Viajes (Agente Sintetizador):** Reensambla todas las piezas, evalúa los itinerarios completos con una puntuación de 0 a 100 (precio, días ganados, calidad de las escalas) y redacta un informe ejecutivo con tablas comparativas, justificación de búsqueda y **enlaces directos de reserva a Google Flights para cada tramo**.

---

## 🔄 2. Diagrama de Flujo de Datos de Extremo a Extremo

```mermaid
flowchart TD
    User([Usuario / CLI / Asistente]) --> CLI[vusca.cli.main]
    
    subgraph Fase 1: Inteligencia de Fechas y Festivos
        CLI --> PTOAgent[vusca.agents.PTOAgent]
        PTOAgent --> HolidayEngine[vusca.calendar_pto.HolidayEngine]
        HolidayEngine --> PTOWindows[Ventanas de Vacaciones Optimizadas]
    end

    subgraph Fase 2: Estrategia de Rutas y Hubs
        CLI --> RouteAgent[vusca.agents.RouteAgent]
        RouteAgent --> Hubs[Hubs con Programas de Escala: IST, DOH, SDQ, etc.]
        RouteAgent --> OpenJaw[Estrategia Multiciudad: Entrada y Salida Asimétrica]
    end

    subgraph Fase 3: Combinatoria y Poda Algorítmica
        PTOWindows & Hubs & OpenJaw --> Combinator[vusca.core.RouteCombinator]
        Combinator --> Blueprints[Decenas de Miles de Itinerarios Teóricos]
        Combinator --> TaskPruning[Poda y Deduplicación: ~500 Tareas Atómicas]
    end

    subgraph Fase 4: Consulta Concurrente y Persistencia
        TaskPruning --> SearchEngine[vusca.core.SearchEngine]
        SearchEngine <--> CacheDB[(SQLite: vusca_cache.db)]
        SearchEngine --> ProviderPool[vusca.providers.MultiProviderPool]
        ProviderPool --> GFProvider[Google Flights API / RapidAPI]
        ProviderPool --> SkyProvider[Skyscanner API]
    end

    subgraph Fase 5: Reensamblaje, Filtrado de Confort y Puntuación
        SearchEngine --> Assemble[Reensamblaje de Itinerarios con Precios Reales]
        Assemble --> ComfortFilter[Filtros de Confort: max_stops <= 1, max_scales <= 2]
        ComfortFilter --> RankedItineraries[Itinerarios Viables Calificados 0-100]
    end

    subgraph Fase 6: Síntesis Ejecutiva y Entrega
        RankedItineraries --> SynthesisAgent[vusca.agents.SynthesisAgent]
        SynthesisAgent --> ReportMD[Informe Ejecutivo Markdown con Enlaces Directos]
        ReportMD --> UserView[Visualización en Consola y Guardado en Archivo .md]
    end
```

---

## 🏛️ 3. Desglose en Profundidad por Componente

### 3.1. Directorio `vusca/models/` (Modelos Fuertemente Tipados)
Todo el sistema está gobernado por esquemas Pydantic para garantizar integridad:
- **`calendar.py`**:
  - `HolidayEvent`: Representa un festivo oficial con fecha, nombre y alcance (nacional, autonómico).
  - `PTOWindow`: Intervalo de fechas con `total_days`, `work_days_needed`, `efficiency_ratio` ($días\_totales / días\_laborables$) y `summary`.
- **`flight.py`**:
  - `FlightSegment`: Salto físico de avión entre dos aeropuertos (aerolínea, número de vuelo, horas).
  - `FlightLegOffer`: Billete de un tramo de origen a destino en una fecha dada. Contiene segmentos, escalas, precio y la propiedad calculada `flight_search_url` que genera siempre un enlace funcional a Google Flights.
  - `StopoverDetail`: Ciudad de escala turística (1 a 3 días), días de estancia y fechas.
  - `Itinerary`: Viaje completo de ida y vuelta. Calcula precio acumulado, ratio de vacaciones y almacena `ai_score` (0-100) y `ai_verdict`.
- **`search.py`**:
  - `SearchLegTask`: Unidad de trabajo atómica (`ORIGEN ➔ DESTINO` en `FECHA`). Rastrea estado (`PENDING`, `SUCCESS`, `CACHED`, `FAILED`).
  - `SearchJob`: Registro persistente de la misión de búsqueda completa en base de datos.

### 3.2. Directorio `vusca/calendar_pto/` (Motor de Festivos)
- **`holiday_engine.py`**:
  - Utiliza la librería oficial `holidays` de Python para España (`ES`) y comunidades autónomas (ej. `MD` Madrid, `PV` País Vasco).
  - `find_optimal_windows(...)`: Algoritmo de ventana deslizante que evalúa periodos en el calendario. Cuenta fines de semana y festivos para priorizar las fechas que maximizan el tiempo libre requiriendo el menor número de días de vacaciones laborables.
  - `generate_flexible_variations(...)`: Genera variaciones deterministas con desplazamiento de $\pm 1$ o $\pm 2$ días (Date Jitter) para encontrar tarifas de avión más baratas en vísperas o días adyacentes.

### 3.3. Directorio `vusca/agents/` (Inteligencia de Decisión y Análisis)
- **`pto_agent.py` (`PTOAgent`)**:
  - Orquesta la selección de fechas.
  - `get_strategy_rationale(...)`: Genera la justificación formal de por qué esas fechas se pasan al motor (festivos detectados, rendimiento vacacional máximo).
- **`route_agent.py` (`RouteAgent`)**:
  - Almacena la base de datos de conocimiento `GLOBAL_HUBS` (Estambul, Doha, Dubái, Santo Domingo, Bangkok, etc.) con sus programas oficiales de stopover (hotel gratuito o paquetes con descuento) y alianzas aéreas.
  - `get_hub_strategy_explanation(...)`: Explica por qué cada hub reduce el coste del corredor y qué aerolíneas puente operan.
  - `get_open_jaw_strategy(...)`: Redacta dinámicamente el valor de la ruta multiciudad según el destino (ej. Japón = ahorro de Shinkansen; Colombia = recorrido lineal norte-sur sin retroceder a Bogotá).
- **`synthesis_agent.py` (`SynthesisAgent`)**:
  - `evaluate_and_rank(...)`: Algoritmo de scoring compuesto:
    - Precio (0–40 pts).
    - Rendimiento vacacional / Ratio PTO (0–35 pts).
    - Calidad y duración del stopover (0–25 pts).
  - `generate_final_report(...)`: Genera el informe final consolidado (con Gemini o heurístico). El formato incluye: justificación de búsqueda, podio de opciones destacadas, tablas comparativas separadas por origen (ej. Madrid vs Bilbao), desglose tramo a tramo con enlaces directos de Google Flights y consejos logísticos de equipaje y stopover.
- **`llm_client.py` (`GeminiClient`)**:
  - Cliente para la API de Google Gemini (`google-genai`). Si la clave `GEMINI_API_KEY` no está configurada, degrada de forma transparente y sin errores a los motores heurísticos de reserva.

### 3.4. Directorio `vusca/core/` (Cerebro Algorítmico y Base de Datos)
- **`combinator.py` (`RouteCombinator`)**:
  - Genera las permutaciones de viajes posibles considerando: orígenes múltiples, destinos de llegada, destinos de regreso Open-Jaw, escalas de ida (`outbound_stopovers`), escalas de vuelta (`return_stopovers`) y ventanas de fecha.
  - **Poda algorítmica**: Agrupa las necesidades de vuelo en un conjunto único de `SearchLegTask`.
  - `assemble_itineraries(...)`: Cruza las ofertas de vuelo reales obtenidas para cada tramo y arma los itinerarios finales aplicando los filtros estrictos de confort (`max_stops_per_leg <= 1` y `max_scales_per_direction <= 2`).
- **`db.py` (`DatabaseManager`)**:
  - Base de datos SQLite local (`vusca_cache.db`) con modo **WAL (Write-Ahead Logging)** y timeout de 30s para evitar bloqueos concurrentes.
  - Almacena tramos consultados en la tabla `cached_legs` (caché persistente de por vida o según TTL).
  - Almacena trabajos en `search_jobs` para poder pausar y reanudar búsquedas largas en cualquier momento.
- **`search_engine.py` (`SearchEngine`)**:
  - Orquesta la ejecución de las consultas.
  - Consulta primero la base de datos local SQLite (`if cached is not None:`). Si el tramo ya existe (incluso si la lista de vuelos está vacía porque no hay frecuencias en esa fecha), lo recupera sin tocar la API de red.
  - Si es nuevo, lo envía al pool de proveedores concurrentemente usando `ThreadPoolExecutor(max_workers=4)`.

### 3.5. Directorio `vusca/providers/` (Conectores de Aerolíneas y APIs)
- **`base.py`**: Interfaz abstracta `BaseFlightProvider` con método `search_leg(origin, destination, date) -> List[FlightLegOffer]`.
- **`google_flights.py` (`GoogleFlightsProvider`)**:
  - Conector para la API de RapidAPI `google-flights2.p.rapidapi.com`.
  - Mantiene una sesión HTTP con `requests.Session()` y pool de conexiones Keep-Alive (`pool_connections=20, pool_maxsize=30`) para evitar reconexiones TCP/TLS lentas.
  - Soporta rotación de claves en caso de error 429 (`GOOGLE_FLIGHTS_API_KEYS`).
- **`pool.py` (`MultiProviderPool`)**:
  - Agrupa múltiples proveedores con balanceo de carga automático y conmutación por error (failover) si una API agota su cuota mensual.
- **`skyscanner4.py`, `rapidapi.py`, `amadeus.py`, `kiwi.py`, `mock.py`**: Conectores alternativos y simulador offline.

### 3.6. Directorio `vusca/cli/` (Interfaz de Terminal)
- **`main.py`**:
  - CLI completa implementada con `argparse` y decorada con `rich` (tablas, paneles de justificación, barras de progreso y renderizado Markdown).
  - Comandos:
    - `python -m vusca search ...` (búsqueda completa).
    - `python -m vusca resume <job_id>` (reanudar trabajo interrumpido).
    - `python -m vusca list` (ver historial de búsquedas y estados).
    - `python -m vusca report <job_id>` (volver a ver el informe generado).

---

## 📋 4. Guía Operativa para un Nuevo Entorno o Nuevo Agente de IA

Si trasladas este proyecto a otra máquina, contenedor o sesión de desarrollo, sigue rigurosamente estos pasos:

### Paso 1: Configurar el Entorno Python
```bash
# Crear el entorno virtual si no existe
python3 -m venv .venv

# Activar entorno
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Paso 2: Variables de Entorno (`.env`)
Asegúrate de que existe un archivo `.env` en la raíz del proyecto con tus credenciales activas:
```ini
# Clave principal de RapidAPI (Google Flights y Skyscanner)
RAPIDAPI_KEY="tu_rapidapi_key_aqui"
GOOGLE_FLIGHTS_API_KEY="tu_rapidapi_key_aqui"

# Opcional: Rotación multi-clave separada por comas si tienes varias cuentas
# GOOGLE_FLIGHTS_API_KEYS="clave1,clave2"

# Opcional: Gemini API Key (para redacción con LLM; si falta, opera en modo heurístico)
GEMINI_API_KEY=""

# Configuración de búsqueda por defecto
DEFAULT_FLIGHT_PROVIDER="google"
```

### Paso 3: Ejecutar la Suite de Verificación
Antes de tocar código o lanzar búsquedas masivas, comprueba que todos los tests unitarios pasen:
```bash
.venv/bin/pytest
# Debe devolver: 19 passed
```

### Paso 4: Comandos Clave de Búsqueda
```bash
# 1. Simulación previa (Dry-Run): Valida combinatoria sin gastar cuota de API
.venv/bin/python -m vusca search \
  --origins MAD,BIO \
  --destinations BOG \
  --return-destinations BOG,MDE,CTG \
  --stopovers SDQ,MIA \
  --month 2026-10 \
  --days-pto 10 \
  --date-flexibility 1 \
  --dry-run

# 2. Búsqueda real de alta precisión:
.venv/bin/python -m vusca search \
  --origins MAD,BIO \
  --destinations BOG \
  --return-destinations BOG,MDE,CTG \
  --stopovers SDQ,MIA,CUN,PTY,LIS \
  --month 2026-10 \
  --days-pto 10 \
  --date-flexibility 1 \
  --max-scales 2 \
  --max-stops-per-leg 1 \
  --provider google

# 3. Ver historial de trabajos anteriores:
.venv/bin/python -m vusca list

# 4. Reanudar o ver informe de un trabajo anterior:
.venv/bin/python -m vusca resume job_df80cc87
```

---

## ⚠️ 5. Reglas Inviolables para Agentes de IA que Modifiquen el Código

1. **Nunca omitir la comprobación de caché (`if cached is not None:`):**
   - Una ruta válida puede tener 0 ofertas de vuelo (ej. no hay vuelo directo un martes concreto). Almacenar `[]` en la caché es vital para que la API no vuelva a consultar esa misma ruta inútilmente en cada iteración.
2. **Respetar las Reglas de Confort de Vuelo:**
   - `max_stops_per_leg <= 1`: Ningún billete de un solo tramo debe admitir más de 1 escala técnica.
   - `max_scales_per_direction <= 2`: Cada trayecto (ida o vuelta) puede tener como máximo 1 escala turística de varios días + 1 escala técnica de conexión.
3. **Mantener siempre los Enlaces Directos de Reserva:**
   - Cada tramo de vuelo en los informes debe incluir el enlace directo `leg.flight_search_url` hacia Google Flights para que el usuario pueda reservar de inmediato.
4. **Explicar siempre el "Por qué se ha hecho de esta manera":**
   - Los informes deben comenzar siempre justificando la estrategia de calendario (festivos aprovechados), la elección de los hubs y la lógica de la ruta multiciudad (Open-Jaw).
5. **No hardcodear textos específicos de un destino en la lógica general:**
   - Por ejemplo, no mencionar el tren Shinkansen o Japón cuando la búsqueda sea a Colombia o Tailandia. Utilizar los métodos contextuales de `RouteAgent` (`get_open_jaw_strategy`).
6. **Mantener la Suite de Tests al 100%:**
   - Cualquier cambio en modelos, agentes o combinatoria debe verificarse con `pytest`. Si se añaden capacidades nuevas, debe añadirse un test en `tests/`.
