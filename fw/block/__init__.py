"""fw.block — the block model, pure functions over the store's blocks (by id); no files.

case    the content cases: accessors and new blocks
text    words, titles and times
tree    walking blocks: reach (a closure) and fold (flat: into a list), what holds what
view    what a block shows: its text, items, draft and title
masks   masks on disk (per block) and in memory (anchors)
links   hyperlinks moved with edits, and backlinks
visits  stretches of attention
kinds   tags: answers and a model's guesses
rank    the garden's memory and the graph's hubs, for home and "from here"
"""

from fw.block.case import *     # noqa: F401,F403
from fw.block.text import *     # noqa: F401,F403
from fw.block.tree import *     # noqa: F401,F403
from fw.block.view import *     # noqa: F401,F403
from fw.block.masks import *    # noqa: F401,F403
from fw.block.kinds import *    # noqa: F401,F403
from fw.block.links import *    # noqa: F401,F403
from fw.block.visits import *   # noqa: F401,F403
from fw.block.rank import *     # noqa: F401,F403
