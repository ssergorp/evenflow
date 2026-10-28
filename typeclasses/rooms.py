"""
Room

Rooms are simple containers that has no location of their own.

"""

from evennia.objects.objects import DefaultRoom

from .objects import ObjectParent


class Room(ObjectParent, DefaultRoom):
    """
    Rooms are like any Object, except their location is None
    (which is default). They also use basetype_setup() to
    add locks so they cannot be puppeted or picked up.
    (to change that, use at_object_creation instead)

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects.
    """

    pass


class AffinityRoom(Room):
    """
    A room that remembers what happens in it.

    Memory (traces and cooldowns) lives in `db.affinity_state` as plain data,
    so it survives restarts. Values come fresh from
    world/locations/<db.location_id>.yaml each time memory is loaded, so
    editing a location file retunes the place without wiping its memory.
    """

    def at_object_creation(self):
        super().at_object_creation()
        self.db.location_id = None
        self.db.travel_seconds = 0
        self.db.affinity_state = None

    def setup_from_spec(self, location_id):
        """Point this room at a location file and give it an empty memory."""
        from world import bridge

        spec = bridge.load_location_spec(location_id)
        self.key = spec["name"]
        self.db.desc = spec.get("description", "").strip()
        self.db.location_id = location_id
        self.db.travel_seconds = spec.get("travel_seconds", 0)
        self.save_memory(bridge.new_location(spec))

    def memory(self):
        """The engine Location for this room, loaded once and cached."""
        if self.ndb.memory is None:
            from evennia.utils.dbserialize import deserialize
            from world import bridge

            spec = bridge.load_location_spec(self.db.location_id)
            state = self.attributes.get("affinity_state")
            if state is None:
                location = bridge.new_location(spec)
            else:
                location = bridge.location_from_state(deserialize(state))
                location.valuation_profile = dict(spec.get("valuation_profile", {}))
            self.ndb.memory = location
        return self.ndb.memory

    def save_memory(self, location=None):
        from world import bridge

        location = location or self.memory()
        self.db.affinity_state = bridge.location_to_state(location)
        self.ndb.memory = location

    def record(self, actor, verb):
        """Remember an actor's action, and return how the place answers."""
        from world import bridge

        outcome = bridge.perform(self.memory(), actor.affinity_id, actor.affinity_tags(), verb)
        return self._finish(actor, verb, outcome)

    def answer(self, actor, action_type, affordances, adjacent_rooms=None):
        """Ask the place how it responds to an actor, without recording anything."""
        from world import bridge

        outcome = bridge.respond(
            self.memory(), actor.affinity_id, actor.affinity_tags(), action_type,
            affordances, adjacent_rooms=adjacent_rooms,
        )
        return self._finish(actor, action_type, outcome)

    # How many evaluations @trace can show per character
    TRACE_HISTORY = 10

    def _finish(self, actor, action_type, outcome):
        # Cooldowns changed even if nothing triggered; keep recent outcomes
        # around for the admin @trace command
        self.save_memory()
        history = (actor.ndb.affordance_history or [])[-(self.TRACE_HISTORY - 1):]
        actor.ndb.affordance_history = history + [(action_type, outcome)]
        return outcome
