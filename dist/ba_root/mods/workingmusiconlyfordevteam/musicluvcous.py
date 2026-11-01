# Released under the MIT License. See LICENSE for details.
#
# Auto-generated; do not edit by hand.
"""Asset-package wrapper for ``a-a19262415.musicluvcous.dev261031`` (bascenev1).

Source files for an asset-package: textures, meshes, sounds, and translated
strings. Publish versions of it for your mods and servers to use.
"""

# ba_meta require api 9
# ba_meta require asset-package 988

# pylint: disable=useless-suppression
# pylint: disable=too-many-lines
# pylint: disable=too-few-public-methods, disallowed-name

from typing import TYPE_CHECKING

from bacommon.assetpackage import ApverNum

from bascenev1._assetref import AssetGroup

# a-a19262415.musicluvcous.dev261031
_ASSET_PACKAGE = ApverNum(988)

if TYPE_CHECKING:
    from bascenev1._assetref import SoundHandle

    class MydirGroup:
        """Asset-group type; see source for the full list."""

        music1: SoundHandle
        music2: SoundHandle

    #: The ``mydir`` group - 2 assets (``music1``, ``music2``). Full list in
    #: source.
    mydir: MydirGroup

_TREE = {'mydir': {'music1': 's', 'music2': 's'}}


if not TYPE_CHECKING:
    mydir = AssetGroup(_ASSET_PACKAGE, _TREE['mydir'], 'mydir')
