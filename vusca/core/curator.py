"""Deterministic Curator and Pareto Frontier Filter for flight itineraries.

Condenses large sets of combinatorially assembled itineraries (e.g. 10,000 - 50,000+)
into a compact, diverse, non-dominated set of archetype champions (Pareto frontier,
hub champions, destination champions, and scenario champions) with statistical ground truth.
Eliminates LLM context overload and hallucinations while preserving 100% of the best deals.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict
import statistics

from vusca.models.flight import Itinerary


@dataclass
class CuratedArchetypes:
    """Structured collection of champion itineraries across multiple analytical dimensions."""
    total_evaluated: int = 0
    best_overall: Optional[Itinerary] = None
    cheapest_overall: Optional[Itinerary] = None
    best_pto_overall: Optional[Itinerary] = None
    
    # Best itinerary for each scenario (e.g. ("MAD", "MAD"), ("BIO", "BIO"), ("MAD", "BIO"), ("BIO", "MAD"))
    scenario_champions: Dict[Tuple[str, str], Itinerary] = field(default_factory=dict)
    
    # Best itinerary for each strategic stopover hub (e.g. "IST", "ICN", "SIN", "BKK", etc.)
    hub_champions: Dict[str, Itinerary] = field(default_factory=dict)
    
    # Best itinerary for each destination airport / island (e.g. "TYO", "OSA", "FUK", "CTS", "OKA", "NGO")
    destination_champions: Dict[str, Itinerary] = field(default_factory=dict)
    
    # Pareto-optimal frontier (non-dominated itineraries in price vs score vs pto)
    pareto_frontier: List[Itinerary] = field(default_factory=list)
    
    # Top diverse selection ready for LLM consumption (no duplicates, maximum coverage)
    curated_selection: List[Itinerary] = field(default_factory=list)
    
    # High-level market statistics (price distribution, averages, floor prices)
    market_stats: Dict[str, Any] = field(default_factory=dict)


class DeterministicCurator:
    """Deterministic, mathematically rigorous filter and curator for flight itineraries.
    
    Designed to process tens of thousands of itineraries in milliseconds, extracting
    the Pareto frontier and multi-dimensional champions without LLM hallucinations.
    """

    def __init__(self, activation_threshold: int = 150):
        """
        Args:
            activation_threshold: Minimum number of itineraries before curation is triggered.
        """
        self.activation_threshold = activation_threshold

    def is_applicable(self, itineraries_count: int) -> bool:
        """Determines if the dataset is large enough to benefit from deterministic curation."""
        return itineraries_count >= self.activation_threshold

    def curate(
        self,
        itineraries: List[Itinerary],
        target_origins: Optional[List[str]] = None,
        target_destinations: Optional[List[str]] = None,
        max_selection_size: int = 20,
    ) -> CuratedArchetypes:
        """Analyzes and curates a large itinerary dataset down to representative champions.
        
        Args:
            itineraries: The full list of evaluated and ranked itineraries.
            target_origins: Optional list of preferred origins to guarantee representation.
            target_destinations: Optional list of destination airports to guarantee representation.
            max_selection_size: Maximum size of the final curated selection for LLM/prompt.
            
        Returns:
            CuratedArchetypes object with global champions, hub champions, scenario champions,
            Pareto frontier, market statistics, and the curated selection.
        """
        if not itineraries:
            return CuratedArchetypes()

        total_count = len(itineraries)
        
        # 1. Global Champions
        best_overall = max(itineraries, key=lambda it: it.ai_score) if itineraries else None
        cheapest_overall = min(itineraries, key=lambda it: it.total_price_eur)
        best_pto_overall = max(itineraries, key=lambda it: it.pto_efficiency_ratio)
        
        # 2. Market Statistics (Statistical Ground Truth)
        prices = [it.total_price_eur for it in itineraries]
        ptos = [it.pto_efficiency_ratio for it in itineraries]
        durations = [it.total_trip_days for it in itineraries]
        
        stats: Dict[str, Any] = {
            "total_itineraries": total_count,
            "price_min": min(prices),
            "price_max": max(prices),
            "price_median": round(float(statistics.median(prices)), 2),
            "price_mean": round(float(statistics.fmean(prices)), 2),
            "pto_ratio_max": max(ptos),
            "pto_ratio_median": round(float(statistics.median(ptos)), 2),
            "duration_min": min(durations),
            "duration_max": max(durations),
            "hub_counts": defaultdict(int),
            "hub_min_prices": {},
            "destination_min_prices": {},
            "scenario_min_prices": {},
        }

        # 3. Scenario Champions (Origin -> Return Arrival Pair)
        # e.g. (MAD, MAD), (BIO, BIO), (MAD, BIO), (BIO, MAD)
        scenario_groups: Dict[Tuple[str, str], List[Itinerary]] = defaultdict(list)
        hub_groups: Dict[str, List[Itinerary]] = defaultdict(list)
        destination_groups: Dict[str, List[Itinerary]] = defaultdict(list)

        for it in itineraries:
            ret_city = it.legs[-1].destination if it.legs else it.origin
            scenario_key = (it.origin, ret_city)
            scenario_groups[scenario_key].append(it)
            
            # Group by stopover hubs
            if it.stopovers:
                for s in it.stopovers:
                    hub_groups[s.city_code].append(it)
                    stats["hub_counts"][s.city_code] += 1
            else:
                hub_groups["DIRECT"].append(it)
                stats["hub_counts"]["DIRECT"] += 1
                
            # Group by destination (entry destination or islands)
            destination_groups[it.final_destination].append(it)

        # Compute scenario champions (best score and cheapest for each)
        scenario_champions: Dict[Tuple[str, str], Itinerary] = {}
        for scen, group in scenario_groups.items():
            best_scen = max(group, key=lambda it: it.ai_score)
            scenario_champions[scen] = best_scen
            cheapest_scen = min(group, key=lambda it: it.total_price_eur)
            stats["scenario_min_prices"][f"{scen[0]} ➔ {scen[1]}"] = cheapest_scen.total_price_eur

        # Compute hub champions (best score per hub)
        hub_champions: Dict[str, Itinerary] = {}
        for hub, group in hub_groups.items():
            best_hub = max(group, key=lambda it: it.ai_score)
            hub_champions[hub] = best_hub
            stats["hub_min_prices"][hub] = min(it.total_price_eur for it in group)

        # Compute destination champions (best score per Japanese island/airport)
        destination_champions: Dict[str, Itinerary] = {}
        for dest, group in destination_groups.items():
            best_dest = max(group, key=lambda it: it.ai_score)
            destination_champions[dest] = best_dest
            stats["destination_min_prices"][dest] = min(it.total_price_eur for it in group)

        # 4. Pareto Frontier Calculation
        # An itinerary A dominates B if:
        # A.price <= B.price and A.score >= B.score and A.pto >= B.pto (with at least one strictly better)
        pareto_candidates = self._compute_pareto_frontier(itineraries)

        # 5. Build Final Curated Selection (Balanced & Diverse)
        # Guarantee inclusion of key archetypes:
        # - Global champions
        # - Scenario champions (MAD-MAD, BIO-BIO, MAD-BIO, BIO-MAD)
        # - Top diverse hub champions
        # - Destination champions
        # - Top Pareto frontier members
        curated_map: Dict[str, Itinerary] = {}
        
        def add_itinerary(it: Optional[Itinerary]):
            if it and it.itinerary_id not in curated_map:
                curated_map[it.itinerary_id] = it

        # A) Global podium
        add_itinerary(best_overall)
        add_itinerary(cheapest_overall)
        add_itinerary(best_pto_overall)

        # B) All scenario champions (guarantee MAD-BIO, BIO-BIO, etc.)
        for scen_it in scenario_champions.values():
            add_itinerary(scen_it)

        # C) Top Pareto frontier members
        for p_it in pareto_candidates[:6]:
            add_itinerary(p_it)

        # D) Diverse hub champions
        for hub_code, h_it in sorted(hub_champions.items(), key=lambda x: -x[1].ai_score):
            add_itinerary(h_it)
            if len(curated_map) >= max_selection_size + 5:
                break

        # E) Diverse destination champions (guarantee Fukuoka, Okinawa, Sapporo, etc.)
        for dest_code, d_it in sorted(destination_champions.items(), key=lambda x: -x[1].ai_score):
            add_itinerary(d_it)

        # Convert to list sorted by AI score descending
        curated_list = sorted(curated_map.values(), key=lambda it: it.ai_score, reverse=True)
        
        # If over max_selection_size, keep top scoring while retaining scenario diversity
        if len(curated_list) > max_selection_size:
            final_selection = self._prune_preserving_diversity(curated_list, max_selection_size)
        else:
            final_selection = curated_list

        return CuratedArchetypes(
            total_evaluated=total_count,
            best_overall=best_overall,
            cheapest_overall=cheapest_overall,
            best_pto_overall=best_pto_overall,
            scenario_champions=scenario_champions,
            hub_champions=hub_champions,
            destination_champions=destination_champions,
            pareto_frontier=pareto_candidates,
            curated_selection=final_selection,
            market_stats=stats,
        )

    @staticmethod
    def _compute_pareto_frontier(itineraries: List[Itinerary]) -> List[Itinerary]:
        """Calculates the non-dominated Pareto frontier based on:
        - Objective 1: Minimize Total Price (EUR)
        - Objective 2: Maximize AI Score
        - Objective 3: Maximize PTO Efficiency Ratio
        """
        if not itineraries:
            return []

        # Unpack to tuples (price, score, pto, it) to avoid attribute overhead in hot loop.
        # Pre-sort by price ascending, score descending, pto descending.
        raw_items = [
            (it.total_price_eur, it.ai_score, it.pto_efficiency_ratio, it)
            for it in itineraries
        ]
        raw_items.sort(key=lambda x: (x[0], -x[1], -x[2]))

        pareto_tuples: List[Tuple[float, float, float, Itinerary]] = []

        for c_price, c_score, c_pto, c_it in raw_items:
            is_dominated = False
            # Because raw_items is sorted by price ascending:
            # any prior member in pareto_tuples has m_price <= c_price.
            # Thus, member dominates candidate if m_score >= c_score and m_pto >= c_pto.
            for m_price, m_score, m_pto, _ in pareto_tuples:
                if m_score >= c_score and m_pto >= c_pto:
                    is_dominated = True
                    break
            if not is_dominated:
                pareto_tuples.append((c_price, c_score, c_pto, c_it))

        # Extract itineraries and sort by AI score descending
        pareto_frontier = [t[3] for t in pareto_tuples]
        pareto_frontier.sort(key=lambda it: it.ai_score, reverse=True)
        return pareto_frontier

    @staticmethod
    def _prune_preserving_diversity(candidates: List[Itinerary], limit: int) -> List[Itinerary]:
        """Prunes a list of candidates to target size while preserving origin and destination diversity."""
        selected: List[Itinerary] = []
        seen_signatures = set()

        # Pass 1: Unique (origin, final_return, final_destination, primary_stopover)
        for it in candidates:
            final_ret = it.legs[-1].destination if it.legs else it.origin
            stop_code = it.stopovers[0].city_code if it.stopovers else "DIRECT"
            sig = (it.origin, final_ret, it.final_destination, stop_code)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                selected.append(it)
            if len(selected) == limit:
                break

        # Pass 2: Fill remaining slots if any
        if len(selected) < limit:
            for it in candidates:
                if it not in selected:
                    selected.append(it)
                if len(selected) == limit:
                    break

        selected.sort(key=lambda it: it.ai_score, reverse=True)
        return selected
