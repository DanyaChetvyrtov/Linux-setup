"""Add inner gaps to XFWM's native half-screen and quarter-screen tiles."""
from dataclasses import dataclass
import select
import time

from Xlib import X, Xatom, Xutil, display, error, protocol

MARKER = "_KALI_SETUP_WINDOW_GAP"
SLOTS = ("left", "right", "up", "down", "up-left", "up-right", "down-left", "down-right")


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def values(self):
        return (self.x, self.y, self.width, self.height)


def tiles(area, gap=0):
    """Keep outer edges fixed and split the inner gap across adjacent tiles."""
    low, high = gap // 2, gap - gap // 2
    mx, my = area.width // 2, area.height // 2
    xs = {"left": (area.x, mx - low),
          "right": (area.x + mx + high, area.width - mx - high)}
    ys = {"up": (area.y, my - low),
          "down": (area.y + my + high, area.height - my - high)}
    result = {}
    for name in SLOTS:
        horizontal = next((s for s in xs if s in name), None)
        vertical = next((s for s in ys if s in name), None)
        x, width = xs[horizontal] if horizontal else (area.x, area.width)
        y, height = ys[vertical] if vertical else (area.y, area.height)
        result[name] = Rect(x, y, width, height)
    return result


def matches(actual, expected, increments=(1, 1)):
    # XFWM can round terminal dimensions down to their character-cell sizes.
    return (abs(actual.x - expected.x) <= 1 and abs(actual.y - expected.y) <= 1
            and 0 <= expected.width - actual.width <= max(1, increments[0] - 1)
            and 0 <= expected.height - actual.height <= max(1, increments[1] - 1))


def size_hints(window):
    hints = window.get_wm_normal_hints()
    result = {"min_width": 1, "min_height": 1, "width_inc": 1, "height_inc": 1}
    if hints is not None:
        for flag, names in ((Xutil.PMinSize, ("min_width", "min_height")),
                            (Xutil.PResizeInc, ("width_inc", "height_inc"))):
            if hints.flags & flag:
                for name in names:
                    result[name] = max(1, getattr(hints, name))
    return result


