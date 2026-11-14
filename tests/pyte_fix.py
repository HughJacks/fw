import pyte
# pyte 0.8.2 lacks SU/SD (CSI n S / CSI n T); real terminals scroll the margin region
def scroll_up(self, count=None, *a, **k):
    y = self.cursor.y
    self.cursor.y = self.margins.bottom if self.margins else self.lines - 1
    for _ in range(count or 1): self.index()
    self.cursor.y = y
def scroll_down(self, count=None, *a, **k):
    y = self.cursor.y
    self.cursor.y = self.margins.top if self.margins else 0
    for _ in range(count or 1): self.reverse_index()
    self.cursor.y = y
pyte.Screen.scroll_up, pyte.Screen.scroll_down = scroll_up, scroll_down
pyte.Stream.csi = {**pyte.Stream.csi, "S": "scroll_up", "T": "scroll_down"}
