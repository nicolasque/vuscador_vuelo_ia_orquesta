"""AI Agent specialized in Holiday and PTO optimization."""

from datetime import date
from typing import List, Optional
from vusca.calendar_pto.holiday_engine import HolidayEngine
from vusca.models.calendar import PTOWindow
from vusca.agents.llm_client import GeminiClient


class PTOAgent:
    """Agent that analyzes calendar, holidays, and suggests optimal travel dates."""

    def __init__(
        self,
        country: str = "ES",
        subdivision: Optional[str] = "MD",
        llm_client: Optional[GeminiClient] = None,
    ):
        self.country = country
        self.subdivision = subdivision
        self.holiday_engine = HolidayEngine(country=country, subdiv=subdivision)
        self.llm = llm_client or GeminiClient()

    def select_best_windows(
        self,
        start_search: date,
        end_search: date,
        max_pto_days: int = 5,
        min_total_days: int = 5,
        max_total_days: int = 21,
        top_k: int = 4,
    ) -> List[PTOWindow]:
        """Calculates optimal date windows and enriches them with strategic insights."""
        windows = self.holiday_engine.find_optimal_windows(
            start_search=start_search,
            end_search=end_search,
            max_pto_days=max_pto_days,
            min_total_days=min_total_days,
            max_total_days=max_total_days,
            top_k=top_k,
        )

        if not windows:
            # Fallback window if no optimal holidays found
            direct_end = start_search + (end_search - start_search)
            windows = [
                PTOWindow(
                    start_date=start_search,
                    end_date=direct_end,
                    total_days=(direct_end - start_search).days + 1,
                    work_days_needed=max_pto_days,
                    weekend_days=2,
                    holiday_days=0,
                    efficiency_ratio=1.0,
                    summary="Ventana estándar directa",
                )
            ]

        # Enrich summaries with Gemini if available, or generate detailed heuristic summary
        if self.llm.is_available:
            self._enrich_with_gemini(windows)
        else:
            self._enrich_heuristic(windows)

        return windows

    def _enrich_heuristic(self, windows: List[PTOWindow]):
        """Generates clear, informative heuristic summaries for each window."""
        for w in windows:
            if w.holidays_names:
                h_str = ", ".join(w.holidays_names)
                w.summary = (
                    f"Aprovecha el festivo de {h_str} sumado a {w.weekend_days} días de fin de semana "
                    f"para disfrutar {w.total_days} días pidiendo solo {w.work_days_needed} días de vacaciones"
                )
            else:
                w.summary = (
                    f"Ventana balanceada de {w.total_days} días con {w.weekend_days} días de fin de semana "
                    f"usando {w.work_days_needed} días laborables"
                )

    def get_strategy_rationale(self, windows: List[PTOWindow]) -> str:
        """Returns a clear explanation of why these windows were passed to the search engine."""
        if not windows:
            return "No se configuraron ventanas específicas de festivos."

        best = max(windows, key=lambda w: w.efficiency_ratio)
        holidays_all = set()
        for w in windows:
            holidays_all.update(w.holidays_names)

        lines = [
            f"- **Objetivo Calendario:** Maximizar los días naturales fuera de la oficina minimizando el consumo de vacaciones (PTO).",
            f"- **Festivos Oficiales Detectados:** {', '.join(holidays_all) if holidays_all else 'Fines de semana estratégicos'} en {self.country} ({self.subdivision or 'Nacional'}).",
            f"- **Rendimiento Máximo:** Hasta **{best.total_days} días de viaje** utilizando únicamente **{best.work_days_needed} días de vacaciones** (multiplicador de eficiencia **x{best.efficiency_ratio}**).",
            f"- **Por qué se alimenta al motor de esta manera:** Permite a la combinatoria explorar fechas de salida en viernes o vísperas de festivo y regresos en domingo/festivo, reduciendo radicalmente el coste en días laborables y buscando tarifas más económicas con variaciones de ±1 a ±2 días.",
        ]
        return "\n".join(lines)

    def _enrich_with_gemini(self, windows: List[PTOWindow]):
        prompt = (
            f"Como agente experto en optimización de vacaciones laborales en {self.country} ({self.subdivision or ''}), "
            f"analiza estas {len(windows)} ventanas de viaje encontradas:\n\n"
        )
        for idx, w in enumerate(windows, 1):
            prompt += (
                f"{idx}. Del {w.start_date} al {w.end_date} ({w.total_days} días en total). "
                f"Días de trabajo requeridos: {w.work_days_needed}. Fines de semana: {w.weekend_days}. "
                f"Festivos aprovechados: {', '.join(w.holidays_names) or 'Ninguno'}.\n"
            )
        prompt += (
            "\nPara cada una, genera en 1 sola frase concisa en español el motivo estratégico laboral "
            "(ej: 'Aprovecha el puente nacional del 12 de octubre y pide 4 días para desconectar 9 días seguidos'). "
            "Responde en formato JSON con la clave 'insights' siendo una lista de strings con una frase por ventana."
        )

        system_inst = "Eres un estratega experto en maximizar días de vacaciones y puentes festivos."
        res = self.llm.generate_json(prompt, system_instruction=system_inst)
        if res and "insights" in res and len(res["insights"]) == len(windows):
            for w, text in zip(windows, res["insights"]):
                w.summary = f"{text} (Eficiencia x{w.efficiency_ratio})"
        else:
            self._enrich_heuristic(windows)