class GapListener:
    def __init__(self, gap):
        if type(gap) is not int or not 0 <= gap <= 100:
            raise ValueError("inner_gap must be an integer from 0 to 100 pixels.")
        self.gap = gap
        self.connection = display.Display()
        self.root = self.connection.screen().root
        self.atoms = {}
        self.windows = {}
        self.dirty = set()
        self.stopping = False
        self.connection.set_error_handler(self.x_error)

    @staticmethod
    def x_error(problem, request):
        # Clients can disappear between an event and the corresponding request.
        if not isinstance(problem, (error.BadWindow, error.BadDrawable)):
            raise problem

    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = self.connection.intern_atom(name)
        return self.atoms[name]

    def property(self, window, name):
        value = window.get_full_property(self.atom(name), X.AnyPropertyType)
        return list(value.value) if value is not None else []

    def clients(self):
        return self.property(self.root, "_NET_CLIENT_LIST")

    def extents(self, window):
        frame = self.property(window, "_NET_FRAME_EXTENTS") or [0, 0, 0, 0]
        # CSD shadows extend outside the visible window, unlike XFWM borders.
        if not any(frame):
            shadow = self.property(window, "_GTK_FRAME_EXTENTS")
            if len(shadow) == 4:
                return tuple(-v for v in shadow)
        return tuple(frame)

    def geometry(self, window):
        geometry = window.get_geometry()
        position = self.root.translate_coords(window, 0, 0)
        left, right, top, bottom = self.extents(window)
        return Rect(position.x - left, position.y - top,
                    geometry.width + left + right, geometry.height + top + bottom)

    def workarea(self, window, rect):
        desktop = self.property(window, "_NET_WM_DESKTOP")
        current = self.property(self.root, "_NET_CURRENT_DESKTOP") or [0]
        index = desktop[0] if desktop and desktop[0] != 0xffffffff else current[0]
        areas = self.property(self.root, "_NET_WORKAREA")
        values = areas[index * 4:index * 4 + 4]
        if len(values) != 4:
            return None
        area = Rect(*values)
        try:
            monitors = self.root.xrandr_get_monitors().monitors
        except (AttributeError, error.XError):
            monitors = []
        cx, cy = rect.x + rect.width // 2, rect.y + rect.height // 2
        for monitor in monitors:
            if (monitor.x <= cx < monitor.x + monitor.width_in_pixels
                    and monitor.y <= cy < monitor.y + monitor.height_in_pixels):
                x, y = max(area.x, monitor.x), max(area.y, monitor.y)
                end_x = min(area.x + area.width, monitor.x + monitor.width_in_pixels)
                end_y = min(area.y + area.height, monitor.y + monitor.height_in_pixels)
                return Rect(x, y, end_x - x, end_y - y)
        return area

    def eligible(self, window):
        types = self.property(window, "_NET_WM_WINDOW_TYPE")
        states = self.property(window, "_NET_WM_STATE")
        excluded = ("FULLSCREEN", "MAXIMIZED_HORZ", "MAXIMIZED_VERT", "HIDDEN", "SHADED")
        return (not window.get_wm_transient_for()
                and (not types or self.atom("_NET_WM_WINDOW_TYPE_NORMAL") in types)
                and not any(self.atom("_NET_WM_STATE_" + s) in states for s in excluded))

    def place(self, window, rect):
        left, right, top, bottom = self.extents(window)
        width, height = rect.width - left - right, rect.height - top - bottom
        hints = size_hints(window)
        if width < max(1, hints.get("min_width", 1)) or height < max(1, hints.get("min_height", 1)):
            return False
        # StaticGravity makes coordinates refer to the client, including CSD shadows.
        flags = X.StaticGravity | (15 << 8) | (2 << 12)
        event = protocol.event.ClientMessage(window=window,
                    client_type=self.atom("_NET_MOVERESIZE_WINDOW"),
                    data=(32, [flags, (rect.x + left) & 0xffffffff,
                               (rect.y + top) & 0xffffffff, width, height]))
        self.root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        return True

    def adjust(self, window):
        if not self.eligible(window):
            return
        rect = self.geometry(window)
        hints = size_hints(window)
        increments = (hints.get("width_inc", 1), hints.get("height_inc", 1))
        marker = self.property(window, MARKER)
        area = self.workarea(window, rect)
        if area is None:
            return
        if len(marker) == 10 and marker[0] == 1 and 0 <= marker[1] < len(SLOTS):
            if matches(rect, Rect(*marker[6:10]), increments):
                target = tiles(area, self.gap)[SLOTS[marker[1]]]
                if matches(rect, target, increments):
                    return
                if self.place(window, target):
                    window.change_property(self.atom(MARKER), Xatom.INTEGER, 32,
                                           marker[:6] + list(target.values()))
                return
            window.delete_property(self.atom(MARKER))
        for slot, native in tiles(area).items():
            if matches(rect, native, increments):
                target = tiles(area, self.gap)[slot]
                if target != native and self.place(window, target):
                    window.change_property(self.atom(MARKER), Xatom.INTEGER, 32,
                        [1, SLOTS.index(slot), *rect.values(), *target.values()])
                return

    def refresh(self):
        clients = set(self.clients())
        for wid in clients - self.windows.keys():
            window = self.connection.create_resource_object("window", wid)
            try:
                window.change_attributes(event_mask=X.StructureNotifyMask | X.PropertyChangeMask)
                self.windows[wid] = window
                self.dirty.add(wid)
            except error.BadWindow:
                pass
        for wid in self.windows.keys() - clients:
            del self.windows[wid]
            self.dirty.discard(wid)

    def restore_windows(self):
        for wid in self.clients():
            window = self.connection.create_resource_object("window", wid)
            try:
                marker = self.property(window, MARKER)
                hints = size_hints(window)
                increments = (hints.get("width_inc", 1), hints.get("height_inc", 1))
                if len(marker) == 10 and marker[0] == 1:
                    if self.eligible(window) and matches(self.geometry(window), Rect(*marker[6:10]), increments):
                        self.place(window, Rect(*marker[2:6]))
                    window.delete_property(self.atom(MARKER))
            except error.BadWindow:
                pass
        self.connection.sync()

    def run(self, ready=None):
        self.root.change_attributes(event_mask=X.PropertyChangeMask | X.SubstructureNotifyMask)
        self.refresh()
        deadline = time.monotonic()
        if ready:
            ready()
        relevant = {self.atom(n) for n in ("_NET_WM_STATE", "_NET_FRAME_EXTENTS",
                   "_GTK_FRAME_EXTENTS", "WM_NORMAL_HINTS", "_NET_WM_DESKTOP")}
        root_relevant = {self.atom(n) for n in ("_NET_WORKAREA", "_NET_CURRENT_DESKTOP",
                                              "_NET_CLIENT_LIST")}
        while not self.stopping:
            while self.connection.pending_events():
                event = self.connection.next_event()
                wid = getattr(getattr(event, "window", None), "id", None)
                if wid == self.root.id and (event.type == X.ConfigureNotify
                        or (event.type == X.PropertyNotify and event.atom in root_relevant)):
                    self.refresh()
                    self.dirty.update(self.windows)
                elif wid in self.windows and (event.type == X.ConfigureNotify
                        or (event.type == X.PropertyNotify and event.atom in relevant)):
                    self.dirty.add(wid)
                else:
                    continue
                deadline = time.monotonic() + 0.075
            if self.dirty and time.monotonic() >= deadline:
                buttons = X.Button1Mask | X.Button2Mask | X.Button3Mask
                if self.root.query_pointer().mask & buttons:
                    deadline = time.monotonic() + 0.075
                else:
                    dirty, self.dirty = self.dirty, set()
                    for wid in dirty:
                        try:
                            if wid in self.windows:
                                self.adjust(self.windows[wid])
                        except error.BadWindow:
                            pass
                    self.connection.flush()
            timeout = max(0, min(0.5, deadline - time.monotonic())) if self.dirty else 0.5
            select.select([self.connection.fileno()], [], [], timeout)

    def close(self):
        self.connection.close()
