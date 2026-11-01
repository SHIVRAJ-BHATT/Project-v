# ba_meta require api 9
from __future__ import annotations

import bascenev1 as bs


class SafeProp(bs.Actor):
    """A prop that deletes itself when it falls out of bounds."""

    def __init__(self, life: float | None = None, **attrs):
        super().__init__()
        self.node = bs.newnode('prop', delegate=self, attrs=attrs)
        if life:
            bs.timer(life, bs.WeakCall(self._die))
        self.autoretain()

    def _die(self) -> None:
        if self.node:
            self.node.delete()

    def handlemessage(self, msg):
        if isinstance(msg, (bs.OutOfBoundsMessage, bs.DieMessage)):
            self._die()
            return None
        return super().handlemessage(msg)
