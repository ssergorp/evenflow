"""
Affinity commands.

Player verbs leave memory traces in the room (burn, plant, offer, hunt,
forage) or ask the room how it feels (rest). Places answer only through
narrative tells; no numbers ever reach players (docs/DO_NOT.md #2).

Admin commands (Builder+) explain the hidden state:
    @affinity   - how this place feels about someone, and why
    @trace      - why the last affordance did or did not trigger
    @toggleaff  - turn an affordance on or off
"""

from evennia import default_cmds

from commands.command import Command
from world import bridge


def _affinity_room(caller):
    from typeclasses.rooms import AffinityRoom

    room = caller.location
    return room if isinstance(room, AffinityRoom) else None


class _CmdAction(Command):
    """Base for verbs that the room remembers."""

    locks = "cmd:all()"
    help_category = "Actions"

    def func(self):
        caller = self.caller
        room = _affinity_room(caller)
        if room is None:
            caller.msg("There is nothing here for that.")
            return

        action = bridge.ACTIONS[self.key]
        caller.msg(action.self_msg)
        room.msg_contents(action.room_msg.format(actor=caller.key), exclude=caller)
        outcome = room.record(caller, self.key)
        for tell in outcome.tells:
            caller.msg(tell)


class CmdBurn(_CmdAction):
    """
    Set a fire.

    Usage:
      burn
    """

    key = "burn"


class CmdPlant(_CmdAction):
    """
    Plant something.

    Usage:
      plant
    """

    key = "plant"


class CmdOffer(_CmdAction):
    """
    Leave an offering to the place.

    Usage:
      offer
    """

    key = "offer"


class CmdHunt(_CmdAction):
    """
    Hunt for game.

    Usage:
      hunt
    """

    key = "hunt"


class CmdForage(_CmdAction):
    """
    Search the ground for anything useful.

    Usage:
      forage
    """

    key = "forage"
    aliases = ["gather", "harvest"]


class CmdRest(Command):
    """
    Rest a while.

    Usage:
      rest
    """

    key = "rest"
    aliases = ["sleep"]
    locks = "cmd:all()"
    help_category = "Actions"

    def func(self):
        caller = self.caller
        caller.msg("You settle down and rest a while.")
        room = _affinity_room(caller)
        if room is None:
            return
        outcome = room.answer(caller, "rest", bridge.REST_AFFORDANCES)
        for tell in outcome.tells:
            caller.msg(tell)


class CmdAffinity(default_cmds.MuxCommand):
    """
    Inspect a place's hidden memory (admin only).

    Usage:
      @affinity [<character>]
      @affinity/age <days>
      @affinity/forget

    Shows how this room feels about a character (default: you) and the
    memories behind it.

    Switches:
      age     - make this room's memories <days> older, to watch it forgive
      forget  - wipe this room's memory
    """

    key = "@affinity"
    switch_options = ("age", "forget")
    locks = "cmd:perm(Builder)"
    help_category = "Admin"

    def func(self):
        caller = self.caller
        room = _affinity_room(caller)
        if room is None:
            caller.msg("This room has no affinity memory.")
            return

        if "forget" in self.switches:
            room.save_memory(bridge.new_location(bridge.load_location_spec(room.db.location_id)))
            caller.msg(f"{room.key} forgets everything.")
            return

        if "age" in self.switches:
            try:
                days = float(self.args)
            except ValueError:
                caller.msg("Usage: @affinity/age <days>")
                return
            bridge.age(room.memory(), days * 86400)
            room.save_memory()
            caller.msg(f"{room.key}'s memories are now {days:g} days older.")
            return

        target = caller.search(self.args, global_search=True) if self.args else caller
        if not target:
            return
        if not hasattr(target, "affinity_tags"):
            caller.msg(f"{target.key} is not something places remember.")
            return
        caller.msg("\n".join(bridge.explain(room.memory(), target.affinity_id, target.affinity_tags())))


class CmdTrace(default_cmds.MuxCommand):
    """
    Explain recent affordance evaluations for a character (admin only).

    Usage:
      @trace [<character>] [= <count>]

    Shows the last <count> evaluations (default 3), newest last: what the
    character did, how the place felt, and what triggered.
    """

    key = "@trace"
    locks = "cmd:perm(Builder)"
    help_category = "Admin"

    def func(self):
        caller = self.caller
        target = caller.search(self.lhs, global_search=True) if self.lhs else caller
        if not target:
            return
        try:
            count = int(self.rhs) if self.rhs else 3
        except ValueError:
            caller.msg("Usage: @trace [<character>] [= <count>]")
            return
        history = (target.ndb.affordance_history or [])[-count:]
        if not history:
            caller.msg(f"No affordance evaluated for {target.key} since the last restart.")
            return
        lines = []
        for action_type, outcome in history:
            lines.append(f"[{action_type}] " + "\n".join(bridge.explain_outcome(outcome)))
        caller.msg("\n".join(lines))


class CmdToggleAff(default_cmds.MuxCommand):
    """
    Turn an affordance on or off everywhere (admin only).

    Usage:
      @toggleaff
      @toggleaff <affordance> on|off

    With no arguments, lists every affordance and whether it is on.
    Resets to config/affinity_defaults.yaml on server restart.
    """

    key = "@toggleaff"
    locks = "cmd:perm(Builder)"
    help_category = "Admin"

    def func(self):
        from world.affinity.affordances import admin_get_registry, admin_toggle_affordance

        caller = self.caller
        if not self.args:
            caller.msg("Affordances:\n" + "\n".join(
                f"  {name:<22} {'on' if on else 'off'}" for name, on in admin_get_registry().items()
            ))
            return

        parts = self.args.split()
        if len(parts) != 2 or parts[1] not in ("on", "off"):
            caller.msg("Usage: @toggleaff <affordance> on|off")
            return
        try:
            admin_toggle_affordance(parts[0], parts[1] == "on")
        except ValueError as e:
            caller.msg(str(e))
            return
        caller.msg(f"{parts[0]} is now {parts[1]}.")
