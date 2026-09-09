"""AI Agent specialized in Route Strategy, Airline Hubs, and Strategic Multi-day Stopovers."""

from typing import List, Dict, Tuple, Optional
from vusca.agents.llm_client import GeminiClient


# Knowledge base of strategic airline hubs with official stopover programs
GLOBAL_HUBS: Dict[str, Dict[str, str]] = {
    "IST": {
        "name": "Estambul",
        "country": "Turquía",
        "corridors": ["EUROPE_ASIA", "EUROPE_AFRICA", "AMERICA_ASIA"],
        "airline": "Turkish Airlines",
        "description": "Puente entre Oriente y Occidente. Programa de stopover de Turkish Airlines con hotel gratis para escalas de más de 20h.",
    },
    "DOH": {
        "name": "Doha",
        "country": "Catar",
        "corridors": ["EUROPE_ASIA", "EUROPE_OCEANIA", "AMERICA_ASIA"],
        "airline": "Qatar Airways",
        "description": "Hub ultra-moderno con paquetes Discover Qatar con hoteles 4* y 5* desde 14 USD la noche.",
    },
    "DXB": {
        "name": "Dubái",
        "country": "Emiratos Árabes",
        "corridors": ["EUROPE_ASIA", "EUROPE_OCEANIA", "EUROPE_AFRICA"],
        "airline": "Emirates",
        "description": "Capital del lujo, rascacielos y compras. Ideal para una parada de 2 días camino al Sudeste Asiático o Japón.",
    },
    "FCO": {
        "name": "Roma",
        "country": "Italia",
        "corridors": ["EUROPE_ASIA", "AMERICA_EUROPE", "AMERICA_ASIA"],
        "airline": "ITA Airways",
        "description": "Una de las cunas de la historia occidental. Añadir 2 días en Roma convierte cualquier viaje en una experiencia cultural inolvidable.",
    },
    "CDG": {
        "name": "París",
        "country": "Francia",
        "corridors": ["EUROPE_ASIA", "EUROPE_AMERICA", "AMERICA_ASIA"],
        "airline": "Air France",
        "description": "El gran hub de SkyTeam en Europa. Perfecto para combinar arte, gastronomía y paseos junto al Sena.",
    },
    "AMS": {
        "name": "Ámsterdam",
        "country": "Países Bajos",
        "corridors": ["EUROPE_ASIA", "EUROPE_AMERICA"],
        "airline": "KLM",
        "description": "Hub compacto y muy eficiente. Canales, museos y excelente conexión directa en tren al aeropuerto Schiphol.",
    },
    "LIS": {
        "name": "Lisboa",
        "country": "Portugal",
        "corridors": ["EUROPE_AMERICA", "EUROPE_AFRICA"],
        "airline": "TAP Air Portugal",
        "description": "Programa oficial TAP Stopover de hasta 10 días sin sobrecoste en el billete entre Europa y América.",
    },
    "SIN": {
        "name": "Singapur",
        "country": "Singapur",
        "corridors": ["EUROPE_OCEANIA", "ASIA_OCEANIA", "EUROPE_ASIA"],
        "airline": "Singapore Airlines",
        "description": "Considerado el mejor aeropuerto del mundo (Jewel). Escala fascinante entre jardines futuristas y gastronomía hawker.",
    },
    "BKK": {
        "name": "Bangkok",
        "country": "Tailandia",
        "corridors": ["EUROPE_ASIA", "EUROPE_OCEANIA"],
        "airline": "Thai Airways",
        "description": "Gran puerta de entrada al Sudeste Asiático. Templos dorados, mercados nocturnos y comida callejera espectacular.",
    },
    "ATH": {
        "name": "Atenas",
        "country": "Grecia",
        "corridors": ["EUROPE_ASIA", "EUROPE_MIDDLE_EAST"],
        "airline": "Aegean",
        "description": "Cuna de la filosofía y el Partenón. Excelente parada intermedia entre el Mediterráneo y Oriente Próximo.",
    },
    "JFK": {
        "name": "Nueva York",
        "country": "EE. UU.",
        "corridors": ["EUROPE_AMERICA", "EUROPE_LATAM", "AMERICA_ASIA"],
        "airline": "Delta / American",
        "description": "La Gran Manzana. Ideal para una escala de compras, espectáculos de Broadway y skyline icónico.",
    },
    "MIA": {
        "name": "Miami",
        "country": "EE. UU.",
        "corridors": ["EUROPE_LATAM", "AMERICA_LATAM"],
        "airline": "American Airlines",
        "description": "Puerta de conexión natural entre Europa, Norteamérica y Latinoamérica.",
    },
    "BOG": {
        "name": "Bogotá",
        "country": "Colombia",
        "corridors": ["EUROPE_LATAM", "NORTH_SOUTH_AMERICA"],
        "airline": "Avianca",
        "description": "Hub neurálgico en Sudamérica. Excelente para conectar hacia el cono sur o el Caribe.",
    },
    "KUL": {
        "name": "Kuala Lumpur",
        "country": "Malasia",
        "corridors": ["EUROPE_ASIA", "EUROPE_OCEANIA"],
        "airline": "Malaysia Airlines / AirAsia",
        "description": "Hub dinámico con torres Petronas y gastronomía multicultural. Tarifas low-cost hacia Japón.",
    },
    "ICN": {
        "name": "Seúl",
        "country": "Corea del Sur",
        "corridors": ["EUROPE_ASIA", "AMERICA_ASIA"],
        "airline": "Korean Air / Asiana",
        "description": "K-Culture, templos y rascacielos. Escala ideal a solo 2 horas de vuelo de Tokio y Osaka.",
    },
    "TPE": {
        "name": "Taipéi",
        "country": "Taiwán",
        "corridors": ["EUROPE_ASIA", "AMERICA_ASIA"],
        "airline": "EVA Air / China Airlines",
        "description": "Mercados nocturnos legendarios y rascacielos Taipei 101. Excelente trampolín hacia Japón.",
    },
    "HKG": {
        "name": "Hong Kong",
        "country": "Hong Kong",
        "corridors": ["EUROPE_ASIA", "EUROPE_OCEANIA"],
        "airline": "Cathay Pacific",
        "description": "Skyline icónico sobre Victoria Harbour y gastronomía cantonesa con estrella Michelin asequible.",
    },
    "HAN": {
        "name": "Hanói",
        "country": "Vietnam",
        "corridors": ["EUROPE_ASIA"],
        "airline": "Vietnam Airlines",
        "description": "Historia colonial, bahía de Halong cercana y cultura de café. Muy económico para pasar 2 días.",
    },
    "SGN": {
        "name": "Ho Chi Minh",
        "country": "Vietnam",
        "corridors": ["EUROPE_ASIA"],
        "airline": "Vietnam Airlines / VietJet",
        "description": "Metrópolis vibrante del sur de Vietnam con conexiones directas a Tokio y precios muy bajos.",
    },
    "AUH": {
        "name": "Abu Dabi",
        "country": "Emiratos Árabes",
        "corridors": ["EUROPE_ASIA", "EUROPE_OCEANIA"],
        "airline": "Etihad Airways",
        "description": "Gran Mezquita Sheikh Zayed y Museo Louvre Abu Dabi. Conexión de lujo directa con Narita.",
    },
    "HEL": {
        "name": "Helsinki",
        "country": "Finlandia",
        "corridors": ["EUROPE_ASIA"],
        "airline": "Finnair",
        "description": "La ruta polar más corta y rápida entre Europa y Japón, minimizando horas de vuelo totales.",
    },
    "FRA": {
        "name": "Frankfurt",
        "country": "Alemania",
        "corridors": ["EUROPE_ASIA", "EUROPE_AMERICA"],
        "airline": "Lufthansa",
        "description": "Mayor hub de Europa Central con frecuencias diarias a Tokio Haneda.",
    },
    "MUC": {
        "name": "Múnich",
        "country": "Alemania",
        "corridors": ["EUROPE_ASIA", "EUROPE_AMERICA"],
        "airline": "Lufthansa",
        "description": "Hub bávaro moderno, eficiente y con conexiones de primera clase hacia Japón.",
    },
    "ZRH": {
        "name": "Zúrich",
        "country": "Suiza",
        "corridors": ["EUROPE_ASIA"],
        "airline": "SWISS",
        "description": "Hub alpino de alta precisión con vuelos directos diarios a Tokio Narita.",
    },
    "PTY": {
        "name": "Ciudad de Panamá",
        "country": "Panamá",
        "corridors": ["EUROPE_LATAM", "NORTH_SOUTH_AMERICA"],
        "airline": "Copa Airlines",
        "description": "El 'Hub de las Américas'. Programa Panamá Stopover sin coste adicional y a solo 1h de vuelo de Bogotá.",
    },
    "CUN": {
        "name": "Cancún",
        "country": "México",
        "corridors": ["EUROPE_LATAM", "NORTH_SOUTH_AMERICA"],
        "airline": "Wingo / Volaris / Avianca",
        "description": "Playas del Caribe mexicano, cenotes y ruinas mayas. Excelente conexión low-cost hacia Colombia.",
    },
    "SDQ": {
        "name": "Santo Domingo",
        "country": "República Dominicana",
        "corridors": ["EUROPE_LATAM", "CARIBBEAN_LATAM"],
        "airline": "Arajet / Air Europa",
        "description": "Zona Colonial histórica, gastronomía caribeña y puente asequible de vuelos hacia Colombia.",
    },
    "BOG": {
        "name": "Bogotá",
        "country": "Colombia",
        "corridors": ["EUROPE_LATAM", "NORTH_SOUTH_AMERICA"],
        "airline": "Avianca / LATAM",
        "description": "Capital andina, Museo del Oro, Monserrate y centro cultural y gastronómico de Colombia.",
    },
    "MDE": {
        "name": "Medellín",
        "country": "Colombia",
        "corridors": ["EUROPE_LATAM", "NORTH_SOUTH_AMERICA"],
        "airline": "Avianca / Wingo",
        "description": "Ciudad de la Eterna Primavera, Comuna 13, innovación urbana y trampolín al Eje Cafetero y Guatapé.",
    },
    "CTG": {
        "name": "Cartagena de Indias",
        "country": "Colombia",
        "corridors": ["EUROPE_LATAM", "CARIBBEAN_LATAM"],
        "airline": "Avianca / Air Europa",
        "description": "Ciudad amurallada colonial, arquitectura de cuento y playas caribeñas de las Islas del Rosario.",
    },
    "CMN": {
        "name": "Casablanca",
        "country": "Marruecos",
        "corridors": ["EUROPE_LATAM", "EUROPE_AMERICA", "EUROPE_AFRICA"],
        "airline": "Royal Air Maroc",
        "description": "Hub atlántico con tarifas históricamente competitivas hacia Brasil (São Paulo) y programa de escala.",
    },
    "OPO": {
        "name": "Oporto",
        "country": "Portugal",
        "corridors": ["EUROPE_LATAM", "EUROPE_AMERICA"],
        "airline": "TAP Air Portugal",
        "description": "Riberas del Duero, bodegas de vino y conexión directa de TAP hacia Brasil con stopover gratuito.",
    },
}

