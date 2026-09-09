"""Combinator engine for generating multi-city itineraries and pruning search spaces."""

import uuid
from collections import defaultdict
from datetime import timedelta, date
from typing import List, Dict, Set, Tuple, Optional, Union, Any
from vusca.models.calendar import PTOWindow
from vusca.models.flight import Itinerary, FlightLegOffer, StopoverDetail
from vusca.models.search import SearchLegTask


class RouteBlueprint:
    """Blueprint of an itinerary to assemble once leg offers are fetched."""
    def __init__(
        self,
        blueprint_id: str,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        pto_window: PTOWindow,
        leg_keys: List[Tuple[str, str, date]],
        stopovers: List[StopoverDetail],
        description: str,
        outbound_keys: Optional[List[Tuple[str, str, date]]] = None,
        return_keys: Optional[List[Tuple[str, str, date]]] = None,
        has_outbound_stopover: bool = False,
        has_return_stopover: bool = False,
    ):
        self.blueprint_id = blueprint_id
        self.origin = origin
        self.destination = destination
        self.start_date = start_date
        self.end_date = end_date
        self.pto_window = pto_window
        self.leg_keys = leg_keys  # [(orig, dest, date), ...]
        self.stopovers = stopovers
        self.description = description
        self.outbound_keys = outbound_keys if outbound_keys is not None else (leg_keys[:2] if has_outbound_stopover else leg_keys[:1])
        self.return_keys = return_keys if return_keys is not None else leg_keys[len(self.outbound_keys):]
        self.has_outbound_stopover = has_outbound_stopover
        self.has_return_stopover = has_return_stopover


