"""Rich Command Line Interface for Vusca."""

import argparse
import sys
import uuid
from datetime import date, datetime, timedelta
from typing import Optional, List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.prompt import Prompt, IntPrompt
from rich.markdown import Markdown

from vusca.agents.pto_agent import PTOAgent
from vusca.agents.route_agent import RouteAgent, GLOBAL_HUBS
from vusca.agents.synthesis_agent import SynthesisAgent
from vusca.core.combinator import RouteCombinator
from vusca.core.db import DatabaseManager
from vusca.core.search_engine import SearchEngine
from vusca.models.search import SearchJob, JobStatus
from vusca.providers import get_flight_provider
from vusca import config

console = Console()


def print_banner():
    banner_text = (
        "[bold cyan]✈️  VUSCA - Orquestador Inteligente de Vuelos con IA[/bold cyan]\n"
        "[italic white]Optimizador de Días de Vacaciones (PTO) & Rutas Multidestino con Stopovers[/italic white]"
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def create_progress_logger(progress: Progress, p_task, title: str = "Consultando tramos"):
    """Creates a callback that logs each completed atomic search leg into the console above the progress bar."""
    def on_progress(task_item, current, total):
        pct = (current * 100.0 / total) if total else 100.0
        price_info = f" (desde [bold yellow]{task_item.min_price_eur:.0f} €[/bold yellow])" if task_item.min_price_eur is not None else ""
        dur_info = f" [dim]({task_item.elapsed_seconds}s)[/dim]" if task_item.elapsed_seconds is not None else ""

        if task_item.status == "CACHED":
            tag = "[bold blue]💾 BD LOCAL[/bold blue]"
            detail = f"[blue]{task_item.results_count} ofertas[/blue]{price_info}"
        elif task_item.status == "NOT_IN_CACHE":
            tag = "[dim yellow]⚡ SIN CACHÉ[/dim yellow]"
            detail = "[dim]Omitido (--cache-only)[/dim]"
        elif task_item.status == "SUCCESS":
            provider_label = task_item.provider_name or "API"
            tag = f"[bold green]🌐 API {provider_label}[/bold green]"
            detail = f"[green]{task_item.results_count} ofertas recibidas[/green]{price_info}"
        else:
            tag = "[bold red]❌ FALLO API[/bold red]"
            err = task_item.error_message or "Sin vuelos disponibles"
            if len(err) > 60:
                err = err[:57] + "..."
            detail = f"[red]{err}[/red]"

        progress.console.print(
            f"[dim][{current:03d}/{total:03d} {pct:3.0f}%][/dim] {tag} ➔ "
            f"[bold cyan]{task_item.origin} ➔ {task_item.destination}[/bold cyan] "
            f"[white]({task_item.travel_date})[/white] | {detail}{dur_info}"
        )
        progress.update(
            p_task,
            completed=current,
            description=f"[cyan]{title} ({current}/{total})...[/cyan]",
        )
    return on_progress


def run_search_flow(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    origins: Optional[List[str]] = None,
    destinations: Optional[List[str]] = None,
    max_pto_days: int = 5,
    month_str: Optional[str] = None,
    year: Optional[int] = None,
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None,
    event: Optional[str] = None,
    country: str = "ES",
    subdivision: Optional[str] = "MD",
    provider_name: Optional[str] = None,
    return_destinations: Optional[List[str]] = None,
    return_arrivals: Optional[List[str]] = None,
    mix_origins: bool = False,
    min_stopover_days: int = 1,
    max_stopover_days: int = 3,
    min_trip_days: int = 5,
    max_trip_days: int = 25,
    stopovers: Optional[List[str]] = None,
    stopover_preset: Optional[str] = None,
    outbound_stopovers: Optional[List[str]] = None,
    return_stopovers: Optional[List[str]] = None,
    include_dual_stopovers: bool = False,
    allowed_scenarios: Optional[List[Tuple[str, str]]] = None,
    priority: str = "balanced",
    top_k_windows: int = 4,
    max_scales: int = 2,
    max_stops_per_leg: int = 1,
    date_flexibility: int = 0,
    dry_run: bool = False,
    cache_only: bool = False,
    output_file: Optional[str] = None,
):
    print_banner()

    today = date.today()
    target_year = year or (datetime.strptime(month_str, "%Y-%m").year if (month_str and "-" in month_str) else today.year)

    # 1. Resolve date search range from explicit dates, preconfigured events, or month/year
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str.strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            console.print("[red]Error: El formato de fecha debe ser AAAA-MM-DD (ej. 2027-03-15)[/red]")
            return
    elif event:
        ev = event.lower().replace("_", "-")
        if ev in ("semana-santa", "easter", "semanasanta", "pascua"):
            start_date = date(target_year, 3, 1)
            end_date = date(target_year, 4, 30)
        elif ev in ("puente-mayo", "mayo"):
            start_date = date(target_year, 4, 25)
            end_date = date(target_year, 5, 31)
        elif ev in ("verano", "agosto"):
            start_date = date(target_year, 7, 1)
            end_date = date(target_year, 8, 31)
        elif ev in ("pilar", "octubre"):
            start_date = date(target_year, 10, 1)
            end_date = date(target_year, 10, 31)
        elif ev in ("navidad", "fin-de-ano"):
            start_date = date(target_year, 12, 15)
            end_date = date(target_year + 1, 1, 15)
        else:
            start_date = date(target_year, 1, 1)
            end_date = date(target_year, 12, 31)
    elif month_str:
        try:
            if "-" in month_str:
                target_dt = datetime.strptime(month_str, "%Y-%m")
                m_year = target_dt.year
                m_month = target_dt.month
            else:
                m_year = target_year
                m_month = int(month_str)
            start_date = date(m_year, m_month, 1)
            # Allow return trips that extend into the following month for long journeys
            lead_days = max(max_trip_days, 30)
            end_date = start_date + timedelta(days=31 + lead_days)
        except ValueError:
            console.print("[red]Error: El formato de mes debe ser AAAA-MM (ej. 2027-03) o el número de mes (1-12)[/red]")
            return
    elif year:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else:
        # Default next month to end of year
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, 12, 31)

    db = DatabaseManager()
    provider = get_flight_provider(provider_name)

    # Normalize origins and destinations
    if origins:
        origins_list = [o.strip().upper() for o in origins if o.strip()]
    elif origin:
        origins_list = [o.strip().upper() for o in origin.split(",") if o.strip()]
    else:
        origins_list = ["MAD"]

    if destinations:
        destinations_list = [d.strip().upper() for d in destinations if d.strip()]
    elif destination:
        destinations_list = [d.strip().upper() for d in destination.split(",") if d.strip()]
    else:
        destinations_list = ["TYO"]

    primary_origin = origins_list[0]
    primary_destination = destinations_list[0]
    ret_dest_list = [r.strip().upper() for r in return_destinations if r.strip()] if return_destinations else list(destinations_list)

    job_id = f"job_{uuid.uuid4().hex[:8]}"
    console.print(f"[bold green]▶ Iniciando Misión de Búsqueda:[/bold green] [yellow]{job_id}[/yellow]")
    console.print(
        f"• Origen(es): [bold]{', '.join(origins_list)}[/bold] ➔ Destino(s): [bold]{', '.join(destinations_list)}[/bold]\n"
        f"• Regreso(s) Posible(s): [bold]{', '.join(ret_dest_list)}[/bold]\n"
        f"• Rango de Salida: [bold]{start_date}[/bold] al [bold]{end_date}[/bold]\n"
        f"• Duración de Viaje Deseada: [bold]{min_trip_days}[/bold] a [bold]{max_trip_days}[/bold] días\n"
        f"• Máximo días de vacaciones (PTO): [bold]{max_pto_days}[/bold] días\n"
        f"• Doble Escala Turística (Dual Stopover): [bold]{'ACTIVADA' if include_dual_stopovers else 'Desactivada'}[/bold]\n"
        f"• Prioridad de Búsqueda: [bold]{priority.upper()}[/bold]\n"
        f"• Escalas Máximas por Trayecto: [bold]{max_scales}[/bold] (incluyendo escala principal)\n"
        f"• Flexibilidad de Fechas: [bold]±{date_flexibility} días[/bold]\n"
        f"• Proveedor de vuelos: [bold]{provider.name}[/bold]\n"
    )

    # -------------------------------------------------------------
    # 1. Agente PTO & Calendario
    # -------------------------------------------------------------
    with console.status("[bold yellow]🤖 [1/5] Agente PTO & Calendario analizando festivos y puentes...[/bold yellow]"):
        pto_agent = PTOAgent(country=country, subdivision=subdivision)
        optimal_windows = pto_agent.select_best_windows(
            start_search=start_date,
            end_search=end_date,
            max_pto_days=max_pto_days,
            min_total_days=min_trip_days,
            max_total_days=max_trip_days,
            top_k=top_k_windows,
        )

    if date_flexibility > 0 and optimal_windows:
        with console.status(f"[bold yellow]🗓️ Generando variaciones de fechas flexibles (±{date_flexibility} días)...[/bold yellow]"):
            candidate_windows = pto_agent.holiday_engine.generate_flexible_variations(
                base_windows=optimal_windows,
                flexibility_days=date_flexibility,
                max_pto_days=max_pto_days,
                min_total_days=min_trip_days,
                max_total_days=max_trip_days,
            )
    else:
        candidate_windows = optimal_windows

    win_table = Table(title="🗓️ Ventanas de Viaje Base Más Eficientes (Optimizadas por IA)", border_style="yellow")
    win_table.add_column("#", justify="center", style="cyan")
    win_table.add_column("Fechas de Viaje", style="white")
    win_table.add_column("Días Totales", justify="center", style="green")
    win_table.add_column("Días Vacaciones", justify="center", style="bold red")
    win_table.add_column("Eficiencia", justify="center", style="bold green")
    win_table.add_column("Estrategia Laboral", style="italic")

    for i, w in enumerate(optimal_windows, 1):
        win_table.add_row(
            str(i),
            f"{w.start_date.strftime('%d/%m')} ➔ {w.end_date.strftime('%d/%m')}",
            f"{w.total_days}d",
            f"{w.work_days_needed}d",
            f"x{w.efficiency_ratio}",
            w.summary,
        )
    console.print(win_table)
    pto_rationale = pto_agent.get_strategy_rationale(optimal_windows)
    console.print(Panel(pto_rationale, title="🎯 Justificación de Calendario (Por Qué se Buscan Estas Fechas)", border_style="yellow"))
    if date_flexibility > 0:
        console.print(f"[cyan]ℹ️ Flexibilidad activa: se evaluarán [bold]{len(candidate_windows)}[/bold] combinaciones de fechas (±{date_flexibility} días).[/cyan]\n")
    else:
        console.print()

    # -------------------------------------------------------------
    # 2. Agente Estratega de Rutas y Stopovers
    # -------------------------------------------------------------
    route_agent = RouteAgent()
    outbound_codes: List[str] = []
    return_codes: List[str] = []

    if outbound_stopovers:
        outbound_codes = [s.strip().upper() for s in outbound_stopovers if s.strip()]
    elif stopovers:
        outbound_codes = [s.strip().upper() for s in stopovers if s.strip()]
    elif stopover_preset:
        outbound_codes, _, _ = route_agent.get_preset_stopovers(stopover_preset)

    if return_stopovers:
        return_codes = [s.strip().upper() for s in return_stopovers if s.strip()]
    elif stopovers:
        return_codes = [s.strip().upper() for s in stopovers if s.strip()]
    elif stopover_preset:
        return_codes, _, _ = route_agent.get_preset_stopovers(stopover_preset)

    if not outbound_codes and not return_codes:
        with console.status("[bold magenta]🤖 [2/5] Agente Estratega ideando paradas intermedias (stopovers)...[/bold magenta]"):
            candidate_codes, stopover_names, stopover_reasons = route_agent.recommend_stopovers(
                origin=primary_origin,
                destination=primary_destination,
                top_k=4,
            )
            outbound_codes = list(candidate_codes)
            return_codes = list(candidate_codes)
    else:
        candidate_codes = list(dict.fromkeys(outbound_codes + return_codes))
        stopover_names = {c: GLOBAL_HUBS.get(c, {}).get("name", c) for c in candidate_codes}
        stopover_reasons = {
            c: GLOBAL_HUBS.get(c, {}).get("description", "Escala intermedia seleccionada")
            for c in candidate_codes
        }

    route_table = Table(title="🌍 Paradas Intermedias (Stopovers) Evaluadas", border_style="magenta")
    route_table.add_column("Hub", justify="center", style="bold cyan")
    route_table.add_column("Ciudad", style="bold white")
    route_table.add_column("Uso en Ruta", justify="center", style="bold yellow")
    route_table.add_column("Motivo Estratégico & Ahorro", style="italic")

    for code in candidate_codes:
        uso = []
        if code in outbound_codes:
            uso.append("Ida")
        if code in return_codes:
            uso.append("Vuelta")
        route_table.add_row(
            code,
            stopover_names.get(code, code),
            " & ".join(uso) or "General",
            stopover_reasons.get(code, "Hub estratégico de conexión internacional"),
        )
    console.print(route_table)

    hub_rationale = route_agent.get_hub_strategy_explanation(candidate_codes)
    open_jaw_strategy = route_agent.get_open_jaw_strategy(destinations_list, ret_dest_list)
    console.print(
        Panel(
            f"{hub_rationale}\n\n- **Estrategia Open-Jaw (Multiciudad):** {open_jaw_strategy}",
            title="🎯 Justificación de Rutas y Hubs (Por Qué se Alimenta al Motor)",
            border_style="magenta",
        )
    )
    console.print()

    # -------------------------------------------------------------
    # 3. Motor Combinatorio en Python
    # -------------------------------------------------------------
    known_names = {
        "TYO": "Tokio", "NRT": "Tokio Narita", "HND": "Tokio Haneda",
        "KIX": "Osaka Kansai", "OSA": "Osaka", "ITM": "Osaka Itami",
        "MAD": "Madrid", "BCN": "Barcelona", "BIO": "Bilbao", "BKK": "Bangkok",
        "SIN": "Singapur", "ICN": "Seúl", "TPE": "Taipéi", "KUL": "Kuala Lumpur",
        "HKG": "Hong Kong", "DOH": "Doha", "DXB": "Dubái",
        "IST": "Estambul", "AUH": "Abu Dhabi",
        "BOG": "Bogotá", "MDE": "Medellín", "CTG": "Cartagena",
        "PTY": "Ciudad de Panamá", "CUN": "Cancún", "SDQ": "Santo Domingo",
        "LIS": "Lisboa", "MIA": "Miami", "CMN": "Casablanca",
        "GRU": "São Paulo", "GIG": "Río de Janeiro", "SSA": "Salvador de Bahía",
        "PEN": "Penang", "SGN": "Ho Chi Minh", "HAN": "Hanói", "DPS": "Bali", "CAI": "El Cairo",
        "FRA": "Frankfurt", "MUC": "Múnich", "CDG": "París", "AMS": "Ámsterdam",
        "ZRH": "Zúrich", "HEL": "Helsinki", "LHR": "Londres", "VIE": "Viena",
        "BRU": "Bruselas", "MXP": "Milán",
    }
    for k, v in known_names.items():
        if k not in stopover_names:
            stopover_names[k] = v

    effective_return_arrivals = return_arrivals if return_arrivals is not None else (origins_list if mix_origins else None)

    with console.status("[bold blue]⚙️ [3/5] Motor Combinatorio generando permutaciones y podando tareas...[/bold blue]"):
        combinator = RouteCombinator(
            origins=origins_list,
            destinations=destinations_list,
            candidate_windows=candidate_windows,
            candidate_stopovers=candidate_codes,
            outbound_stopovers=outbound_codes,
            return_stopovers=return_codes,
            stopover_names=stopover_names,
            return_destinations=ret_dest_list,
            return_arrivals=effective_return_arrivals,
            allowed_scenarios=allowed_scenarios,
            min_stopover_days=min_stopover_days,
            max_stopover_days=max_stopover_days,
            include_dual_stopovers=include_dual_stopovers,
        )
        blueprints, leg_tasks = combinator.generate_blueprints()

    # Si es modo simulación (dry-run), mostrar desglose y presupuesto sin llamar a la API
    if dry_run:
        stats = combinator.estimate_task_volume(db=db)
        dry_table = Table(title="🔍 Simulación Previa / Dry-Run (Matriz de Búsqueda & Presupuesto API)", border_style="cyan")
        dry_table.add_column("Métrica", style="bold white")
        dry_table.add_column("Valor Estimado", justify="right", style="bold green")

        dry_table.add_row("Ciudades de Origen", ", ".join(origins_list))
        dry_table.add_row("Ciudades de Destino", ", ".join(destinations_list))
        dry_table.add_row("Aeropuertos de Regreso", ", ".join(ret_dest_list))
        dry_table.add_row("Escalas de Ida (Outbound)", ", ".join(outbound_codes))
        dry_table.add_row("Escalas de Vuelta (Inbound)", ", ".join(return_codes))
        dry_table.add_row("Ventanas de Fechas Evaluadas", str(len(candidate_windows)))
        dry_table.add_row("Total Itinerarios Combinatorios (Blueprints)", f"[bold cyan]{stats['total_blueprints']}[/bold cyan]")
        dry_table.add_row("Consultas Atómicas a la API (Deduplicadas)", f"[bold white]{stats['total_leg_tasks']}[/bold white]")
        dry_table.add_row("Consultas en Caché Local (SQLite)", f"[bold green]{stats['cached_leg_tasks']}[/bold green]")
        dry_table.add_row("Llamadas Reales Requeridas a la API", f"[bold yellow]{stats['api_calls_needed']}[/bold yellow]")

        console.print(dry_table)
        console.print()

        corridor_table = Table(title="✈️ Desglose por Corredores de Vuelo", border_style="magenta")
        corridor_table.add_column("Corredor", style="bold cyan")
        corridor_table.add_column("Consultas de Fechas", justify="center", style="white")
        for corridor, count in sorted(stats["corridors"].items(), key=lambda x: -x[1]):
            corridor_table.add_row(corridor, str(count))
        console.print(corridor_table)
        console.print("\n[bold green]✓ Simulación completada con éxito. Presupuesto de API validado sin consumo de cuota.[/bold green]\n")
        return

    console.print(
        f"[green]✓ Combinatoria calculada:[/green] Se han generado [bold]{len(blueprints)}[/bold] posibles itinerarios completos.\n"
        f"[green]✓ Poda algorítmica realizada:[/green] Se requieren únicamente [bold]{len(leg_tasks)}[/bold] consultas atómicas a la API.\n"
    )

    # -------------------------------------------------------------
    # 4. Orquestador de Búsqueda y APIs (Resiliente)
    # -------------------------------------------------------------
    search_job = SearchJob(
        job_id=job_id,
        origin=", ".join(origins_list),
        final_destination=", ".join(destinations_list),
        status=JobStatus.PENDING,
        country=country,
        subdivision=subdivision,
        max_pto_days=max_pto_days,
        preferred_month=month_str,
        return_destinations=ret_dest_list,
        candidate_windows=candidate_windows,
        candidate_stopovers=candidate_codes,
        stopover_names=stopover_names,
        tasks=leg_tasks,
    )
    db.save_job(search_job)

    search_engine = SearchEngine(provider=provider, db=db)

    console.print("[bold yellow]⚡ [4/5] Ejecutando consultas a APIs de vuelo con control de rate-limit y caché...[/bold yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        p_task = progress.add_task("[cyan]Consultando tramos...", total=len(leg_tasks))
        on_progress = create_progress_logger(progress, p_task, title="Consultando tramos")

        itineraries = search_engine.execute_job(
            job=search_job,
            blueprints=blueprints,
            progress_callback=on_progress,
            max_scales_per_direction=max_scales,
            max_stops_per_leg=max_stops_per_leg,
            cache_only=cache_only,
        )

    cached_count = sum(1 for t in search_job.tasks if t.status == "CACHED")
    api_count = sum(1 for t in search_job.tasks if t.status == "SUCCESS")
    failed_count = sum(1 for t in search_job.tasks if t.status == "FAILED")
    skipped_count = sum(1 for t in search_job.tasks if t.status == "NOT_IN_CACHE")
    total_offers = sum(t.results_count for t in search_job.tasks)
    summary_parts = [f"[bold blue]💾 {cached_count} en BD local[/bold blue]", f"[bold green]🌐 {api_count} vía API[/bold green]"]
    if skipped_count:
        summary_parts.append(f"[dim yellow]⚡ {skipped_count} sin caché local (modo offline)[/dim yellow]")
    if failed_count:
        summary_parts.append(f"[bold red]❌ {failed_count} fallidas[/bold red]")
    console.print(
        f"[bold green]✓ Fase de consultas finalizada:[/bold green] {' | '.join(summary_parts)} | "
        f"[yellow]{total_offers:,} ofertas evaluadas[/yellow] ➔ "
        f"[bold white]{len(itineraries)} itinerarios viables estructurados[/bold white].\n"
    )

    # -------------------------------------------------------------
    # 5. Agente Sintetizador & Analista de IA
    # -------------------------------------------------------------
    with console.status("[bold green]🤖 [5/5] Agente Sintetizador de IA analizando y calificando resultados...[/bold green]"):
        synthesis_agent = SynthesisAgent()
        ranked_itineraries = synthesis_agent.evaluate_and_rank(itineraries, priority=priority)

        # Filter strictly by min_trip_days if specified
        if min_trip_days > 5:
            ranked_itineraries = [it for it in ranked_itineraries if it.total_trip_days >= min_trip_days]

        search_context = {
            "priority": priority,
            "origins": origins_list,
            "destinations": destinations_list,
            "return_destinations": ret_dest_list,
            "return_arrivals": effective_return_arrivals,
            "allowed_scenarios": allowed_scenarios,
            "mix_origins": mix_origins,
            "candidate_windows": candidate_windows,
            "optimal_windows": optimal_windows,
            "candidate_stopovers": candidate_codes,
            "stopover_names": stopover_names,
            "pto_strategy": pto_rationale,
            "hub_strategy": hub_rationale,
            "open_jaw_strategy": open_jaw_strategy,
            "constraints": {
                "priority": priority,
                "max_scales": max_scales,
                "max_stops_per_leg": max_stops_per_leg,
                "max_pto_days": max_pto_days,
                "min_trip_days": min_trip_days,
                "max_trip_days": max_trip_days,
                "date_flexibility": date_flexibility,
            },
            "stats": {
                "total_blueprints": len(blueprints),
                "total_leg_tasks": len(leg_tasks),
            },
        }

        report_markdown = synthesis_agent.generate_final_report(
            origin=origin or ", ".join(origins_list),
            destination=destination or ", ".join(destinations_list),
            itineraries=ranked_itineraries,
            candidate_stopover_names=stopover_names,
            search_context=search_context,
        )
        search_job.ai_final_analysis = report_markdown
        db.save_job(search_job)

    # Render results in terminal
    console.print()
    console.print(Panel("[bold green]🏆 RESULTADOS Y RECOMENDACIÓN FINAL DE LA IA[/bold green]", border_style="green"))
    console.print(Markdown(report_markdown))

    # Save to file if requested or by default
    orig_slug = "_".join(origins_list)
    dest_slug = "_".join(destinations_list)
    out_path = output_file or f"reporte_{orig_slug}_{dest_slug}_{job_id}.md"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report_markdown)
        console.print(f"\n[bold cyan]💾 Informe guardado en archivo:[/bold cyan] [yellow]{out_path}[/yellow]")
    except Exception as e:
        console.print(f"[red]No se pudo guardar el archivo {out_path}: {e}[/red]")


