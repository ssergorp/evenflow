"""
Build the starter map: five rooms that remember.

    Hollowmere ── east ── Forest Edge ── north ── Whispering Woods ── north ── Old Grove
                              │                         │
                              └──── east ── Riverbank ──┘ (west)

Runs automatically on the server's first start (server/conf/at_initial_setup.py).
On an existing database, run it in-game as a superuser:

    py from world.build import build_world; build_world()

Safe to run again: rooms are found by their location_id tag, not recreated.
Limbo (#2, where new characters start) becomes Hollowmere.
"""

from evennia import create_object, search_tag
from evennia.objects.models import ObjectDB

ROOM_TYPECLASS = "typeclasses.rooms.AffinityRoom"
EXIT_TYPECLASS = "typeclasses.exits.Exit"
TAG_CATEGORY = "mythworld"

# (from, exit name, aliases, to)
EXITS = [
    ("hollowmere", "east", ["e"], "forest_edge"),
    ("forest_edge", "west", ["w"], "hollowmere"),
    ("forest_edge", "north", ["n"], "whispering_woods"),
    ("whispering_woods", "south", ["s"], "forest_edge"),
    ("whispering_woods", "north", ["n"], "old_grove"),
    ("old_grove", "south", ["s"], "whispering_woods"),
    ("whispering_woods", "east", ["e"], "riverbank"),
    ("riverbank", "west", ["w"], "whispering_woods"),
    ("forest_edge", "east", ["e"], "riverbank"),
    ("riverbank", "south", ["s"], "forest_edge"),
]


def _find_room(location_id):
    found = search_tag(location_id, category=TAG_CATEGORY)
    return found[0] if found else None


def _make_room(location_id, existing=None):
    room = _find_room(location_id)
    if room:
        return room
    if existing is not None:
        existing.swap_typeclass(ROOM_TYPECLASS, clean_attributes=False, run_start_hooks="all")
        room = existing
    else:
        room = create_object(ROOM_TYPECLASS, key=location_id)
    room.setup_from_spec(location_id)
    room.tags.add(location_id, category=TAG_CATEGORY)
    return room


def build_world(caller=None):
    """Create (or complete) the starter map. Returns rooms by location_id."""
    limbo = ObjectDB.objects.get_id(2)
    rooms = {"hollowmere": _make_room("hollowmere", existing=limbo)}
    for location_id in ("forest_edge", "whispering_woods", "old_grove", "riverbank"):
        rooms[location_id] = _make_room(location_id)

    for source, name, aliases, dest in EXITS:
        room = rooms[source]
        if any(ex.key == name for ex in room.exits):
            continue
        create_object(
            EXIT_TYPECLASS, key=name, aliases=aliases,
            location=room, destination=rooms[dest],
        )

    if caller:
        caller.msg("The starter map is ready: " + ", ".join(r.key for r in rooms.values()))
    return rooms