class RouteCombinator:
    """Generates unique leg tasks and valid multi-city itinerary permutations across multiple origins & destinations."""

    def __init__(
        self,
        origin: Optional[Union[str, List[str]]] = None,
        destination: Optional[Union[str, List[str]]] = None,
        candidate_windows: Optional[List[PTOWindow]] = None,
        candidate_stopovers: Optional[List[str]] = None,
        stopover_names: Optional[Dict[str, str]] = None,
        return_destinations: Optional[List[str]] = None,
        return_arrivals: Optional[List[str]] = None,
        min_stopover_days: int = 1,
        max_stopover_days: int = 3,
        inbound_stopover_limit: Optional[int] = None,
        origins: Optional[Union[str, List[str]]] = None,
        destinations: Optional[Union[str, List[str]]] = None,
        outbound_stopovers: Optional[List[str]] = None,
        return_stopovers: Optional[List[str]] = None,
        include_dual_stopovers: bool = True,
    ):
        # Resolve origins (accepting both origins and origin)
        raw_origins = origins if origins is not None else origin
        if isinstance(raw_origins, list):
            self.origins = [o.strip().upper() for o in raw_origins if o.strip()]
        elif isinstance(raw_origins, str):
            self.origins = [o.strip().upper() for o in raw_origins.split(",") if o.strip()]
        else:
            self.origins = ["MAD"]

        # Resolve destinations (accepting both destinations and destination)
        raw_destinations = destinations if destinations is not None else destination
        if isinstance(raw_destinations, list):
            self.destinations = [d.strip().upper() for d in raw_destinations if d.strip()]
        elif isinstance(raw_destinations, str):
            self.destinations = [d.strip().upper() for d in raw_destinations.split(",") if d.strip()]
        else:
            self.destinations = ["TYO"]

        # Backward-compatible single origin/destination properties
        self.origin = self.origins[0] if self.origins else "MAD"
        self.destination = self.destinations[0] if self.destinations else "TYO"

        # Return departure cities from vacation region (e.g. TYO, OSA, KIX)
        if return_destinations:
            self.return_destinations = [r.strip().upper() for r in return_destinations if r.strip()]
        else:
            self.return_destinations = list(self.destinations)

        # Return arrival cities in home country (e.g. MAD, BCN)
        if return_arrivals:
            self.return_arrivals = [r.strip().upper() for r in return_arrivals if r.strip()]
        else:
            self.return_arrivals = None  # defaults to returning to origin departed from

        self.candidate_windows = candidate_windows or []
        self.candidate_stopovers = [s.strip().upper() for s in (candidate_stopovers or []) if s.strip()]
        self.stopover_names = stopover_names or {}
        self.min_stopover_days = min_stopover_days
        self.max_stopover_days = max_stopover_days
        self.inbound_stopover_limit = inbound_stopover_limit

        # Configurable outbound and return stopovers
        if outbound_stopovers is not None:
            self.outbound_stopovers = [s.strip().upper() for s in outbound_stopovers if s.strip()]
        else:
            self.outbound_stopovers = list(self.candidate_stopovers)

        if return_stopovers is not None:
            self.return_stopovers = [s.strip().upper() for s in return_stopovers if s.strip()]
        else:
            self.return_stopovers = list(self.candidate_stopovers)

        self.include_dual_stopovers = include_dual_stopovers

    def generate_blueprints(self) -> Tuple[List[RouteBlueprint], List[SearchLegTask]]:
        """
        Builds route permutations across all origin, destination, return, and stopover pairs
        and extracts deduplicated atomic SearchLegTasks.
        """
        blueprints: List[RouteBlueprint] = []
        unique_tasks_dict: Dict[str, SearchLegTask] = {}

        def add_task(orig: str, dest: str, d: date) -> str:
            key = f"{orig.upper()}:{dest.upper()}:{d.isoformat()}"
            if key not in unique_tasks_dict:
                unique_tasks_dict[key] = SearchLegTask(
                    task_id=str(uuid.uuid4())[:8],
                    origin=orig.upper(),
                    destination=dest.upper(),
                    travel_date=d,
                )
            return key

        for window in self.candidate_windows:
            total_days = window.total_days
            start = window.start_date
            end = window.end_date

            for orig in self.origins:
                for dest in self.destinations:
                    for ret_orig in self.return_destinations:
                        ret_dest_candidates = self.return_arrivals if self.return_arrivals else [orig]
                        for ret_dest in ret_dest_candidates:
                            is_open_jaw = (ret_orig != dest) or (ret_dest != orig)

                            # 1. Baseline Route (orig -> dest | Return: ret_orig -> ret_dest)
                            add_task(orig, dest, start)
                            add_task(ret_orig, ret_dest, end)

                            desc_baseline = (
                                f"Multiciudad ({orig} ➔ {dest} | Regreso: {ret_orig} ➔ {ret_dest})"
                                if is_open_jaw
                                else f"Directo / Ruta Base ({orig} ➔ {dest} ➔ {ret_dest})"
                            )

                            b_id = f"direct_{orig}_{dest}_{ret_orig}_{ret_dest}_{window.key}"
                            blueprints.append(
                                RouteBlueprint(
                                    blueprint_id=b_id,
                                    origin=orig,
                                    destination=dest,
                                    start_date=start,
                                    end_date=end,
                                    pto_window=window,
                                    leg_keys=[
                                        (orig, dest, start),
                                        (ret_orig, ret_dest, end),
                                    ],
                                    stopovers=[],
                                    description=desc_baseline,
                                    has_outbound_stopover=False,
                                    has_return_stopover=False,
                                )
                            )

                            # 2. Outbound Stopover Routes (orig -> stopover -> dest | Return: ret_orig -> ret_dest)
                            for stopover in self.outbound_stopovers:
                                if stopover in (orig, dest, ret_orig, ret_dest):
                                    continue
                                s_name = self.stopover_names.get(stopover, stopover)

                                for stay_days in range(self.min_stopover_days, self.max_stopover_days + 1):
                                    remaining_days = total_days - stay_days
                                    if remaining_days < 3:
                                        continue

                                    leg1_date = start
                                    leg2_date = start + timedelta(days=stay_days)
                                    leg3_date = end

                                    add_task(orig, stopover, leg1_date)
                                    add_task(stopover, dest, leg2_date)
                                    add_task(ret_orig, ret_dest, leg3_date)

                                    stopover_detail = StopoverDetail(
                                        city_code=stopover,
                                        city_name=s_name,
                                        stay_days=stay_days,
                                        arrival_date=leg1_date,
                                        departure_date=leg2_date,
                                        highlights=f"Escala de ida de {stay_days} días en {s_name}",
                                    )

                                    desc_stopover = (
                                        f"{orig} ➔ {s_name} ({stay_days}d) ➔ {dest} | Regreso: {ret_orig} ➔ {ret_dest}"
                                        if is_open_jaw
                                        else f"{orig} ➔ {s_name} ({stay_days}d) ➔ {dest} ➔ {ret_dest}"
                                    )

                                    blueprints.append(
                                        RouteBlueprint(
                                            blueprint_id=f"outbound_{orig}_{stopover}_{stay_days}d_{dest}_ret_{ret_orig}_{ret_dest}_{window.key}",
                                            origin=orig,
                                            destination=dest,
                                            start_date=start,
                                            end_date=end,
                                            pto_window=window,
                                            leg_keys=[
                                                (orig, stopover, leg1_date),
                                                (stopover, dest, leg2_date),
                                                (ret_orig, ret_dest, leg3_date),
                                            ],
                                            stopovers=[stopover_detail],
                                            description=desc_stopover,
                                            has_outbound_stopover=True,
                                            has_return_stopover=False,
                                        )
                                    )

                            # 3. Inbound / Return Stopover Routes (orig -> dest | Return: ret_orig -> stopover -> ret_dest)
                            inbound_candidates = (
                                self.return_stopovers[: self.inbound_stopover_limit]
                                if self.inbound_stopover_limit is not None
                                else self.return_stopovers
                            )
                            for stopover in inbound_candidates:
                                if stopover in (orig, dest, ret_orig, ret_dest):
                                    continue
                                s_name = self.stopover_names.get(stopover, stopover)
                                for stay_days in range(self.min_stopover_days, self.max_stopover_days + 1):
                                    remaining_days = total_days - stay_days
                                    if remaining_days < 3:
                                        continue

                                    leg1_date = start
                                    leg2_date = end - timedelta(days=stay_days)
                                    leg3_date = end

                                    add_task(orig, dest, leg1_date)
                                    add_task(ret_orig, stopover, leg2_date)
                                    add_task(stopover, ret_dest, leg3_date)

                                    stopover_detail = StopoverDetail(
                                        city_code=stopover,
                                        city_name=s_name,
                                        stay_days=stay_days,
                                        arrival_date=leg2_date,
                                        departure_date=leg3_date,
                                        highlights=f"Escala de regreso de {stay_days} días en {s_name}",
                                    )

                                    desc_inbound = (
                                        f"{orig} ➔ {dest} | Regreso: {ret_orig} ➔ {s_name} ({stay_days}d) ➔ {ret_dest}"
                                        if is_open_jaw
                                        else f"{orig} ➔ {dest} ➔ {s_name} ({stay_days}d) ➔ {ret_dest}"
                                    )

                                    blueprints.append(
                                        RouteBlueprint(
                                            blueprint_id=f"inbound_{orig}_{dest}_ret_{ret_orig}_{stopover}_{stay_days}d_{ret_dest}_{window.key}",
                                            origin=orig,
                                            destination=dest,
                                            start_date=start,
                                            end_date=end,
                                            pto_window=window,
                                            leg_keys=[
                                                (orig, dest, leg1_date),
                                                (ret_orig, stopover, leg2_date),
                                                (stopover, ret_dest, leg3_date),
                                            ],
                                            stopovers=[stopover_detail],
                                            description=desc_inbound,
                                            has_outbound_stopover=False,
                                            has_return_stopover=True,
                                        )
                                    )

                            # 4. Dual Stopover Routes (Outbound Stopover AND Return Stopover)
                            if self.include_dual_stopovers:
                                for stop_out in self.outbound_stopovers:
                                    if stop_out in (orig, dest, ret_orig, ret_dest):
                                        continue
                                    s_out_name = self.stopover_names.get(stop_out, stop_out)

                                    for stop_ret in inbound_candidates:
                                        if stop_ret in (orig, dest, ret_orig, ret_dest) or stop_ret == stop_out:
                                            continue
                                        s_ret_name = self.stopover_names.get(stop_ret, stop_ret)

                                        # Evaluate balanced stopover durations (e.g. 2d out and 2d ret)
                                        for stay_out in range(self.min_stopover_days, self.max_stopover_days + 1):
                                            for stay_ret in (2,) if stay_out > 2 else range(self.min_stopover_days, self.max_stopover_days + 1):
                                                if total_days - stay_out - stay_ret < 5:
                                                    continue

                                                leg1_date = start
                                                leg2_date = start + timedelta(days=stay_out)
                                                leg3_date = end - timedelta(days=stay_ret)
                                                leg4_date = end

                                                add_task(orig, stop_out, leg1_date)
                                                add_task(stop_out, dest, leg2_date)
                                                add_task(ret_orig, stop_ret, leg3_date)
                                                add_task(stop_ret, ret_dest, leg4_date)

                                                s_out_detail = StopoverDetail(
                                                    city_code=stop_out,
                                                    city_name=s_out_name,
                                                    stay_days=stay_out,
                                                    arrival_date=leg1_date,
                                                    departure_date=leg2_date,
                                                    highlights=f"Escala de ida de {stay_out} días en {s_out_name}",
                                                )
                                                s_ret_detail = StopoverDetail(
                                                    city_code=stop_ret,
                                                    city_name=s_ret_name,
                                                    stay_days=stay_ret,
                                                    arrival_date=leg3_date,
                                                    departure_date=leg4_date,
                                                    highlights=f"Escala de regreso de {stay_ret} días en {s_ret_name}",
                                                )

                                                desc_dual = (
                                                    f"{orig} ➔ {s_out_name} ({stay_out}d) ➔ {dest} | Regreso: {ret_orig} ➔ {s_ret_name} ({stay_ret}d) ➔ {ret_dest}"
                                                )

                                                blueprints.append(
                                                    RouteBlueprint(
                                                        blueprint_id=f"dual_{orig}_{stop_out}_{stay_out}d_{dest}_{ret_orig}_{stop_ret}_{stay_ret}d_{ret_dest}_{window.key}",
                                                        origin=orig,
                                                        destination=dest,
                                                        start_date=start,
                                                        end_date=end,
                                                        pto_window=window,
                                                        leg_keys=[
                                                            (orig, stop_out, leg1_date),
                                                            (stop_out, dest, leg2_date),
                                                            (ret_orig, stop_ret, leg3_date),
                                                            (stop_ret, ret_dest, leg4_date),
                                                        ],
                                                        stopovers=[s_out_detail, s_ret_detail],
                                                        description=desc_dual,
                                                        has_outbound_stopover=True,
                                                        has_return_stopover=True,
                                                    )
                                                )

        leg_tasks = list(unique_tasks_dict.values())
        return blueprints, leg_tasks

    def estimate_task_volume(self, db: Optional[Any] = None) -> Dict[str, Any]:
        """
        Calculates search matrix statistics, API call budget, and cache hit estimate.
        """
        blueprints, leg_tasks = self.generate_blueprints()
        corridors: Dict[str, int] = defaultdict(int)
        cached_count = 0

        for task in leg_tasks:
            corridor_key = f"{task.origin} ➔ {task.destination}"
            corridors[corridor_key] += 1
            if db is not None:
                cached = db.get_cached_offers(task.origin, task.destination, task.travel_date)
                if cached:
                    cached_count += 1

        return {
            "total_blueprints": len(blueprints),
            "total_leg_tasks": len(leg_tasks),
            "cached_leg_tasks": cached_count,
            "api_calls_needed": len(leg_tasks) - cached_count,
            "origins": self.origins,
            "destinations": self.destinations,
            "return_destinations": self.return_destinations,
            "stopovers": self.candidate_stopovers,
            "outbound_stopovers": self.outbound_stopovers,
            "return_stopovers": self.return_stopovers,
            "windows_count": len(self.candidate_windows),
            "corridors": dict(corridors),
        }

    @staticmethod
    def assemble_itineraries(
        blueprints: List[RouteBlueprint],
        offers_by_key: Dict[str, List[FlightLegOffer]],
        max_scales_per_direction: int = 2,
        max_stops_per_leg: int = 1,
    ) -> List[Itinerary]:
        """
        Combines fetched flight leg offers into completed full itineraries.
        Filters combinations so that:
          1. Every individual flight leg has at most max_stops_per_leg (default 1).
          2. Total scales per direction do not exceed max_scales_per_direction (default 2),
             where a main strategic stopover counts as 1 scale.
        Selects the best/cheapest valid combination for each blueprint.
        """
        itineraries: List[Itinerary] = []

        def find_cheapest_valid_direction(
            keys: List[Tuple[str, str, date]],
            has_stopover: bool,
        ) -> Optional[List[FlightLegOffer]]:
            candidates_list = []
            for orig, dest, d in keys:
                key = f"{orig.upper()}:{dest.upper()}:{d.isoformat()}"
                offs = offers_by_key.get(key, [])
                if not offs:
                    return None
                # Filter out offers where stops_count > max_stops_per_leg (default 1)
                # Any flight leg between origin, central stopover and destination must have at most 1 connection!
                valid_offs = [o for o in offs if o.stops_count <= max_stops_per_leg]
                if not valid_offs:
                    return None
                # Sort candidate offers: prefer lower price, then fewer stops, then shorter duration
                candidates_list.append(
                    sorted(valid_offs, key=lambda o: (o.price_eur, o.stops_count, o.total_duration_minutes or 9999))
                )

            best_combo = None
            best_price = float("inf")
            main_stopover_count = 1 if has_stopover else 0

            import itertools
            for combo in itertools.product(*candidates_list):
                if any(leg.stops_count > max_stops_per_leg for leg in combo):
                    continue
                transfer_stops = sum(leg.stops_count for leg in combo)
                total_scales = main_stopover_count + transfer_stops
                if total_scales <= max_scales_per_direction:
                    combo_price = sum(leg.price_eur for leg in combo)
                    if combo_price < best_price:
                        best_price = combo_price
                        best_combo = list(combo)
                        # Break early if 0 transfer stops found (optimal for both comfort and price)
                        if transfer_stops == 0:
                            break

            return best_combo

        for bp in blueprints:
            out_keys = getattr(bp, "outbound_keys", None) or (bp.leg_keys[:2] if getattr(bp, "has_outbound_stopover", False) else bp.leg_keys[:1])
            ret_keys = getattr(bp, "return_keys", None) or bp.leg_keys[len(out_keys):]
            has_out_stop = getattr(bp, "has_outbound_stopover", False)
            has_ret_stop = getattr(bp, "has_return_stopover", False)

            best_outbound = find_cheapest_valid_direction(out_keys, has_out_stop)
            if not best_outbound:
                continue

            best_return = find_cheapest_valid_direction(ret_keys, has_ret_stop)
            if not best_return:
                continue

            legs_for_bp = best_outbound + best_return

            itinerary = Itinerary(
                itinerary_id=str(uuid.uuid4())[:8],
                origin=bp.origin,
                final_destination=bp.destination,
                start_date=bp.start_date,
                end_date=bp.end_date,
                legs=legs_for_bp,
                stopovers=bp.stopovers,
                route_summary=bp.description,
            )
            itinerary.calculate_totals(work_days=bp.pto_window.work_days_needed)
            itineraries.append(itinerary)

        # Sort by total price ascending
        itineraries.sort(key=lambda it: it.total_price_eur)
        return itineraries