HUB_PRESETS: Dict[str, List[str]] = {
    "asia_top": ["BKK", "SIN", "ICN", "DOH", "IST"],
    "asia_full": ["BKK", "SIN", "KUL", "ICN", "TPE", "HKG", "HAN", "SGN", "DOH", "DXB", "IST"],
    "gulf": ["DOH", "DXB", "AUH", "IST"],
    "europe": ["IST", "HEL", "FRA", "MUC", "CDG", "AMS", "FCO", "ZRH"],
    "all_asia": ["BKK", "SIN", "KUL", "ICN", "TPE", "HKG", "DOH", "DXB", "AUH", "IST"],
    "istanbul": ["IST"],
    "brasil": ["LIS", "CMN", "FCO"],
    "brazil": ["LIS", "CMN", "FCO"],
    "latam_top": ["LIS", "CMN", "BOG", "PTY"],
}


class RouteAgent:
    """Agent that devises candidate intermediate hubs and multi-city stopovers."""

    def __init__(self, llm_client: Optional[GeminiClient] = None):
        self.llm = llm_client or GeminiClient()

    def get_preset_stopovers(self, preset_name: str) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
        """Returns stopovers based on a named preset."""
        preset_key = preset_name.lower().replace("-", "_")
        codes = HUB_PRESETS.get(preset_key, HUB_PRESETS["asia_top"])
        names = {c: GLOBAL_HUBS.get(c, {}).get("name", c) for c in codes}
        reasons = {c: GLOBAL_HUBS.get(c, {}).get("description", "Escala estratégica") for c in codes}
        return codes, names, reasons

    def recommend_stopovers(
        self,
        origin: str,
        destination: str,
        top_k: int = 3,
        preset: Optional[str] = None,
    ) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
        """
        Returns:
            - candidate_codes: List of IATA codes (e.g. ['BKK', 'SIN', 'DOH'])
            - stopover_names: Dict mapping code -> Name (e.g. {'BKK': 'Bangkok'})
            - stopover_reasons: Dict mapping code -> Reason/Highlights
        """
        if preset:
            return self.get_preset_stopovers(preset)

        orig = origin.upper()
        dest = destination.upper()

        if self.llm.is_available:
            res = self._recommend_with_gemini(orig, dest, top_k)
            if res:
                return res

        # Fallback heuristic
        return self._recommend_heuristic(orig, dest, top_k)

    def _recommend_with_gemini(
        self, origin: str, destination: str, top_k: int
    ) -> Optional[Tuple[List[str], Dict[str, str], Dict[str, str]]]:
        prompt = (
            f"Como estratega experto en rutas aéreas internacionales y programas de escalas (stopovers), "
            f"propón exactamente entre 3 y {top_k} aeropuertos intermedios (hubs IATA de 3 letras) "
            f"ideales para hacer una escala interesante de 1 a 3 días en una ruta entre el origen {origin} y el destino {destination}.\n\n"
            f"Requisitos:\n"
            f"1. Deben ser ciudades intermedias lógicas con gran atractivo turístico o con aerolíneas que abaraten la ruta (ej: Turkish en IST, Qatar en DOH, ITA en FCO, Emirates en DXB, TAP en LIS, etc.).\n"
            f"2. NO propongas el propio origen ({origin}) ni el propio destino ({destination}).\n"
            f"3. Responde ÚNICAMENTE en JSON con el siguiente esquema:\n"
            f'{{"stopovers": [{{"code": "IST", "city": "Estambul", "reason": "Cultura y gran hub de Turkish con stopover gratis"}}, ...]}}'
        )

        res = self.llm.generate_json(
            prompt,
            system_instruction="Eres un planificador experto en aviación comercial y rutas multidestino.",
        )

        if res and "stopovers" in res and isinstance(res["stopovers"], list) and len(res["stopovers"]) > 0:
            codes: List[str] = []
            names: Dict[str, str] = {}
            reasons: Dict[str, str] = {}
            for item in res["stopovers"][:top_k]:
                c = item.get("code", "").upper().strip()
                if c and c != origin and c != destination:
                    codes.append(c)
                    names[c] = item.get("city", c)
                    reasons[c] = item.get("reason", "")

            if codes:
                return codes, names, reasons

        return None

    def _recommend_heuristic(
        self, origin: str, destination: str, top_k: int
    ) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
        # Heuristic corridor matching
        corridor = "EUROPE_ASIA"
        # Check if origin or dest is in Americas, Europe, Asia, etc.
        americas = {"JFK", "MIA", "BOG", "EZE", "MEX", "GRU", "GIG", "SSA", "REC", "FOR", "BSB", "CNF"}
        brazil = {"GRU", "GIG", "SSA", "REC", "FOR", "BSB", "CNF", "FLN"}
        asia = {"TYO", "NRT", "HND", "OSA", "KIX", "NGO", "FUK", "BKK", "SIN", "KUL", "DPS", "ICN", "TPE"}
        europe = {"MAD", "BCN", "BIO", "VLC", "AGP", "LIS", "CDG", "FCO", "LHR", "AMS", "FRA", "MUC", "ATH", "VIE"}

        if (origin in europe and destination in brazil) or (destination in brazil):
            corridor = "EUROPE_LATAM"
        elif origin in europe and destination in asia:
            corridor = "EUROPE_ASIA"
        elif origin in europe and destination in americas:
            corridor = "EUROPE_AMERICA"
        elif origin in americas and destination in europe:
            corridor = "AMERICA_EUROPE"

        selected_codes = []
        names = {}
        reasons = {}

        for code, info in GLOBAL_HUBS.items():
            if code == origin or code == destination:
                continue
            if corridor in info["corridors"]:
                selected_codes.append(code)
                names[code] = info["name"]
                reasons[code] = info["description"]
            if len(selected_codes) >= top_k:
                break

        # Fallback if none matched
        if not selected_codes:
            for code in ["IST", "FCO", "DOH"]:
                if code not in (origin, destination):
                    selected_codes.append(code)
                    names[code] = GLOBAL_HUBS[code]["name"]
                    reasons[code] = GLOBAL_HUBS[code]["description"]

        return selected_codes, names, reasons

    def get_hub_strategy_explanation(self, candidate_codes: List[str]) -> str:
        """Returns a clear explanation of why these hubs were selected for the search engine."""
        if not candidate_codes:
            return "No se configuraron escalas intermedias (búsqueda directa exclusiva)."

        lines = [
            "- **Objetivo de los Hubs Intermedios:** Dividir trayectos de larga distancia, reducir tarifas aprovechando aerolíneas de enlace y añadir un destino turístico extra de 1 a 3 días sin comprar billetes independientes.",
        ]
        for c in candidate_codes:
            info = GLOBAL_HUBS.get(c, {})
            name = info.get("name", c)
            airline = info.get("airline", "Aerolíneas de enlace")
            desc = info.get("description", "Hub de conexión estratégica")
            lines.append(f"  - **{name} ({c}) - {airline}:** {desc}")
        return "\n".join(lines)

    def get_open_jaw_strategy(self, destinations: List[str], return_destinations: List[str]) -> str:
        """Returns a contextual explanation of why Open-Jaw (multiciudad) is recommended for this trip."""
        d_set = {d.upper() for d in destinations}
        r_set = {r.upper() for r in return_destinations}
        all_cities = d_set.union(r_set)

        if len(r_set) <= 1 and r_set == d_set:
            return "Ruta clásica de ida y vuelta a la misma ciudad de entrada."

        # Japan context
        if any(c in all_cities for c in ("TYO", "NRT", "HND", "OSA", "KIX", "ITM")):
            return (
                "La ruta Multiciudad (Open-Jaw) entrando por Tokio (`TYO`) y saliendo por Osaka (`OSA`) "
                "permite recorrer Japón de manera lineal (Tokio ➔ Kioto ➔ Nara ➔ Osaka) sin tener que desandar el camino "
                "de vuelta a Tokio en tren bala Shinkansen. Esto ahorra ~100 € por viajero y entre 4 y 5 horas de viaje."
            )

        # Colombia context
        if any(c in all_cities for c in ("BOG", "MDE", "CTG", "CLO")):
            return (
                "La ruta Multiciudad (Open-Jaw) entrando por Bogotá (`BOG`) y regresando desde Cartagena de Indias (`CTG`) o Medellín (`MDE`) "
                "permite recorrer Colombia linealmente de sur a norte (Andes ➔ Eje Cafetero ➔ Medellín ➔ Caribe) sin tener que retroceder "
                "a Bogotá. Esto ahorra un vuelo interno adicional (~60-90 €/persona) y evita perder un día entero de vacaciones en traslados innecesarios."
            )

        # Southeast Asia context
        if any(c in all_cities for c in ("BKK", "HKT", "CNX", "SIN", "KUL", "HAN", "SGN")):
            return (
                "La ruta Multiciudad (Open-Jaw) combinando dos ciudades principales (ej. Bangkok y Phuket, o Singapur y Bali) "
                "permite explorar zonas culturales o metropolitanas primero y culminar el viaje relajándose en la playa o islas, "
                "sin gastar presupuesto ni horas de viaje en regresar al punto inicial."
            )

        return (
            "La ruta Multiciudad (Open-Jaw) te permite diseñar un itinerario lineal entre regiones geográficas diferentes, "
            "optimizando tus días de vacaciones al evitar desandar el camino hacia el aeropuerto de llegada y eliminando un vuelo interno."
        )

