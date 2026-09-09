"""AI Synthesis and Evaluation Agent for flight itineraries."""

from typing import List, Optional, Dict, Any
from vusca.models.flight import Itinerary
from vusca.agents.llm_client import GeminiClient


class SynthesisAgent:
    """Agent that analyzes, scores, and synthesizes final flight search results."""

    def __init__(self, llm_client: Optional[GeminiClient] = None):
        self.llm = llm_client or GeminiClient()

    def evaluate_and_rank(self, itineraries: List[Itinerary]) -> List[Itinerary]:
        """Scores itineraries and attaches AI verdicts."""
        if not itineraries:
            return []

        # Find min and max price for normalization
        prices = [it.total_price_eur for it in itineraries]
        min_price = min(prices)
        max_price = max(prices)
        price_spread = max(max_price - min_price, 1.0)

        for it in itineraries:
            # Price score (0-40 pts): cheaper gets more points
            price_score = 40.0 * (1.0 - ((it.total_price_eur - min_price) / price_spread))

            # PTO efficiency score (0-35 pts): higher ratio gets more points
            pto_score = min(it.pto_efficiency_ratio * 12.0, 35.0)

            # Stopover richness score (0-25 pts): multi-city gets bonus
            stopover_score = 15.0 if it.stopovers else 5.0
            if len(it.stopovers) >= 2:
                stopover_score = 25.0
            elif it.stopovers and it.stopovers[0].stay_days in (2, 3):
                stopover_score += 10.0

            total_score = round(price_score + pto_score + stopover_score, 1)
            it.ai_score = total_score

            # Basic verdict label
            if len(it.stopovers) >= 2:
                s1, s2 = it.stopovers[0], it.stopovers[1]
                it.ai_verdict = f"Gran ruta con doble escala: {s1.stay_days}d en {s1.city_name} y {s2.stay_days}d en {s2.city_name}."
            elif it.stopovers:
                s = it.stopovers[0]
                it.ai_verdict = f"Excelente combinación con {s.stay_days} días para conocer {s.city_name}."
            else:
                it.ai_verdict = "Ruta directa sin escalas intermedias prolongadas."

        # Sort by AI Score descending
        itineraries.sort(key=lambda it: it.ai_score, reverse=True)
        return itineraries

    def generate_final_report(
        self,
        origin: str,
        destination: str,
        itineraries: List[Itinerary],
        candidate_stopover_names: Dict[str, str],
    ) -> str:
        """Generates an executive analysis report using Gemini or heuristic template."""
        if not itineraries:
            return "No se encontraron itinerarios válidos para los criterios seleccionados."

        ranked = self.evaluate_and_rank(itineraries)
        best_overall = ranked[0]
        cheapest = min(ranked, key=lambda it: it.total_price_eur)
        best_pto = max(ranked, key=lambda it: it.pto_efficiency_ratio)

        if self.llm.is_available:
            ai_report = self._generate_with_gemini(
                origin, destination, ranked[:5], best_overall, cheapest, best_pto
            )
            if ai_report:
                return ai_report

        return self._generate_heuristic_report(
            origin, destination, ranked, best_overall, cheapest, best_pto, candidate_stopover_names
        )

    def _generate_with_gemini(
        self,
        origin: str,
        destination: str,
        top_itineraries: List[Itinerary],
        best_overall: Itinerary,
        cheapest: Itinerary,
        best_pto: Itinerary,
    ) -> Optional[str]:
        prompt = (
            f"Como asistente experto en viajes e inteligencia de vuelos, redacta un informe ejecutivo "
            f"en español y en formato Markdown para un viaje desde {origin} hasta {destination}.\n\n"
            f"DATOS DE LAS MEJORES OPCIONES ENCONTRADAS:\n"
            f"- MEJOR OPCIÓN GLOBAL: {best_overall.route_summary} | Precio: {best_overall.total_price_eur}€ | "
            f"Días totales: {best_overall.total_trip_days} (Vacaciones gastadas: {best_overall.work_days_needed}) | "
            f"Fechas: {best_overall.start_date} a {best_overall.end_date}.\n"
            f"- MÁS ECONÓMICA: {cheapest.route_summary} | Precio: {cheapest.total_price_eur}€.\n"
            f"- MAYOR EFICIENCIA PTO: {best_pto.route_summary} | Ratio: x{best_pto.pto_efficiency_ratio}.\n\n"
            f"DETALLES DE LOS TRAMOS:\n"
        )

        for idx, it in enumerate(top_itineraries, 1):
            prompt += f"\nOpción {idx} (Puntuación AI: {it.ai_score}/100):\n"
            prompt += f"  Ruta: {it.route_summary} - Total: {it.total_price_eur}€\n"
            for leg in it.legs:
                prompt += (
                    f"    * Tramo {leg.origin} -> {leg.destination} ({leg.departure_date}): "
                    f"{leg.price_eur}€ con {', '.join(leg.airline_names) or 'Aerolínea'}\n"
                )
            if it.stopovers:
                s = it.stopovers[0]
                prompt += f"    * Escala de {s.stay_days} días en {s.city_name} ({s.arrival_date} al {s.departure_date})\n"

        prompt += (
            "\nESTRUCTURA DEL INFORME QUE DEBES GENERAR:\n"
            "1. Resumen Ejecutivo y Ganador Recomendado (por qué merece la pena la parada intermedia).\n"
            "2. Tabla Comparativa de las Mejores Opciones (Ruta, Días Totales, Días de Vacaciones, Precio Total, Puntuación).\n"
            "3. Consejos Prácticos para la Escala Intermedia (qué hacer en 1-2 días en la ciudad de stopover, equipaje facturado vs de mano, etc.).\n"
            "4. Desglose detallado de vuelos con sus enlaces o pautas de reserva.\n"
            "Sé persuasivo, claro y profesional."
        )

        system_inst = "Eres el Agente Sintetizador de Vuelos Inteligente de Vusca. Analizas vuelos y maximizas la experiencia y el ahorro del viajero."
        return self.llm.generate_text(prompt, system_instruction=system_inst)

    def _generate_heuristic_report(
        self,
        origin: str,
        destination: str,
        ranked: List[Itinerary],
        best_overall: Itinerary,
        cheapest: Itinerary,
        best_pto: Itinerary,
        candidate_stopover_names: Optional[Dict[str, str]] = None,
    ) -> str:
        stop_names = candidate_stopover_names or {}
        md = []
        md.append(f"# ✈️ Informe de Búsqueda Inteligente: {origin} ➔ {destination}\n")
        md.append(
            "> Este informe ha sido analizado y sintetizado por el **Agente de Inteligencia Artificial** de Vusca, "
            "optimizando días de vacaciones y escalas estratégicas.\n"
        )

        md.append("## 🏆 Opciones Destacadas\n")
        md.append(
            f"- **🥇 Mejor Opción Global (Score {best_overall.ai_score}/100):** {best_overall.route_summary}\n"
            f"  - **Precio Total:** `{best_overall.total_price_eur} €`\n"
            f"  - **Calendario:** Del `{best_overall.start_date}` al `{best_overall.end_date}` "
            f"({best_overall.total_trip_days} días totales usando solo **{best_overall.work_days_needed} días de vacaciones**)\n"
            f"  - **Eficiencia PTO:** `x{best_overall.pto_efficiency_ratio}` (por cada día pedido trabajas disfrutas {best_overall.pto_efficiency_ratio} días de viaje)\n"
        )

        if cheapest.itinerary_id != best_overall.itinerary_id:
            md.append(
                f"- **💰 Opción Más Económica:** {cheapest.route_summary} a solo `{cheapest.total_price_eur} €`\n"
            )

        if best_pto.itinerary_id != best_overall.itinerary_id:
            md.append(
                f"- **⚡ Mayor Rendimiento Vacacional:** {best_pto.route_summary} "
                f"({best_pto.total_trip_days} días de viaje con {best_pto.work_days_needed} días de vacaciones, ratio `x{best_pto.pto_efficiency_ratio}`)\n"
            )

        md.append("\n## 📊 Tabla Comparativa de las 10 Mejores Opciones de Vuelo\n")
        md.append("| # | Ruta y Paradas | Días Viaje | Días Vacaciones | Precio Total | Puntuación IA |")
        md.append("|---|----------------|:----------:|:---------------:|:------------:|:-------------:|")
        for i, it in enumerate(ranked[:10], 1):
            md.append(
                f"| {i} | {it.route_summary} | {it.total_trip_days}d | {it.work_days_needed}d | {it.total_price_eur} € | **{it.ai_score}**/100 |"
            )

        # Check if multiple return origin airports exist (e.g. TYO vs KIX/OSA)
        return_origins = set()
        for it in ranked:
            if it.legs:
                # Origin of return leg back to home origin
                last_leg = it.legs[-1]
                # If there was an inbound stopover, the return began at leg[-2].origin
                return_city = it.legs[1].origin if len(it.legs) == 3 and "inbound" in it.itinerary_id else last_leg.origin
                return_origins.add(return_city)

        if len(return_origins) > 1:
            md.append("\n## 🔄 Comparativa de Ciudades de Regreso (Multiciudad / Open-Jaw)\n")
            for r_code in sorted(return_origins):
                r_name = stop_names.get(r_code, r_code)
                r_its = [
                    it for it in ranked
                    if any(leg.origin == r_code and leg.destination == origin for leg in it.legs)
                    or (len(it.legs) == 3 and it.legs[1].origin == r_code)
                ]
                if r_its:
                    min_r = min(r_its, key=lambda x: x.total_price_eur)
                    md.append(
                        f"- **Regreso por {r_name} ({r_code}):** Mejor precio total: `{min_r.total_price_eur} €` "
                        f"({min_r.route_summary})\n"
                    )
            md.append(
                "> **💡 Consejo de Viaje:** La ruta *Open-Jaw* (llegar a Tokio y volver por Osaka) te permite recorrer Japón linealmente "
                "de este a oeste sin tener que gastar tiempo ni dinero en volver a Tokio en tren bala Shinkansen (ahorro adicional de ~100 €/persona)."
            )

        md.append("\n## 🧭 Desglose del Itinerario Recomendado\n")
        for i, leg in enumerate(best_overall.legs, 1):
            airlines = ", ".join(leg.airline_names) or "Línea Aérea"
            md.append(f"### Tramo {i}: {leg.origin} ➔ {leg.destination}")
            md.append(f"- **Fecha:** `{leg.departure_date}`")
            md.append(f"- **Aerolíneas:** {airlines}")
            md.append(f"- **Precio estimado:** `{leg.price_eur} €`")
            if leg.booking_url:
                md.append(f"- **Reserva / Consulta:** [Ver Vuelos en Google Flights]({leg.booking_url})")

        if best_overall.stopovers:
            st = best_overall.stopovers[0]
            md.append(f"\n### 💡 Consejos para la escala en {st.city_name} ({st.stay_days} días)")
            md.append(
                f"- **Fechas de escala:** Del `{st.arrival_date}` al `{st.departure_date}`.\n"
                f"- **Logística:** Al ser una parada de {st.stay_days} días, tu equipaje de bodega se retira en {st.city_name} "
                "para disfrutar cómodamente de la estancia en un hotel céntrico antes del siguiente vuelo.\n"
                f"- **Ahorro & Experiencia:** Romper el vuelo largo no solo reduce la fatiga del viaje sino que te permite tachar "
                f"{st.city_name} de tu lista de destinos por una fracción del coste de un viaje individual."
            )

        return "\n".join(md)
