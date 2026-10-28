"""
Characters

Characters are (by default) Objects setup to be puppeted by Accounts.
They are what you "see" in game. The Character class in this module
is setup to be the "default" character type created by the default
creation commands.

"""

from evennia.objects.objects import DefaultCharacter

from .objects import ObjectParent


class Character(ObjectParent, DefaultCharacter):
    """
    The Character just re-implements some of the Object's methods and hooks
    to represent a Character entity in-game.

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Object child classes like this.

    Characters carry affinity tags (Evennia tags in the "affinity" category,
    e.g. "human", "elf") that places remember as group identity.
    """

    DEFAULT_AFFINITY_TAGS = ("human", "outsider")

    def at_object_creation(self):
        super().at_object_creation()
        for tag in self.DEFAULT_AFFINITY_TAGS:
            self.tags.add(tag, category="affinity")

    @property
    def affinity_id(self):
        """Stable id places remember this character by."""
        return self.dbref

    def affinity_tags(self):
        return set(self.tags.get(category="affinity", return_list=True))

    def at_post_move(self, source_location, move_type="move", **kwargs):
        super().at_post_move(source_location, move_type=move_type, **kwargs)
        from typeclasses.rooms import AffinityRoom
        from world import bridge

        if move_type == "traverse" and isinstance(self.location, AffinityRoom):
            outcome = self.location.answer(self, "move.arrive", bridge.ARRIVE_AFFORDANCES)
            for tell in outcome.tells:
                self.msg(tell)