def resume_flow(job_id: str):
    print_banner()
    db = DatabaseManager()
    job = db.get_job(job_id)
    if not job:
        console.print(f"[bold red]Error: No se encontró el trabajo de búsqueda con ID {job_id}[/bold red]")
        return

    console.print(f"[bold green]▶ Reanudando Misión de Búsqueda:[/bold green] [yellow]{job_id}[/yellow]")
    console.print(f"• Origen: {job.origin} ➔ Destino: {job.final_destination}")
    console.print(f"• Estado anterior: [bold]{job.status}[/bold]")
    console.print(f"• Progreso: {job.completed_task_count}/{job.total_task_count} tramos completados\n")

    if job.status == JobStatus.COMPLETED and job.ai_final_analysis:
        console.print("[bold yellow]Este trabajo ya había finalizado. Mostrando informe:[/bold yellow]\n")
        console.print(Markdown(job.ai_final_analysis))
        return

    # Reconstruct blueprints
    combinator = RouteCombinator(
        origin=job.origin,
        destination=job.final_destination,
        candidate_windows=job.candidate_windows,
        candidate_stopovers=job.candidate_stopovers,
        stopover_names=job.stopover_names,
        min_stopover_days=job.min_stopover_days,
        max_stopover_days=job.max_stopover_days,
    )
    blueprints, _ = combinator.generate_blueprints()

    provider = get_flight_provider()
    search_engine = SearchEngine(provider=provider, db=db)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        p_task = progress.add_task("[cyan]Reanudando consultas...", total=len(job.tasks))
        on_progress = create_progress_logger(progress, p_task, title="Reanudando consultas")

        itineraries = search_engine.execute_job(
            job=job,
            blueprints=blueprints,
            progress_callback=on_progress,
        )

    cached_count = sum(1 for t in job.tasks if t.status == "CACHED")
    api_count = sum(1 for t in job.tasks if t.status == "SUCCESS")
    failed_count = sum(1 for t in job.tasks if t.status == "FAILED")
    total_offers = sum(t.results_count for t in job.tasks)
    summary_parts = [f"[bold blue]💾 {cached_count} en BD local[/bold blue]", f"[bold green]🌐 {api_count} vía API[/bold green]"]
    if failed_count:
        summary_parts.append(f"[bold red]❌ {failed_count} fallidas[/bold red]")
    console.print(
        f"[bold green]✓ Búsqueda finalizada con éxito:[/bold green] {' | '.join(summary_parts)} | "
        f"[yellow]{total_offers:,} ofertas evaluadas[/yellow] ➔ "
        f"[bold white]{len(itineraries)} itinerarios viables estructurados[/bold white].\n"
    )

    synthesis_agent = SynthesisAgent()
    ranked = synthesis_agent.evaluate_and_rank(itineraries)

    origins_list = [o.strip() for o in job.origin.split(",") if o.strip()]
    destinations_list = [d.strip() for d in job.final_destination.split(",") if d.strip()]
    ret_dest_list = job.return_destinations or destinations_list

    route_agent = RouteAgent()
    pto_agent = PTOAgent(country=job.country, subdivision=job.subdivision)

    search_context = {
        "origins": origins_list,
        "destinations": destinations_list,
        "return_destinations": ret_dest_list,
        "candidate_windows": job.candidate_windows,
        "candidate_stopovers": job.candidate_stopovers,
        "stopover_names": job.stopover_names,
        "pto_strategy": pto_agent.get_strategy_rationale(job.candidate_windows),
        "hub_strategy": route_agent.get_hub_strategy_explanation(job.candidate_stopovers),
        "open_jaw_strategy": route_agent.get_open_jaw_strategy(destinations_list, ret_dest_list),
        "constraints": {
            "max_scales": 2,
            "max_stops_per_leg": 1,
            "max_pto_days": job.max_pto_days,
        },
        "stats": {
            "total_blueprints": len(blueprints),
            "total_leg_tasks": len(job.tasks),
        },
    }

    report_md = synthesis_agent.generate_final_report(
        origin=job.origin,
        destination=job.final_destination,
        itineraries=ranked,
        candidate_stopover_names=job.stopover_names,
        search_context=search_context,
    )
    job.ai_final_analysis = report_md
    db.save_job(job)

    console.print(Markdown(report_md))


