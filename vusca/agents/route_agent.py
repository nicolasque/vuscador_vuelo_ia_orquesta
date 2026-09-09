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
}

HUB_PRESETS: Dict[str, List[str]] = {
    "asia_top": ["BKK", "SIN", "ICN", "DOH", "IST"],
    "asia_full": ["BKK", "SIN", "KUL", "ICN", "TPE", "HKG", "HAN", "SGN", "DOH", "DXB", "IST"],
    "gulf": ["DOH", "DXB", "AUH", "IST"],
    "europe": ["IST", "HEL", "FRA", "MUC", "CDG", "AMS", "FCO", "ZRH"],
    "all_asia": ["BKK", "SIN", "KUL", "ICN", "TPE", "HKG", "DOH", "DXB", "AUH", "IST"],
    "istanbul": ["IST"],
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
        americas = {"JFK", "MIA", "BOG", "EZE", "MEX"}
        asia = {"TYO", "NRT", "HND", "OSA", "KIX", "NGO", "FUK", "BKK", "SIN", "KUL", "DPS", "ICN", "TPE"}
        europe = {"MAD", "BCN", "BIO", "VLC", "AGP", "LIS", "CDG", "FCO", "LHR", "AMS", "FRA", "MUC", "ATH", "VIE"}

        if origin in europe and destination in asia:
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
