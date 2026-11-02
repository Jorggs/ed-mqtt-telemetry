"""
Reconstructs the "Telemetry/State" JSON blob from the journal event stream --
matching the schema actually consumed by the user's Home Assistant package:

    {
        "Credits": int,
        "SystemName": str,
        "IsDocked": bool,
        "StationName": str | None,
        "Body": str | None,
        "ShipType": str,        # internal ship code, e.g. "anaconda"
        "ShipTypeDisplay": str, # game-provided human-readable name (from the
                                # journal's own "..._Localised" companion field
                                # on LoadGame/Loadout/ShipyardSwap) -- this is
                                # authoritative and needs no hardcoded lookup
                                # table, so it stays correct as Frontier adds
                                # new ships.
        "ShipName": str,
        "SystemPopulation": int,
        "StarPos": [x, y, z],
        "Rank": {
            "Combat": [level, pct], "Trade": [level, pct], "Explore": [level, pct],
            "Federation": [level, pct], "Empire": [level, pct], "CQC": [level, pct],
            "Exobiologist": [level, pct], "Soldier": [level, pct]
        },
        "Statistics": { ... raw contents of the journal "Statistics" event ... }
    }

Rank levels come from the journal "Rank" event, progress percentages from the
separate "Progress" event -- both fire together at load and are merged here
into the combined [level, pct] pairs the HA templates expect.
"""

RANK_CATEGORIES = (
    "Combat", "Trade", "Explore", "Federation", "Empire",
    "CQC", "Exobiologist", "Soldier",
)


def _localised_ship_name(event):
    """Elite Dangerous writes a "<Key>_Localised" companion whenever a raw
    value is one of its internal "$symbol;" tokens. Ship-type fields have
    used both "Ship" and "ShipType" as the base key name across different
    events/journal versions, so check both companions."""
    for key in ("ShipType_Localised", "Ship_Localised"):
        if event.get(key):
            return event[key]
    return None


class StateTracker:
    def __init__(self):
        # kept for anything that wants simple current system/station (e.g.
        # optional Location/System, Location/Station topics)
        self.system = None
        self.station = None
        self.docked = False

        self._rank_levels = {}
        self._rank_progress = {}

        self.state = {
            "Credits": None,
            "SystemName": None,
            "IsDocked": False,
            "StationName": None,
            "Body": None,
            "ShipType": None,
            "ShipTypeDisplay": None,
            "ShipName": None,
            "SystemPopulation": None,
            "StarPos": None,
            "MaxJumpRange": None,
            "Rank": {},
            "Statistics": {},
        }

    def _rebuild_rank(self):
        rank = {}
        cats = set(self._rank_levels) | set(self._rank_progress)
        for cat in cats:
            rank[cat] = [
                self._rank_levels.get(cat, 0),
                self._rank_progress.get(cat, 0),
            ]
        self.state["Rank"] = rank

    def ingest(self, event):
        """Update internal state from one journal event dict. Returns a tuple
        (location_changed, state_changed, ship_changed)."""
        name = event.get("event")
        location_changed = False
        state_changed = False
        ship_changed = False

        prev_ship = (
            self.state["ShipName"],
            self.state["ShipType"],
            self.state["ShipTypeDisplay"],
            self.state["MaxJumpRange"],
        )

        if "Credits" in event:
            self.state["Credits"] = event.get("Credits")
            state_changed = True

        if name == "LoadGame":
            self.state["ShipType"] = event.get("Ship")
            # An unnamed ship has an empty/absent ShipName -- store "" so a
            # previous ship's name can never linger.
            self.state["ShipName"] = event.get("ShipName") or ""
            localised = _localised_ship_name(event)
            if localised:
                self.state["ShipTypeDisplay"] = localised
            state_changed = True

        elif name == "Loadout":
            # Loadout fires on every ship/module change and carries the
            # current ShipName/ShipIdent/ShipType too. We only pull out the
            # fields we actually use -- the full event is large and noisy,
            # so it's excluded from MQTT publishing by default (see
            # config.DEFAULT_SETTINGS["excluded_journal_events"]).
            if event.get("Ship"):
                self.state["ShipType"] = event.get("Ship")
                # Every ship Loadout describes the *current* ship, so its
                # ShipName is authoritative even when empty (unnamed ship).
                # Previously an empty name was ignored, leaving the last
                # ship's name in place.
                self.state["ShipName"] = event.get("ShipName") or ""
            localised = _localised_ship_name(event)
            if localised:
                self.state["ShipTypeDisplay"] = localised
            if "MaxJumpRange" in event:
                self.state["MaxJumpRange"] = event.get("MaxJumpRange")
            state_changed = True

        elif name == "ShipyardSwap":
            self.state["ShipType"] = event.get("ShipType", self.state["ShipType"])
            # ShipyardSwap doesn't carry the new ship's name; clear the old
            # one now so it can't linger -- the Loadout that follows the swap
            # supplies the real name if there is one.
            self.state["ShipName"] = ""
            localised = _localised_ship_name(event)
            if localised:
                self.state["ShipTypeDisplay"] = localised
            state_changed = True

        elif name == "Rank":
            for cat in RANK_CATEGORIES:
                if cat in event:
                    self._rank_levels[cat] = event.get(cat)
            self._rebuild_rank()
            state_changed = True

        elif name == "Progress":
            for cat in RANK_CATEGORIES:
                if cat in event:
                    self._rank_progress[cat] = event.get(cat)
            self._rebuild_rank()
            state_changed = True

        elif name == "Statistics":
            self.state["Statistics"] = {
                k: v for k, v in event.items() if k not in ("timestamp", "event")
            }
            state_changed = True

        elif name in ("Location", "FSDJump", "CarrierJump"):
            prev_body = self.state["Body"]
            prev_starpos = self.state["StarPos"]
            prev_population = self.state["SystemPopulation"]

            new_system = event.get("StarSystem")
            if new_system and new_system != self.system:
                self.system = new_system
                location_changed = True
            self.state["SystemName"] = new_system
            self.state["StarPos"] = event.get("StarPos", self.state["StarPos"])
            self.state["Body"] = event.get("Body", self.state["Body"])
            if "Population" in event:
                self.state["SystemPopulation"] = event.get("Population")

            if self.state["Body"] != prev_body or self.state["StarPos"] != prev_starpos \
                    or self.state["SystemPopulation"] != prev_population:
                location_changed = True

            docked = bool(event.get("Docked", False))
            if docked != self.docked:
                self.docked = docked
                location_changed = True
            self.state["IsDocked"] = docked
            if not docked:
                if self.station is not None:
                    self.station = None
                    location_changed = True
                self.state["StationName"] = None
            if docked:
                station = event.get("StationName")
                if station and station != self.station:
                    self.station = station
                    location_changed = True
                self.state["StationName"] = station
            state_changed = True

        elif name == "Docked":
            self.docked = True
            self.state["IsDocked"] = True
            station = event.get("StationName")
            if station != self.station:
                self.station = station
                location_changed = True
            self.state["StationName"] = station
            if "StarSystem" in event:
                self.state["SystemName"] = event.get("StarSystem")
            state_changed = True

        elif name == "Undocked":
            self.docked = False
            self.state["IsDocked"] = False
            if self.station is not None:
                self.station = None
                location_changed = True
            self.state["StationName"] = None
            state_changed = True

        new_ship = (
            self.state["ShipName"],
            self.state["ShipType"],
            self.state["ShipTypeDisplay"],
            self.state["MaxJumpRange"],
        )
        if new_ship != prev_ship:
            ship_changed = True

        return location_changed, state_changed, ship_changed