def list_jobs_flow():
    print_banner()
    db = DatabaseManager()
    jobs = db.list_jobs(limit=20)
    if not jobs:
        console.print("[yellow]No hay trabajos de búsqueda registrados todavía.[/yellow]")
        return

    table = Table(title="📋 Historial de Búsquedas", border_style="cyan")
    table.add_column("Job ID", style="yellow")
    table.add_column("Ruta", style="white")
    table.add_column("Estado", style="bold")
    table.add_column("Última Actualización", style="italic")

    for j in jobs:
        st = j["status"]
        st_style = "green" if st == "COMPLETED" else ("yellow" if st == "IN_PROGRESS" else "white")
        table.add_row(
            j["job_id"],
            f"{j['origin']} ➔ {j['destination']}",
            f"[{st_style}]{st}[/{st_style}]",
            str(j["updated_at"])[:19],
        )
    console.print(table)


def interactive_wizard():
    print_banner()
    console.print("[bold cyan]🧙 Asistente Interactivo de Búsqueda Avanzada de Vuelos[/bold cyan]\n")

    origins_raw = Prompt.ask("Aeropuerto(s) de origen (separados por coma)", default="MAD, BIO").upper()
    destinations_raw = Prompt.ask("Aeropuerto(s) de destino final (separados por coma)", default="KUL, SIN").upper()

    origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
    destinations = [d.strip() for d in destinations_raw.split(",") if d.strip()]

    current_year = date.today().year
    year_input = IntPrompt.ask("Año deseado para viajar", default=current_year + 1)

    timing_type = Prompt.ask(
        "Tipo de fechas",
        choices=["evento", "mes", "fechas-exactas", "todo-el-ano"],
        default="evento",
    )

    event_val = None
    month_val = None
    start_val = None
    end_val = None

    if timing_type == "evento":
        event_val = Prompt.ask(
            "Selecciona el evento o festivo",
            choices=["semana-santa", "puente-mayo", "verano", "pilar", "navidad"],
            default="semana-santa",
        )
    elif timing_type == "mes":
        month_val = Prompt.ask(
            "Mes deseado (AAAA-MM o 1-12)",
            default=f"{year_input}-03",
        )
    elif timing_type == "fechas-exactas":
        start_val = Prompt.ask("Fecha de inicio (AAAA-MM-DD)", default=f"{year_input}-03-15")
        end_val = Prompt.ask("Fecha de fin (AAAA-MM-DD)", default=f"{year_input}-04-11")

    min_days = IntPrompt.ask("Duración mínima del viaje en días (ej. 10 para puente, 21 para gran viaje)", default=10)
    max_days = IntPrompt.ask("Duración máxima del viaje en días", default=max(min_days + 4, 25))
    days_pto = IntPrompt.ask(
        "Máximo de días de vacaciones de trabajo a gastar (PTO)",
        default=min(14, max(int(min_days * 0.6), 5)),
    )

    dual_stop = Prompt.ask("¿Permitir doble escala turística (ida y vuelta)?", choices=["s", "n"], default="s") == "s"

    priority_val = Prompt.ask(
        "Criterio de optimización",
        choices=["balanced", "cheapest", "pto"],
        default="balanced",
    )

    provider_choice = Prompt.ask(
        "Proveedor de vuelos",
        choices=["auto", "google", "pool", "mock", "rapidapi", "amadeus"],
        default="auto",
    )

    run_search_flow(
        origins=origins,
        destinations=destinations,
        origin=origins[0],
        destination=destinations[0],
        year=year_input,
        event=event_val,
        month_str=month_val,
        start_date_str=start_val,
        end_date_str=end_val,
        min_trip_days=min_days,
        max_trip_days=max_days,
        max_pto_days=days_pto,
        include_dual_stopovers=dual_stop,
        priority=priority_val,
        provider_name=provider_choice,
    )


