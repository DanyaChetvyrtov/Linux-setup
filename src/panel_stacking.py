"""Keep unmanaged XFCE docks above applications during a BSPWM session."""
import select

from Xlib import X, Xatom, display, error

SELECTION = "_KALI_SETUP_PANEL_STACKING"
READY = "_KALI_SETUP_PANEL_STACKING_READY"


class PanelStacking:
    def __init__(self):
        self.connection = display.Display()
        self.root = self.connection.screen().root
        self.atoms = {}
        self.selection = self.atom(f"{SELECTION}_S{self.connection.get_default_screen()}")
        self.known = set()
        self.panels = set()
        self.owner = None
        self.wm = self.property(self.root, "_NET_SUPPORTING_WM_CHECK")
        self.connection.set_error_handler(self.x_error)

    @staticmethod
    def x_error(problem, request):
        # A window can close between inspecting it and configuring its stack.
        if not isinstance(problem, (error.BadWindow, error.BadDrawable)):
            raise problem

    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = self.connection.intern_atom(name)
        return self.atoms[name]

    def property(self, window, name):
        value = window.get_full_property(self.atom(name), X.AnyPropertyType)
        return list(value.value) if value is not None else []

    def is_bspwm(self):
        if not self.wm:
            return False
        window = self.connection.create_resource_object("window", self.wm[0])
        try:
            return bytes(self.property(window, "_NET_WM_NAME")) == b"bspwm"
        except error.BadWindow:
            return False

    def running(self):
        owner = self.connection.get_selection_owner(self.selection)
        try:
            return bool(owner and self.property(owner, "_NET_SUPPORTING_WM_CHECK") == self.wm
                        and self.property(owner, READY) == [1])
        except error.BadWindow:
            return False

    def claim(self):
        # Selection ownership is scoped to this X screen, including on reload.
        self.connection.grab_server()
        try:
            owner = self.connection.get_selection_owner(self.selection)
            try:
                if owner and self.property(owner, "_NET_SUPPORTING_WM_CHECK") == self.wm:
                    return False
            except error.BadWindow:
                pass
            self.owner = self.root.create_window(-1, -1, 1, 1, 0, 0, X.InputOnly)
            self.owner.change_property(self.atom("_NET_SUPPORTING_WM_CHECK"), Xatom.WINDOW, 32, self.wm)
            self.owner.set_selection_owner(self.selection, X.CurrentTime)
            return True
        finally:
            self.connection.ungrab_server()
            self.connection.flush()

    def adjust(self):
        if self.property(self.root, "_NET_SUPPORTING_WM_CHECK") != self.wm:
            return False
        children = self.root.query_tree().children  # XQueryTree orders bottom to top.
        live = {w.id for w in children}
        self.known.intersection_update(live)
        self.panels.intersection_update(live)
        clients = set(self.property(self.root, "_NET_CLIENT_LIST"))
        panels, applications, overlays = [], [], []
        overlay_types = {self.atom("_NET_WM_WINDOW_TYPE_" + kind)
                         for kind in ("MENU", "DROPDOWN_MENU", "POPUP_MENU", "NOTIFICATION")}
        for index, window in enumerate(children):
            try:
                if window.id not in self.known:
                    window.change_attributes(event_mask=X.PropertyChangeMask)
                    self.known.add(window.id)
                    cls = window.get_wm_class()
                    if (cls and cls[1] == "Xfce4-panel"
                            and self.atom("_NET_WM_WINDOW_TYPE_DOCK") in self.property(window, "_NET_WM_WINDOW_TYPE")):
                        self.panels.add(window.id)
                    else:
                        self.panels.discard(window.id)
                if window.id not in self.panels and window.id not in clients:
                    continue
                attributes = window.get_attributes()
                if attributes.map_state != X.IsViewable:
                    continue
                if window.id in self.panels:
                    panels.append((index, window))
                elif not attributes.override_redirect:
                    types = set(self.property(window, "_NET_WM_WINDOW_TYPE"))
                    states = self.property(window, "_NET_WM_STATE")
                    if (types & overlay_types or self.atom("_NET_WM_STATE_FULLSCREEN") in states):
                        overlays.append((index, window))
                    else:
                        applications.append((index, window))
            except error.BadWindow:
                continue
        upper = overlays[0] if overlays else None
        lower = next(((i, w) for i, w in reversed(applications) if not upper or i < upper[0]), None)
        for index, panel in panels:
            # Place relative to application windows, leaving popup/lock windows
            # above them intact. Changing only the stack preserves XFCE hiding,
            # the reveal sensor, panel geometry, reserved space, and input focus.
            if upper and index > upper[0]:
                panel.configure(sibling=upper[1], stack_mode=X.Below)
            elif lower and index < lower[0]:
                panel.configure(sibling=lower[1], stack_mode=X.Above)
        self.connection.flush()
        return True

    def run(self):
        self.root.change_attributes(event_mask=X.SubstructureNotifyMask | X.PropertyChangeMask)
        if not self.is_bspwm() or not self.claim():
            return
        if not self.adjust():
            return
        self.owner.change_property(self.atom(READY), Xatom.CARDINAL, 32, [1])
        self.connection.flush()
        properties = {self.atom(name) for name in (
            "_NET_SUPPORTING_WM_CHECK", "_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING",
            "_NET_CURRENT_DESKTOP", "_NET_WM_STATE", "_NET_WM_WINDOW_TYPE", "WM_CLASS")}
        while True:
            if not self.connection.pending_events():
                select.select([self.connection], [], [])
            dirty = False
            while self.connection.pending_events():
                event = self.connection.next_event()
                if event.type == X.SelectionClear:
                    return
                if event.type == X.DestroyNotify and event.window.id == self.wm[0]:
                    return
                if event.type == X.PropertyNotify:
                    if event.atom not in properties:
                        continue
                    if event.atom in (self.atom("WM_CLASS"), self.atom("_NET_WM_WINDOW_TYPE")):
                        self.known.discard(event.window.id)
                elif event.type not in (X.MapNotify, X.UnmapNotify, X.ConfigureNotify,
                                       X.DestroyNotify, X.ReparentNotify):
                    continue
                dirty = True
            if dirty and not self.adjust():
                return

    def close(self):
        self.connection.close()
