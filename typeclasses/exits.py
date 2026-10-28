"""
Exits

Exits are connectors between Rooms. An exit always has a destination property
set and has a single command defined on itself with the same name as its key,
for allowing Characters to traverse the exit to its destination.

"""

from evennia.objects.objects import DefaultExit
from evennia.utils import delay

from .objects import ObjectParent


class Exit(ObjectParent, DefaultExit):
    """
    Exits are connectors between rooms. Exits are normal Objects except
    they defines the `destination` property and overrides some hooks
    and methods to represent the exits.

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects child classes like this.

    Leaving a room that remembers asks it how it feels about the traveler:
    hostile places may slow them (pathing) or send them somewhere else
    (misleading navigation).
    """

    def at_traverse(self, traversing_object, target_location, **kwargs):
        from typeclasses.rooms import AffinityRoom
        from world import bridge

        source = traversing_object.location
        if not isinstance(source, AffinityRoom) or not hasattr(traversing_object, "affinity_tags"):
            return super().at_traverse(traversing_object, target_location, **kwargs)

        if traversing_object.ndb.traveling:
            traversing_object.msg("You are already on your way.")
            return

        neighbors = {
            exit.destination.dbref: exit.destination
            for exit in source.exits
            if exit.destination and exit.destination != target_location
        }
        outcome = source.answer(
            traversing_object, "move.depart", bridge.DEPART_AFFORDANCES,
            adjacent_rooms=list(neighbors) or None,
        )
        for tell in outcome.tells:
            traversing_object.msg(tell)
        target_location = neighbors.get(outcome.redirect_target, target_location)

        seconds = bridge.travel_delay(outcome, source.db.travel_seconds or 0)
        if seconds <= 0:
            return super().at_traverse(traversing_object, target_location, **kwargs)

        traversing_object.ndb.traveling = True
        delay(seconds, self._arrive_late, traversing_object, source, target_location)

    def _arrive_late(self, traversing_object, source, target_location):
        traversing_object.ndb.traveling = False
        # Only finish the trip if nothing else moved them in the meantime
        if traversing_object.location == source:
            super().at_traverse(traversing_object, target_location)