def cli_entrypoint():
    parser = argparse.ArgumentParser(
        description="Vusca - Orquestador Inteligente de Vuelos con IA, Optimización PTO y Stopovers"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Ejecutar búsqueda avanzada de vuelos")
    search_parser.add_argument("--origin", "-o", help="Código IATA de origen (ej. MAD)")
    search_parser.add_argument("--origins", help="Códigos IATA de origen separados por coma (ej. MAD,BIO)")
    search_parser.add_argument("--destination", "-d", help="Código IATA de destino (ej. TYO, BKK, KUL)")
    search_parser.add_argument("--destinations", help="Códigos IATA de destino separados por coma (ej. KUL,SIN)")
    search_parser.add_argument("--return-destinations", "-rd", help="Aeropuertos de regreso alternativos separados por coma (ej. KUL,SIN)")
    search_parser.add_argument("--days-pto", "-p", type=int, default=5, help="Días máximos de vacaciones a gastar")
    search_parser.add_argument("--trip-days", "-td", type=int, help="Duración deseada del viaje en días (ej. 21)")
    search_parser.add_argument("--min-trip-days", type=int, default=5, help="Mínimo de días totales de viaje (ej. 21)")
    search_parser.add_argument("--max-trip-days", type=int, default=25, help="Máximo de días totales de viaje")
    search_parser.add_argument("--year", "-y", type=int, help="Año de viaje (ej. 2027)")
    search_parser.add_argument("--month", "-m", help="Mes preferido (AAAA-MM o 1-12, ej. 2027-03 o 3)")
    search_parser.add_argument("--start-date", help="Fecha de inicio exacta (AAAA-MM-DD)")
    search_parser.add_argument("--end-date", help="Fecha de fin exacta (AAAA-MM-DD)")
    search_parser.add_argument(
        "--event",
        "-e",
        choices=["semana-santa", "easter", "puente-mayo", "verano", "agosto", "navidad", "pilar"],
        help="Evento festivo preconfigurado (ej. semana-santa)",
    )
    search_parser.add_argument(
        "--priority",
        choices=["balanced", "cheapest", "pto"],
        default="balanced",
        help="Prioridad de optimización: 'balanced' (precio + confort + PTO), 'cheapest' (mínimo precio) o 'pto' (máxima eficiencia)",
    )
    search_parser.add_argument(
        "--dual-stopovers",
        action="store_true",
        help="Permitir doble escala turística estratégica (en la ida y en la vuelta)",
    )
    search_parser.add_argument("--top-k-windows", type=int, default=4, help="Número de ventanas de calendario a evaluar")
    search_parser.add_argument("--country", default="ES", help="País para cálculo de festivos (ej. ES)")
    search_parser.add_argument("--subdiv", default="MD", help="Comunidad autónoma o región (ej. MD)")
    search_parser.add_argument(
        "--provider",
        default=config.FLIGHT_PROVIDER or "google",
        choices=["auto", "mock", "amadeus", "kiwi", "rapidapi", "google", "google-flights", "skyscanner4", "duffel", "pool"],
        help=f"API de vuelos o grupo de APIs (por defecto: {config.FLIGHT_PROVIDER or 'google'})",
    )
    search_parser.add_argument("--min-stopover", type=int, default=1, help="Días mínimos por escala")
    search_parser.add_argument("--max-stopover", type=int, default=3, help="Días máximos por escala")
    search_parser.add_argument(
        "--stopovers",
        help="Escalas intermedias deseadas separadas por coma (ej. DOH,DXB,AUH,IST,BKK,ICN,HKG)",
    )
    search_parser.add_argument(
        "--outbound-stopovers",
        help="Escalas intermedias específicas para la ida separadas por coma (ej. DOH,DXB)",
    )
    search_parser.add_argument(
        "--return-stopovers",
        help="Escalas intermedias específicas para la vuelta separadas por coma (ej. BKK,SIN,IST,ICN)",
    )
    search_parser.add_argument(
        "--stopover-preset",
        choices=["asia_top", "asia_full", "gulf", "europe", "all_asia", "istanbul", "brasil", "brazil", "latam_top"],
        help="Preset de escalas estratégicas intermedias recomendadas por IA",
    )
    search_parser.add_argument(
        "--date-flexibility",
        "-df",
        type=int,
        default=0,
        help="Flexibilidad en días (±1 o ±2 días) sobre las ventanas óptimas del calendario",
    )
    search_parser.add_argument(
        "--max-scales",
        type=int,
        default=2,
        help="Máximo de escalas permitidas por trayecto (ida/vuelta, incluyendo la escala principal). Por defecto: 2",
    )
    search_parser.add_argument(
        "--max-stops-per-leg",
        type=int,
        default=1,
        help="Máximo de escalas técnicas permitidas en un único billete/tramo de vuelo. Por defecto: 1",
    )
    search_parser.add_argument(
        "--mix-origins",
        action="store_true",
        help="Permitir mezclar ciudades de origen y regreso (ej. empezar en Madrid y terminar en Bilbao o viceversa)",
    )
    search_parser.add_argument(
        "--return-arrivals",
        "-ra",
        help="Aeropuertos de regreso en país de origen separados por coma (ej. MAD,BIO)",
    )
    search_parser.add_argument(
        "--allowed-scenarios",
        "-as",
        help="Pares de (origen-regreso) permitidos separados por coma (ej. BIO-BIO,MAD-MAD,MAD-BIO)",
    )
    search_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular combinatoria, estimar tareas atómicas y coste de llamadas a API sin conectar a la red",
    )
    search_parser.add_argument(
        "--preset",
        choices=list(config.SEARCH_PRESETS.keys()),
        help="Perfil preconfigurado de búsqueda integral (ej. bilbao_europe_japan, japan_super_ampliada)",
    )
    search_parser.add_argument(
        "--cache-only",
        "--offline",
        action="store_true",
        help="Modo sin conexión: ensamblar y analizar únicamente a partir de la base de datos local (sin peticiones a la API)",
    )
    search_parser.add_argument("--output", "-out", help="Ruta donde guardar el informe Markdown")

    # Command: resume
    resume_parser = subparsers.add_parser("resume", help="Reanudar un trabajo de búsqueda interrumpido")
    resume_parser.add_argument("job_id", help="ID del trabajo a reanudar")

    # Command: list
    subparsers.add_parser("list", help="Listar trabajos de búsqueda recientes")

    # Command: report
    report_parser = subparsers.add_parser("report", help="Mostrar informe de un trabajo completado")
    report_parser.add_argument("job_id", help="ID del trabajo")

    args = parser.parse_args()

    if args.command == "search":
        preset_cfg = config.SEARCH_PRESETS.get(args.preset, {}) if getattr(args, "preset", None) else {}

        origins_input = (
            [x.strip().upper() for x in args.origins.split(",") if x.strip()]
            if getattr(args, "origins", None)
            else ([x.strip().upper() for x in args.origin.split(",") if x.strip()] if getattr(args, "origin", None) else preset_cfg.get("origins"))
        )

        destinations_input = (
            [x.strip().upper() for x in args.destinations.split(",") if x.strip()]
            if getattr(args, "destinations", None)
            else ([x.strip().upper() for x in args.destination.split(",") if x.strip()] if getattr(args, "destination", None) else preset_cfg.get("destinations"))
        )

        if not origins_input or not destinations_input:
            interactive_wizard()
        else:
            ret_dests = (
                [x.strip().upper() for x in args.return_destinations.split(",") if x.strip()]
                if getattr(args, "return_destinations", None)
                else preset_cfg.get("return_destinations")
            )

            stopovers_list = (
                [x.strip().upper() for x in args.stopovers.split(",") if x.strip()]
                if getattr(args, "stopovers", None)
                else preset_cfg.get("stopovers")
            )

            outbound_stopovers_list = (
                [x.strip().upper() for x in args.outbound_stopovers.split(",") if x.strip()]
                if getattr(args, "outbound_stopovers", None)
                else preset_cfg.get("outbound_stopovers")
            )

            return_stopovers_list = (
                [x.strip().upper() for x in args.return_stopovers.split(",") if x.strip()]
                if getattr(args, "return_stopovers", None)
                else preset_cfg.get("return_stopovers")
            )

            min_days = args.min_trip_days if args.min_trip_days != 5 else preset_cfg.get("min_trip_days", 5)
            max_days = args.max_trip_days if args.max_trip_days != 25 else preset_cfg.get("max_trip_days", 25)
            max_pto = args.days_pto if args.days_pto != 5 else preset_cfg.get("days_pto", 5)

            if getattr(args, "trip_days", None):
                min_days = args.trip_days
                max_days = max(args.trip_days + 4, max_days)
                if max_pto == 5:
                    max_pto = max(int(args.trip_days * 0.75), 12)
            elif min_days >= 15 and max_pto == 5:
                max_pto = max(int(min_days * 0.65), 13)

            ret_arrivals = (
                [x.strip().upper() for x in args.return_arrivals.split(",") if x.strip()]
                if getattr(args, "return_arrivals", None)
                else preset_cfg.get("return_arrivals")
            )
            allowed_scenarios_input = (
                [tuple(x.strip().upper().split("-")) for x in args.allowed_scenarios.split(",") if "-" in x]
                if getattr(args, "allowed_scenarios", None)
                else None
            )
            mix_origins_flag = getattr(args, "mix_origins", False) or preset_cfg.get("mix_origins", False)
            event_val = getattr(args, "event", None) or preset_cfg.get("event")
            year_val = getattr(args, "year", None) or preset_cfg.get("year")
            flexibility_val = args.date_flexibility if args.date_flexibility != 0 else preset_cfg.get("date_flexibility", 0)
            subdiv_val = args.subdiv if args.subdiv != "MD" else preset_cfg.get("subdivision", "MD")
            priority_val = getattr(args, "priority", "balanced") if args.priority != "balanced" else preset_cfg.get("priority", "balanced")

            run_search_flow(
                origins=origins_input,
                destinations=destinations_input,
                origin=origins_input[0],
                destination=destinations_input[0],
                max_pto_days=max_pto,
                month_str=args.month,
                year=year_val,
                start_date_str=getattr(args, "start_date", None),
                end_date_str=getattr(args, "end_date", None),
                event=event_val,
                priority=priority_val,
                include_dual_stopovers=getattr(args, "dual_stopovers", False) or preset_cfg.get("include_dual_stopovers", False),
                allowed_scenarios=allowed_scenarios_input,
                top_k_windows=getattr(args, "top_k_windows", 4) or preset_cfg.get("top_k_windows", 4),
                country=args.country,
                subdivision=subdiv_val,
                provider_name=args.provider,
                return_destinations=ret_dests,
                return_arrivals=ret_arrivals,
                mix_origins=mix_origins_flag,
                min_stopover_days=args.min_stopover,
                max_stopover_days=args.max_stopover,
                min_trip_days=min_days,
                max_trip_days=max_days,
                stopovers=stopovers_list,
                stopover_preset=getattr(args, "stopover_preset", None),
                outbound_stopovers=outbound_stopovers_list,
                return_stopovers=return_stopovers_list,
                max_scales=getattr(args, "max_scales", 2),
                max_stops_per_leg=getattr(args, "max_stops_per_leg", 1),
                date_flexibility=flexibility_val,
                dry_run=args.dry_run,
                cache_only=getattr(args, "cache_only", False),
                output_file=args.output,
            )
    elif args.command == "resume":
        resume_flow(args.job_id)
    elif args.command == "list":
        list_jobs_flow()
    elif args.command == "report":
        resume_flow(args.job_id)
    else:
        # Default: interactive wizard if run with no args
        interactive_wizard()


if __name__ == "__main__":
    cli_entrypoint()
