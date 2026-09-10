"""AI Synthesis and Evaluation Agent for flight itineraries."""

from typing import List, Optional, Dict, Any
from urllib.parse import quote
from vusca.models.flight import Itinerary
from vusca.agents.llm_client import GeminiClient
from vusca.core.curator import DeterministicCurator, CuratedArchetypes


class SynthesisAgent:
    """Agent that analyzes, scores, and synthesizes final flight search results."""

    def __init__(
        self,
        llm_client: Optional[GeminiClient] = None,
        curator: Optional[DeterministicCurator] = None,
    ):
        self.llm = llm_client or GeminiClient()
        self.curator = curator or DeterministicCurator(activation_threshold=100)

    def evaluate_and_rank(
        self,
        itineraries: List[Itinerary],
        priority: str = "balanced",
    ) -> List[Itinerary]:
        """Scores itineraries and attaches AI verdicts.
        priority can be 'balanced' (default, price + pto + stops) or 'cheapest' (purely minimal price).
        """
        if not itineraries:
            return []

        # Find min and max price for normalization
        prices = [it.total_price_eur for it in itineraries]
        min_price = min(prices)
        max_price = max(prices)
        price_spread = max(max_price - min_price, 1.0)

        for it in itineraries:
            if priority in ("cheapest", "price", "price_first"):
                # Price score is dominant (0-80 pts)
                price_score = 80.0 * (1.0 - ((it.total_price_eur - min_price) / price_spread))
                # Stopover/comfort score (0-20 pts)
                stopover_score = 15.0 if it.stopovers else 20.0
                pto_score = 0.0
                total_score = round(price_score + stopover_score, 1)
            else:
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

        # Sort: if cheapest priority, sort primarily by lowest total price
        if priority in ("cheapest", "price", "price_first"):
            itineraries.sort(key=lambda it: (it.total_price_eur, -it.ai_score))
        else:
            itineraries.sort(key=lambda it: it.ai_score, reverse=True)
        return itineraries

    def generate_final_report(
        self,
        origin: str,
        destination: str,
        itineraries: List[Itinerary],
        candidate_stopover_names: Dict[str, str],
        search_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generates an executive analysis report using Gemini or heuristic template."""
        if not itineraries:
            return "No se encontraron itinerarios válidos para los criterios seleccionados."

        ctx = search_context or {}
        priority = ctx.get("priority", "balanced")
        ranked = self.evaluate_and_rank(itineraries, priority=priority)

        # Deterministic reduction for large datasets
        curated_data: Optional[CuratedArchetypes] = None
        if self.curator.is_applicable(len(ranked)):
            curated_data = self.curator.curate(
                ranked,
                target_origins=ctx.get("origins"),
                target_destinations=ctx.get("destinations"),
                max_selection_size=20,
            )

        best_overall = curated_data.best_overall if (curated_data and curated_data.best_overall) else ranked[0]
        cheapest = curated_data.cheapest_overall if (curated_data and curated_data.cheapest_overall) else min(ranked, key=lambda it: it.total_price_eur)
        best_pto = curated_data.best_pto_overall if (curated_data and curated_data.best_pto_overall) else max(ranked, key=lambda it: it.pto_efficiency_ratio)

        if self.llm.is_available:
            ai_report = self._generate_with_gemini(
                origin, destination, ranked, best_overall, cheapest, best_pto, candidate_stopover_names, ctx, curated_data=curated_data
            )
            if ai_report:
                return ai_report

        return self._generate_heuristic_report(
            origin, destination, ranked, best_overall, cheapest, best_pto, candidate_stopover_names, ctx, curated_data=curated_data
        )

    @staticmethod
    def _get_options_by_origin(
        ranked: List[Itinerary],
        origins_list: List[str],
        limit_per_origin: int = 4,
        curated_selection: Optional[List[Itinerary]] = None,
    ) -> Dict[str, List[Itinerary]]:
        """Selects diverse, top-scoring itineraries for each origin airport."""
        target_origins = [o for o in origins_list if any(it.origin == o for it in ranked)] or list(dict.fromkeys([it.origin for it in ranked]))
        options_by_orig: Dict[str, List[Itinerary]] = {}

        for orig_code in target_origins:
            orig_itins = [it for it in ranked if it.origin == orig_code]
            selected = []
            seen_routes = set()

            # Pass 0: Seed with curated diverse champions if available
            if curated_selection:
                for it in curated_selection:
                    if it.origin == orig_code:
                        ret_arr = it.legs[-1].destination if it.legs else it.origin
                        sig = (it.final_destination, ret_arr, tuple(s.city_code for s in it.stopovers))
                        if sig not in seen_routes:
                            seen_routes.add(sig)
                            selected.append(it)
                        if len(selected) == limit_per_origin:
                            break

            # Pass 1: Distinct route signatures (dest + return arrival + stopover sequence)
            if len(selected) < limit_per_origin:
                for it in orig_itins:
                    ret_arr = it.legs[-1].destination if it.legs else it.origin
                    sig = (it.final_destination, ret_arr, tuple(s.city_code for s in it.stopovers))
                    if sig not in seen_routes:
                        seen_routes.add(sig)
                        selected.append(it)
                    if len(selected) == limit_per_origin:
                        break

            # Pass 2: Fill up to limit_per_origin with remaining top-scoring options
            if len(selected) < limit_per_origin:
                for it in orig_itins:
                    if it not in selected:
                        selected.append(it)
                    if len(selected) == limit_per_origin:
                        break

            options_by_orig[orig_code] = selected

        return options_by_orig

    @staticmethod
    def _get_options_by_scenario(
        ranked: List[Itinerary],
        scenarios_list: Optional[List[Tuple[str, str]]] = None,
        limit_per_scenario: int = 4,
        curated_selection: Optional[List[Itinerary]] = None,
    ) -> Dict[Tuple[str, str], List[Itinerary]]:
        """Selects diverse, top-scoring itineraries for each route scenario (origin, return_arrival)."""
        if scenarios_list:
            target_scenarios = [
                s for s in scenarios_list
                if any((it.origin == s[0] and (it.legs[-1].destination if it.legs else it.origin) == s[1]) for it in ranked)
            ]
        else:
            target_scenarios = list(dict.fromkeys([
                (it.origin, it.legs[-1].destination if it.legs else it.origin) for it in ranked
            ]))

        options_by_scen: Dict[Tuple[str, str], List[Itinerary]] = {}

        for scen in target_scenarios:
            orig_code, ret_code = scen
            scen_itins = [
                it for it in ranked
                if it.origin == orig_code and (it.legs[-1].destination if it.legs else it.origin) == ret_code
            ]
            selected = []
            seen_routes = set()

            # Pass 0: Seed with curated diverse champions
            if curated_selection:
                for it in curated_selection:
                    it_ret = it.legs[-1].destination if it.legs else it.origin
                    if it.origin == orig_code and it_ret == ret_code:
                        sig = (it.final_destination, it_ret, tuple(s.city_code for s in it.stopovers))
                        if sig not in seen_routes:
                            seen_routes.add(sig)
                            selected.append(it)
                        if len(selected) == limit_per_scenario:
                            break

            # Pass 1: Distinct route signatures (dest + return arrival + stopover sequence)
            if len(selected) < limit_per_scenario:
                for it in scen_itins:
                    it_ret = it.legs[-1].destination if it.legs else it.origin
                    sig = (it.final_destination, it_ret, tuple(s.city_code for s in it.stopovers))
                    if sig not in seen_routes:
                        seen_routes.add(sig)
                        selected.append(it)
                    if len(selected) == limit_per_scenario:
                        break

            # Pass 2: Fill up to limit with remaining top-scoring options
            if len(selected) < limit_per_scenario:
                for it in scen_itins:
                    if it not in selected:
                        selected.append(it)
                    if len(selected) == limit_per_scenario:
                        break

            options_by_scen[scen] = selected

        return options_by_scen

    def _generate_with_gemini(
        self,
        origin: str,
        destination: str,
        ranked: List[Itinerary],
        best_overall: Itinerary,
        cheapest: Itinerary,
        best_pto: Itinerary,
        candidate_stopover_names: Dict[str, str],
        context: Dict[str, Any],
        curated_data: Optional[CuratedArchetypes] = None,
    ) -> Optional[str]:
        origins_list = context.get("origins") or [o.strip() for o in origin.split(",") if o.strip()]
        destinations_list = context.get("destinations") or [d.strip() for d in destination.split(",") if d.strip()]

        prompt = (
            f"Como asistente experto en inteligencia de viajes y vuelos internacionales de Vusca, "
            f"redacta un informe ejecutivo exhaustivo en español y en formato Markdown para un viaje "
            f"desde {', '.join(origins_list)} hasta {', '.join(destinations_list)}.\n\n"
            f"CONTEXTO Y JUSTIFICACIÓN DE LA BÚSQUEDA (POR QUÉ SE BUSCÓ DE ESTA MANERA):\n"
            f"- Justificación de calendario (PTO): {context.get('pto_strategy', 'Optimización de días de vacaciones con festivos')}\n"
            f"- Justificación de hubs y paradas: {context.get('hub_strategy', 'Escalas estratégicas de 1-3 días en hubs con stopover')}\n"
            f"- Justificación Multiciudad (Open-Jaw): {context.get('open_jaw_strategy', 'Rutas lineales sin retroceder')}\n"
            f"- Restricciones de confort: Máximo 1 escala de conexión por tramo de billete, máximo 2 escalas totales por sentido.\n\n"
        )

        if curated_data and curated_data.market_stats:
            m_stats = curated_data.market_stats
            prompt += (
                f"RESUMEN ESTADÍSTICO DEL MERCADO ({curated_data.total_evaluated:,} combinaciones reales analizadas deterministamente):\n"
                f"- Rango global de precios: {m_stats.get('price_min')}€ - {m_stats.get('price_max')}€ "
                f"(Mediana: {m_stats.get('price_median')}€ | Media: {m_stats.get('price_mean')}€)\n"
                f"- Precios mínimos por Escenario: {dict(m_stats.get('scenario_min_prices', {}))}\n"
                f"- Precios mínimos por Hub: {dict(m_stats.get('hub_min_prices', {}))}\n"
                f"- Precios mínimos por Destino: {dict(m_stats.get('destination_min_prices', {}))}\n\n"
            )

        prompt += (
            f"DATOS DE LAS MEJORES OPCIONES ENCONTRADAS ({len(ranked)} evaluadas):\n"
            f"- GANADOR GLOBAL: {best_overall.route_summary} | {best_overall.total_price_eur}€ | {best_overall.total_trip_days}d ({best_overall.work_days_needed} PTO)\n"
            f"- MÁS ECONÓMICA: {cheapest.route_summary} | {cheapest.total_price_eur}€ | {cheapest.total_trip_days}d ({cheapest.work_days_needed} PTO)\n"
            f"- MÁXIMA EFICIENCIA PTO: {best_pto.route_summary} | Ratio x{best_pto.pto_efficiency_ratio} | {best_pto.total_trip_days}d ({best_pto.work_days_needed} PTO)\n\n"
        )

        curated_sel = curated_data.curated_selection if curated_data else None
        allowed_scenarios = context.get("allowed_scenarios")
        use_scenario_view = bool(allowed_scenarios)

        if use_scenario_view:
            options_by_scen = self._get_options_by_scenario(
                ranked, scenarios_list=allowed_scenarios, limit_per_scenario=4, curated_selection=curated_sel
            )
            prompt += "OPCIONES SELECCIONADAS POR ESCENARIO DE RUTA:\n"
            for scen, itins in options_by_scen.items():
                orig_code, ret_code = scen
                orig_name = candidate_stopover_names.get(orig_code, orig_code)
                ret_name = candidate_stopover_names.get(ret_code, ret_code)
                scen_label = f"{orig_name} -> {ret_name} ({orig_code} -> {ret_code})"
                prompt += f"\n=== {scen_label}: {len(itins)} Mejores Opciones ===\n"
                for idx, it in enumerate(itins, 1):
                    prompt += f"\nOpción {idx} para {scen_label} ({it.ai_score}/100) - {it.route_summary} - Total: {it.total_price_eur}€ - {it.total_trip_days} días ({it.work_days_needed}d PTO):\n"
                    for leg in it.legs:
                        carriers = ", ".join(leg.airline_names) or "Aerolínea"
                        prompt += (
                            f"    * Tramo {leg.origin} -> {leg.destination} ({leg.departure_date}): "
                            f"{leg.price_eur}€ con {carriers} ({leg.stops_count} escalas) | Link: {leg.flight_search_url}\n"
                        )
        else:
            options_by_origin = self._get_options_by_origin(ranked, origins_list, limit_per_origin=4, curated_selection=curated_sel)
            prompt += "OPCIONES SELECCIONADAS POR AEROPUERTO DE ORIGEN:\n"
            for orig_code, itins in options_by_origin.items():
                orig_name = candidate_stopover_names.get(orig_code, orig_code)
                prompt += f"\n=== {orig_name} ({orig_code}): {len(itins)} Mejores Opciones ===\n"
                for idx, it in enumerate(itins, 1):
                    prompt += f"\nOpción {idx} desde {orig_name} ({it.ai_score}/100) - {it.route_summary} - Total: {it.total_price_eur}€ - {it.total_trip_days} días ({it.work_days_needed}d PTO):\n"
                    for leg in it.legs:
                        carriers = ", ".join(leg.airline_names) or "Aerolínea"
                        prompt += (
                            f"    * Tramo {leg.origin} -> {leg.destination} ({leg.departure_date}): "
                            f"{leg.price_eur}€ con {carriers} ({leg.stops_count} escalas) | Link: {leg.flight_search_url}\n"
                        )

        prompt += (
            "\nESTRUCTURA OBLIGATORIA DEL INFORME:\n"
            "1. Título e introducción con resumen del análisis de la IA.\n"
            "2. Configuración y Justificación de la Búsqueda (Por qué se ha hecho de esta manera: calendario, festivos, hubs y Open-Jaw).\n"
            "3. Opciones Destacadas Globales (El Podio: Ganador Global, Más Económica, Mayor Rendimiento).\n"
            "4. Tablas Comparativas por Aeropuerto de Origen (separando Madrid, Bilbao, etc.).\n"
            "5. Desglose Exhaustivo de las Mejores Opciones: REGLA ESTRICTA -> DEBES INCLUIR OBLIGATORIAMENTE EXACTAMENTE 4 OPCIONES DETALLADAS PARA CADA AEROPUERTO DE ORIGEN (4 DESDE MADRID Y 4 DESDE BILBAO, 8 OPCIONES EN TOTAL). Para CADA opción muestra: Título con medalla, Precio Total, Duración (fechas) y PTO, Ruta completa, Desglose tramo a tramo con precios, fechas, aerolíneas, escalas y el enlace directo [Ver Vuelos en Google Flights](url), y la ventaja competitiva de la opción.\n"
            "6. Estrategia Multiciudad / Open-Jaw específica para el destino.\n"
            "7. Consejos Logísticos para las Escalas Intermedias (equipaje facturado, hoteles de stopover, tiempos).\n"
            "Sé riguroso, analítico, persuasivo y estructurado."
        )

        system_inst = "Eres el Agente Sintetizador de Vuelos de Vusca. Generas informes de viaje de nivel profesional con enlaces reales y explicaciones estratégicas."
        return self.llm.generate_text(prompt, system_instruction=system_inst)

    @staticmethod
    def _format_price(p: float) -> str:
        return f"{p:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    def _format_itinerary_card(
        self,
        it: Itinerary,
        rank_num: int,
        medal: str,
        stop_names: Dict[str, str],
        dest_label: str,
    ) -> str:
        out = []
        st = it.stopovers

        # Build attractive title
        if len(st) >= 2:
            s1_name = st[0].city_name
            s2_name = st[1].city_name
            if rank_num == 1 and dest_label == "Japón":
                title = f'{medal} Opción {rank_num}: La "Ruta Dorada de Asia Oriental" (Japón + {s1_name} + {s2_name})'
            elif rank_num == 1 and dest_label == "Brasil":
                title = f'{medal} Opción {rank_num}: La "Gran Ruta Brasileña" (Brasil + {s1_name} + {s2_name})'
            elif rank_num == 1:
                title = f"{medal} Opción {rank_num}: La Gran Ruta {dest_label} ({dest_label} + {s1_name} + {s2_name})"
            else:
                title = f"{medal} Opción {rank_num}: {dest_label} + {s1_name} + {s2_name}"
        elif len(st) == 1:
            s_name = st[0].city_name
            if rank_num == 1 and dest_label == "Brasil":
                title = f"{medal} Opción {rank_num}: Brasil + {s_name} (Parada Atlántica)"
            elif rank_num == 1:
                title = f"{medal} Opción {rank_num}: Ruta Panorámica ({dest_label} + {s_name})"
            else:
                title = f"{medal} Opción {rank_num}: {dest_label} + {s_name}"
        else:
            final_name = stop_names.get(it.final_destination, it.final_destination)
            title = f"{medal} Opción {rank_num}: Vuelo Directo / Ruta Base ({it.origin} ➔ {final_name})"

        # Format Route summary with full city names and Open-Jaw detection
        route_str = it.route_summary
        for code, name in stop_names.items():
            route_str = route_str.replace(f" {code} ", f" {name} ")
            if route_str.endswith(f" {code}"):
                route_str = route_str[:-len(code)] + name
            if route_str.startswith(f"{code} "):
                route_str = name + route_str[len(code):]

        import re
        route_str = re.sub(r'\(1d\)', '(1 día)', route_str)
        route_str = re.sub(r'\((\d+)d\)', r'(\1 días)', route_str)

        # Detect Open-Jaw (entry != exit)
        is_open_jaw = False
        if len(it.legs) >= 2:
            outbound_dest = it.legs[0].destination if len(it.legs) == 2 else it.legs[1].destination
            inbound_orig = it.legs[1].origin if len(it.legs) == 2 else (it.legs[2].origin if len(it.legs) == 4 else (it.legs[1].origin if len(it.legs) == 3 and "inbound" in it.itinerary_id else it.legs[-1].origin))
            if outbound_dest != inbound_orig:
                is_open_jaw = True
                route_str = route_str.replace("| Regreso:", "| Regreso Open-Jaw:")

        s_date = it.start_date.strftime("%d/%m/%Y")
        e_date = it.end_date.strftime("%d/%m/%Y")

        final_return = it.legs[-1].destination if it.legs else it.origin
        is_cross_origin = (it.origin != final_return)
        orig_name_label = stop_names.get(it.origin, it.origin)
        ret_name_label = stop_names.get(final_return, final_return)

        out.append(f"### {title}\n")
        out.append(f"- **Precio Total: {self._format_price(it.total_price_eur)}**")
        out.append(f"- **Duración:** {it.total_trip_days} días ({s_date} al {e_date}) | **Vacaciones requeridas: {it.work_days_needed} días**")
        if is_cross_origin:
            out.append(f"- **Tipo de Conexión:** 🔄 **Ruta Interciudad Mixta:** Salida desde **{orig_name_label} ({it.origin})** y regreso a **{ret_name_label} ({final_return})**.")
        out.append(f"- **Ruta:** `{route_str}`")
        out.append("- **Desglose de Vuelos:**")

        for idx, leg in enumerate(it.legs, 1):
            d_str = leg.departure_date.strftime("%d/%m/%Y")
            carriers = ", ".join(leg.airline_names) or "Aerolínea"

            # Detailed stops explanation
            if leg.stops_count == 0:
                stops_detail = "Vuelo **DIRECTO** sin escalas"
            elif leg.stops_count == 1:
                transfers = [s.arrival_airport for s in leg.segments[:-1]] if leg.segments else []
                transfer_str = f" en {', '.join(transfers)}" if transfers else ""
                stops_detail = f"1 escala técnica{transfer_str}"
            else:
                transfers = [s.arrival_airport for s in leg.segments[:-1]] if leg.segments else []
                transfer_str = f" en {', '.join(transfers)}" if transfers else ""
                stops_detail = f"{leg.stops_count} escalas técnicas{transfer_str}"

            out.append(
                f"  {idx}. **{d_str}:** [{leg.origin} ➔ {leg.destination}]({leg.flight_search_url}) "
                f"por **{self._format_price(leg.price_eur)}** | *{carriers}* ({stops_detail})."
            )

        # Multi-tab opener link
        legs_urls = [leg.flight_search_url for leg in it.legs]
        encoded_urls = quote("||".join(legs_urls), safe='')
        card_title_encoded = quote(title, safe='')
        launcher_link = f"file:///Users/nicolas/Documents/42/vusca_vuelos_orquesta/open_tabs.html#title={card_title_encoded}&urls={encoded_urls}"
        out.append(f"- **Abrir Todos los Tramos:** [🚀 Abrir las {len(it.legs)} pestañas a la vez en Google Flights (Solo Ida)]({launcher_link})")

        # Escalas summary line
        if len(it.legs) == 4 and len(st) >= 2:
            t_out = it.legs[0].stops_count + it.legs[1].stops_count
            t_in = it.legs[2].stops_count + it.legs[3].stops_count
            t_out_desc = f"{t_out} técnica + " if t_out else ""
            t_in_desc = f" + {t_in} técnica" if t_in else ""
            s1_d = f"{st[0].stay_days} día" if st[0].stay_days == 1 else f"{st[0].stay_days} días"
            s2_d = f"{st[1].stay_days} día" if st[1].stay_days == 1 else f"{st[1].stay_days} días"
            out_str = f"Ida = {t_out + 1} escalas ({t_out_desc}{s1_d} en {st[0].city_name})"
            in_str = f"Vuelta = {t_in + 1} escalas ({s2_d} en {st[1].city_name}{t_in_desc})"
            out.append(f"- **Escalas:** {out_str} | {in_str}.")
        elif len(it.legs) == 3 and len(st) == 1:
            s_d = f"{st[0].stay_days} día" if st[0].stay_days == 1 else f"{st[0].stay_days} días"
            if st[0].city_code == it.legs[0].destination:
                t_out = it.legs[0].stops_count + it.legs[1].stops_count
                t_in = it.legs[2].stops_count
                t_out_desc = f"{t_out} técnica + " if t_out else ""
                t_in_desc = f"{t_in} técnica" if t_in else "Directo"
                out_str = f"Ida = {t_out + 1} escalas ({t_out_desc}{s_d} en {st[0].city_name})"
                in_str = f"Vuelta = {t_in} escalas ({t_in_desc})"
            else:
                t_out = it.legs[0].stops_count
                t_in = it.legs[1].stops_count + it.legs[2].stops_count
                t_out_desc = f"{t_out} técnica" if t_out else "Directo"
                t_in_desc = f" + {t_in} técnica" if t_in else ""
                out_str = f"Ida = {t_out} escalas ({t_out_desc})"
                in_str = f"Vuelta = {t_in + 1} escalas ({s_d} en {st[0].city_name}{t_in_desc})"
            out.append(f"- **Escalas:** {out_str} | {in_str}.")
        elif len(it.legs) == 2:
            s0 = "Vuelo Directo" if it.legs[0].stops_count == 0 else f"{it.legs[0].stops_count} escala técnica"
            s1 = "Vuelo Directo" if it.legs[1].stops_count == 0 else f"{it.legs[1].stops_count} escala técnica"
            out.append(f"- **Escalas:** Ida = {s0} | Vuelta = {s1}.")

        # Ventaja
        if is_open_jaw and len(st) >= 2:
            ventaja = (
                f"Recorrido lineal en destino sin desandar el camino ni pagar vuelos internos de regreso. "
                f"Añade 2 destinos extra ({st[0].city_name} y {st[1].city_name}) aprovechando escalas estratégicas."
            )
        elif is_open_jaw and len(st) == 1:
            ventaja = (
                f"Ahorro de trayecto interno en destino gracias al formato Open-Jaw, sumando una escala turística en {st[0].city_name}."
            )
        elif is_open_jaw:
            ventaja = (
                "Ruta multiciudad (Open-Jaw) que ahorra tiempo y dinero al evitar volver a la ciudad de llegada para coger el vuelo de vuelta."
            )
        elif len(st) >= 2:
            ventaja = f"Permite conocer {st[0].city_name} y {st[1].city_name} dividiendo los vuelos largos y reduciendo el jet lag."
        elif len(st) == 1:
            ventaja = f"Permite disfrutar de {st[0].stay_days} días en {st[0].city_name} dividiendo el viaje intercontinental."
        else:
            ventaja = "Ruta directa y eficiente para quien prioriza llegar al destino principal en el menor tiempo posible."

        out.append(f"- **Ventaja:** {ventaja}")

        return "\n".join(out)

    def _generate_heuristic_report(
        self,
        origin: str,
        destination: str,
        ranked: List[Itinerary],
        best_overall: Itinerary,
        cheapest: Itinerary,
        best_pto: Itinerary,
        candidate_stopover_names: Optional[Dict[str, str]] = None,
        context: Optional[Dict[str, Any]] = None,
        curated_data: Optional[CuratedArchetypes] = None,
    ) -> str:
        stop_names = candidate_stopover_names or {}
        ctx = context or {}
        origins_list = ctx.get("origins") or [o.strip() for o in origin.split(",") if o.strip()]
        destinations_list = ctx.get("destinations") or [d.strip() for d in destination.split(",") if d.strip()]

        # Determine country or destination label
        all_dests = {d.upper() for d in destinations_list}
        if any(d in all_dests for d in ("TYO", "OSA", "NRT", "HND", "KIX")):
            dest_label = "Japón"
        elif any(d in all_dests for d in ("BOG", "MDE", "CTG", "CLO")):
            dest_label = "Colombia"
        elif any(d in all_dests for d in ("BKK", "HKT", "CNX")):
            dest_label = "Tailandia"
        elif any(d in all_dests for d in ("GRU", "GIG", "SSA", "REC", "FOR", "BSB", "CNF", "FLN")):
            dest_label = "Brasil"
        elif any(d in all_dests for d in ("KUL", "PEN")) and "SIN" in all_dests:
            dest_label = "Malasia & Singapur"
        elif any(d in all_dests for d in ("KUL", "PEN")):
            dest_label = "Malasia"
        elif "SIN" in all_dests:
            dest_label = "Singapur"
        else:
            dest_label = " / ".join([stop_names.get(d, d) for d in destinations_list])

        origins_str = " / ".join([stop_names.get(o, o) for o in origins_list])
        dest_str = " / ".join([stop_names.get(d, d) for d in destinations_list])

        md: List[str] = []

        # 1. Título
        md.append(f"# ✈️ Informe de Búsqueda Inteligente: {origins_str} ➔ {dest_str}\n")
        md.append(
            "> Este informe ha sido analizado y sintetizado por el **Agente de Inteligencia Artificial** de Vusca, "
            "maximizando el rendimiento vacacional, evaluando escalas estratégicas y garantizando conexiones cómodas.\n"
        )

        # 2. Configuración y Justificación de la Búsqueda
        md.append("## 🎯 Configuración y Justificación de la Búsqueda (Por Qué se Buscó de Esta Manera)\n")

        # Justificación de calendario
        pto_strat = ctx.get("pto_strategy")
        md.append("### 📅 1. Estrategia de Calendario y Festivos (PTO)")
        if pto_strat:
            md.append(f"{pto_strat}\n")
        else:
            md.append(
                f"- **Objetivo:** Maximizar días naturales de viaje minimizando el consumo de vacaciones.\n"
                f"- **Rendimiento:** Opciones de hasta **{best_pto.total_trip_days} días de viaje** utilizando únicamente "
                f"**{best_pto.work_days_needed} días de vacaciones** laborables (eficiencia **x{best_pto.pto_efficiency_ratio}**).\n"
            )

        # Justificación de Hubs
        hub_strat = ctx.get("hub_strategy")
        md.append("### 🌍 2. Estrategia de Hubs y Paradas Intermedias (Stopovers)")
        if hub_strat:
            md.append(f"{hub_strat}\n")
        else:
            md.append(
                "- **Objetivo:** Seleccionar aeropuertos clave con programas de escala (stopover) y tarifas de enlace "
                "competitivas para romper los vuelos largos y disfrutar de 1 a 3 días en un destino adicional sin billetes extra.\n"
            )

        # Justificación Open-Jaw
        open_jaw_strat = ctx.get("open_jaw_strategy")
        if open_jaw_strat:
            md.append("### 🔄 3. Estrategia Multiciudad (Open-Jaw)")
            md.append(f"{open_jaw_strat}\n")

        # Reglas de Confort y Métricas
        constraints = ctx.get("constraints", {})
        stats = ctx.get("stats", {})
        md.append("### 🛑 4. Reglas de Confort y Poda Algorítmica")
        max_scales = constraints.get("max_scales", 2)
        max_stops_leg = constraints.get("max_stops_per_leg", 1)
        tot_bp = stats.get("total_blueprints", len(ranked))
        tot_tasks = stats.get("total_leg_tasks", "deduplicadas")

        md.append(
            f"- **Máximo {max_stops_leg} escala técnica por billete:** Se descartan vuelos con conexiones múltiples agotadoras.\n"
            f"- **Máximo {max_scales} escalas totales por sentido:** 1 escala turística de varios días + como máximo 1 escala de conexión técnica.\n"
            f"- **Eficiencia de búsqueda:** Se evaluaron **{tot_bp} itinerarios combinatorios**, podados algorítmicamente a **{tot_tasks} consultas atómicas** para proteger la cuota de la API y garantizar datos frescos.\n"
        )

        if curated_data and curated_data.market_stats:
            m_stats = curated_data.market_stats
            md.append("### 📈 5. Análisis Determinista y Estadísticas de Mercado (Reducción Pareto)")
            md.append(
                f"- **Volumen evaluado:** Se procesaron y puntuaron **{curated_data.total_evaluated:,} itinerarios reales** de forma determinista.\n"
                f"- **Rango global de mercado:** desde **{self._format_price(m_stats['price_min'])}** hasta **{self._format_price(m_stats['price_max'])}** "
                f"(Precio mediano: **{self._format_price(m_stats['price_median'])}** | Media: **{self._format_price(m_stats['price_mean'])}**).\n"
            )
            if m_stats.get("scenario_min_prices"):
                scen_str = ", ".join([f"{scen}: **{self._format_price(pr)}**" for scen, pr in m_stats["scenario_min_prices"].items()])
                md.append(f"- **Tarifas mínimas por combinación origen-regreso:** {scen_str}.\n")
            if m_stats.get("hub_min_prices"):
                top_hubs = sorted(m_stats["hub_min_prices"].items(), key=lambda x: x[1])[:6]
                hub_str = ", ".join([f"{h}: **{self._format_price(pr)}**" for h, pr in top_hubs])
                md.append(f"- **Hubs más económicos encontrados:** {hub_str}.\n")

        curated_sel = curated_data.curated_selection if curated_data else None
        allowed_scenarios = ctx.get("allowed_scenarios")
        use_scenario_view = bool(allowed_scenarios)

        if use_scenario_view:
            options_by_scenario = self._get_options_by_scenario(
                ranked, scenarios_list=allowed_scenarios, limit_per_scenario=4, curated_selection=curated_sel
            )

            # 3. Cuadro Ampliado de Posibilidades (Tabla Grande Reducida)
            md.append("## 📊 Cuadro Ampliado de Posibilidades (Comparativa de Opciones)\n")
            for scen, top_4 in options_by_scenario.items():
                orig_code, ret_code = scen
                orig_name = stop_names.get(orig_code, orig_code)
                ret_name = stop_names.get(ret_code, ret_code)
                scen_itins = [
                    it for it in ranked
                    if it.origin == orig_code and (it.legs[-1].destination if it.legs else it.origin) == ret_code
                ]
                flag = "🇪🇸" if orig_code in ("MAD", "BIO", "BCN", "VLC", "AGP") else "🛫"
                if orig_code == ret_code:
                    md.append(f"### {flag} Opciones {orig_name} ➔ {dest_label} ➔ {orig_name} ({orig_code} ➔ {orig_code})\n")
                else:
                    md.append(f"### 🔄 Ruta Mixta Interciudad: {orig_name} ➔ {dest_label} ➔ {ret_name} ({orig_code} ➔ {ret_code})\n")

                md.append("| # | Ruta y Paradas | Fechas | Días Viaje | Días Vacaciones | Precio Total | Puntuación IA |")
                md.append("|---|----------------|:------:|:----------:|:---------------:|:------------:|:-------------:|")
                for i, it in enumerate(scen_itins[:15], 1):
                    md.append(
                        f"| {i:2d} | {it.route_summary} | {it.start_date.strftime('%d/%m')} – {it.end_date.strftime('%d/%m')} | "
                        f"{it.total_trip_days}d | {it.work_days_needed}d | **{self._format_price(it.total_price_eur)}** | **{it.ai_score}**/100 |"
                    )
                md.append("")

            # 4. Desglose Detallado de las Mejores Opciones (Estructura de Tarjetas Solicitada)
            md.append("## 🏆 Desglose Detallado de las Mejores Opciones\n")
            medals = ["🥇", "🥈", "🥉", "🏅"]

            for scen, top_4 in options_by_scenario.items():
                orig_code, ret_code = scen
                orig_name = stop_names.get(orig_code, orig_code)
                ret_name = stop_names.get(ret_code, ret_code)
                flag = "🇪🇸" if orig_code in ("MAD", "BIO", "BCN", "VLC", "AGP") else "🛫"
                if orig_code == ret_code:
                    md.append(f"### {flag} Las 4 Mejores Opciones: {orig_name} ➔ {dest_label} ➔ {orig_name} ({orig_code} ➔ {orig_code})\n")
                else:
                    md.append(f"### 🔄 Las 4 Mejores Opciones: Ruta Mixta {orig_name} ➔ {dest_label} ➔ {ret_name} ({orig_code} ➔ {ret_code})\n")

                for idx, it in enumerate(top_4, 1):
                    medal = medals[idx - 1] if idx <= len(medals) else "✈️"
                    card = self._format_itinerary_card(it, idx, medal, stop_names, dest_label)
                    md.append(card)
                    md.append("\n---\n")
        else:
            options_by_origin = self._get_options_by_origin(ranked, origins_list, limit_per_origin=4, curated_selection=curated_sel)

            # 3. Cuadro Ampliado de Posibilidades (Tabla Grande Reducida)
            md.append("## 📊 Cuadro Ampliado de Posibilidades (Comparativa de Opciones)\n")
            for orig_code in options_by_origin.keys():
                orig_name = stop_names.get(orig_code, orig_code)
                orig_itins = [it for it in ranked if it.origin == orig_code]

                flag = "🇪🇸" if orig_code in ("MAD", "BIO", "BCN", "VLC", "AGP") else "🛫"
                md.append(f"### {flag} Opciones desde {orig_name} ({orig_code})\n")

                md.append("| # | Ruta y Paradas | Fechas | Días Viaje | Días Vacaciones | Precio Total | Puntuación IA |")
                md.append("|---|----------------|:------:|:----------:|:---------------:|:------------:|:-------------:|")
                for i, it in enumerate(orig_itins[:15], 1):
                    md.append(
                        f"| {i:2d} | {it.route_summary} | {it.start_date.strftime('%d/%m')} – {it.end_date.strftime('%d/%m')} | "
                        f"{it.total_trip_days}d | {it.work_days_needed}d | **{self._format_price(it.total_price_eur)}** | **{it.ai_score}**/100 |"
                    )
                md.append("")

            # 4. Desglose Detallado de las Mejores Opciones (Estructura de Tarjetas Solicitada)
            md.append("## 🏆 Desglose Detallado de las Mejores Opciones\n")
            medals = ["🥇", "🥈", "🥉", "🏅"]

            for orig_code, top_4 in options_by_origin.items():
                orig_name = stop_names.get(orig_code, orig_code)
                flag = "🇪🇸" if orig_code in ("MAD", "BIO", "BCN", "VLC", "AGP") else "🛫"
                md.append(f"### {flag} Las 4 Mejores Opciones desde {orig_name} ({orig_code})\n")

                for idx, it in enumerate(top_4, 1):
                    medal = medals[idx - 1] if idx <= len(medals) else "✈️"
                    card = self._format_itinerary_card(it, idx, medal, stop_names, dest_label)
                    md.append(card)
                    md.append("\n---\n")

        # 5. Comparativa Multiciudad (Open-Jaw)
        return_origins = set()
        for it in ranked:
            if it.legs:
                last_leg = it.legs[-1]
                return_city = it.legs[1].origin if len(it.legs) == 3 and "inbound" in it.itinerary_id else last_leg.origin
                return_origins.add(return_city)

        if len(return_origins) > 1:
            md.append("## 🔄 Comparativa de Ciudades de Regreso (Multiciudad / Open-Jaw)\n")
            for r_code in sorted(return_origins):
                r_name = stop_names.get(r_code, r_code)
                r_its = [
                    it for it in ranked
                    if any(leg.origin == r_code and leg.destination in origins_list for leg in it.legs)
                    or (len(it.legs) == 3 and it.legs[1].origin == r_code)
                ]
                if r_its:
                    min_r = min(r_its, key=lambda x: x.total_price_eur)
                    md.append(
                        f"- **Regreso por {r_name} ({r_code}):** Mejor precio total: `{self._format_price(min_r.total_price_eur)}` "
                        f"({min_r.route_summary})\n"
                    )

            open_jaw_note = ctx.get("open_jaw_strategy")
            if open_jaw_note:
                md.append(f"\n> **💡 Consejo Multiciudad:** {open_jaw_note}\n")

        # 6. Comparativa de Rutas Mixtas Interciudad (si existen)
        cross_origin_itins = [it for it in ranked if it.origin != (it.legs[-1].destination if it.legs else it.origin)]
        if cross_origin_itins:
            md.append("## 🔄 Comparativa de Rutas Mixtas Interciudad (Empezar en una ciudad y volver por otra)\n")
            pair_map = {}
            for it in cross_origin_itins:
                ret_city = it.legs[-1].destination if it.legs else it.origin
                pair = (it.origin, ret_city)
                if pair not in pair_map or it.total_price_eur < pair_map[pair].total_price_eur:
                    pair_map[pair] = it

            for (o_c, r_c), best_it in sorted(pair_map.items()):
                o_n = stop_names.get(o_c, o_c)
                r_n = stop_names.get(r_c, r_c)
                md.append(
                    f"- **Salida {o_n} ({o_c}) ➔ Regreso {r_n} ({r_c}):** Mejor precio total: `{self._format_price(best_it.total_price_eur)}` "
                    f"({best_it.route_summary})\n"
                )
            md.append("")

        # 7. Consejos Logísticos de Stopover
        md.append("## 💡 Consejos Logísticos para las Escalas Intermedias (Stopovers)\n")
        md.append(
            "- **Equipaje Facturado:** En escalas de 24h a 72h, tu equipaje de bodega se retira en el aeropuerto intermedio. "
            "Te permite disponer cómodamente de tus pertenencias en el hotel céntrico antes del siguiente vuelo.\n"
            "- **Salud & Descanso:** Romper un trayecto intercontinental largo divide el desfase horario y evita el agotamiento de vuelos seguidos de más de 12 horas.\n"
            "- **Ahorro Estratégico:** Gracias a los acuerdos de conexión de aerolíneas puente (ej. Turkish, Arajet, Qatar, Air Europa), "
            "añadir un destino intermedio resulta habitualmente más económico que comprar billetes punto a punto por separado.\n"
        )

        return "\n".join(md)

