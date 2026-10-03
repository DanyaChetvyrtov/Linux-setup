#!/usr/bin/env python3
"""Show live XFCE hotkeys with editable descriptions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from shortcut_catalog import Binding, annotation_path, default_description, extract_bindings, read_annotation

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Xfconf", "0")
from gi.repository import Gio, GLib, Gtk, Pango, Xfconf

HOTKEY, DESCRIPTION, COMMAND, PROVIDER, SHORTCUT, PROPERTY, ANNOTATED = range(7)
CATEGORIES = {"commands": "Applications", "xfwm4": "Windows & workspaces"}


class ShortcutStore:
    def __init__(self, metadata_channel="kali-setup-shortcuts"):
        if not Xfconf.init():
            raise RuntimeError("Could not connect to your desktop settings")
        self.bindings = Xfconf.Channel.new("xfce4-keyboard-shortcuts")
        self.notes = Xfconf.Channel.new(metadata_channel)
        self.metadata_channel = metadata_channel

    def rows(self):
        catalog = json.loads((REPO / "config/shortcut-descriptions.json").read_text())
        notes = self.notes.get_properties("/descriptions")
        rows = []
        for provider in CATEGORIES:
            override = self.bindings.get_bool(f"/{provider}/custom/override", False)
            base = f"/{provider}/" + ("custom" if override else "default")
            for binding in extract_bindings(provider, self.bindings.get_properties(base), base):
                key, modifiers = Gtk.accelerator_parse(binding.shortcut)
                label = Gtk.accelerator_get_label(key, modifiers) if key else binding.shortcut
                saved = read_annotation(binding, notes.get(annotation_path(binding)))
                description = saved if saved is not None else default_description(binding, catalog)
                rows.append([label, description, binding.command, provider, binding.shortcut,
                             binding.property, saved is not None])
        return sorted(rows, key=lambda row: (row[PROVIDER] != "commands", row[HOTKEY].casefold()))

    def save(self, binding, description):
        if self.bindings.get_string(binding.property, None) != binding.command:
            raise RuntimeError("This shortcut changed while you were editing. Select it again and retry.")
        path = annotation_path(binding)
        description = description.strip()
        if description:
            value = json.dumps({"command": binding.command, "description": description}, ensure_ascii=False)
            if not self.notes.set_string(path, value):
                raise RuntimeError("Could not save the description")
        else:
            self.notes.reset_property(path, False)


class ShortcutWindow(Gtk.ApplicationWindow):
    def __init__(self, application, backend):
        super().__init__(application=application, title="Shortcuts")
        self.backend = backend
        self.set_default_size(1120, 680)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name("preferences-desktop-keyboard")
        self.reload_id = 0
        self.signal_ids = []
        self.store = Gtk.ListStore(str, str, str, str, str, str, bool)
        self.filtered = self.store.filter_new()
        self.filtered.set_visible_func(self.visible)
        self.sorted = Gtk.TreeModelSort(model=self.filtered)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=20)
        self.add(outer)
        title = Gtk.Label(label="Your shortcuts", xalign=0)
        title.set_markup('<span size="x-large" weight="bold">Your shortcuts</span>')
        outer.pack_start(title, False, False, 0)
        subtitle = Gtk.Label(label="Application and window hotkeys, with descriptions you can edit.", xalign=0)
        subtitle.get_style_context().add_class("dim-label")
        outer.pack_start(subtitle, False, False, 0)

        toolbar = Gtk.Box(spacing=10)
        self.search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search hotkeys, descriptions, or commands")
        self.search.connect("search-changed", self.refilter)
        toolbar.pack_start(self.search, True, True, 0)
        self.category = Gtk.ComboBoxText()
        self.category.append("all", "All shortcuts")
        for provider, label in CATEGORIES.items():
            self.category.append(provider, label)
        self.category.set_active_id("all")
        self.category.connect("changed", self.refilter)
        toolbar.pack_start(self.category, False, False, 0)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Refresh shortcuts")
        refresh.get_accessible().set_name("Refresh shortcuts")
        refresh.connect("clicked", lambda _button: self.reload())
        toolbar.pack_start(refresh, False, False, 0)
        outer.pack_start(toolbar, False, False, 0)

        self.tree = Gtk.TreeView(model=self.sorted, headers_visible=True, enable_search=False)
        self.tree.set_tooltip_column(COMMAND)
        self.tree.get_selection().connect("changed", self.selection_changed)
        self.tree.connect("row-activated", lambda *_args: self.edit_description())
        for name, column_id, width in [("Hotkey", HOTKEY, 220), ("Description", DESCRIPTION, 390),
                                      ("Command", COMMAND, 390)]:
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, xpad=10, ypad=8)
            if column_id == DESCRIPTION:
                renderer.set_property("editable", True)
                renderer.connect("edited", self.inline_description)
            column = Gtk.TreeViewColumn(name, renderer, text=column_id)
            column.set_resizable(True)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(width)
            column.set_min_width(130)
            column.set_sort_column_id(column_id)
            if column_id == COMMAND:
                column.set_expand(True)
            if column_id == DESCRIPTION:
                column.set_cell_data_func(renderer, self.description_cell)
            self.tree.append_column(column)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        outer.pack_start(scroll, True, True, 0)

        footer = Gtk.Box(spacing=10)
        self.count = Gtk.Label(xalign=0, hexpand=True)
        self.count.get_style_context().add_class("dim-label")
        footer.pack_start(self.count, True, True, 0)
        self.edit_button = Gtk.Button(label="Edit description…", sensitive=False)
        self.edit_button.connect("clicked", lambda _button: self.edit_description())
        footer.pack_start(self.edit_button, False, False, 0)
        settings = Gtk.MenuButton(label="Edit hotkeys…")
        menu = Gtk.Menu()
        for label, command in [("Application shortcuts", "xfce4-keyboard-settings"),
                               ("Window & workspace shortcuts", "xfwm4-settings")]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, cmd=command: self.open_settings(cmd))
            menu.append(item)
        menu.show_all()
        settings.set_popup(menu)
        footer.pack_start(settings, False, False, 0)
        outer.pack_start(footer, False, False, 0)
        hint = Gtk.Label(label="Super = Windows key. Double-click a row to edit its description.", xalign=0)
        hint.get_style_context().add_class("dim-label")
        outer.pack_start(hint, False, False, 0)

        # Observe D-Bus directly: PyGObject cannot marshal Xfconf's unset GValue
        # when a property is removed. Both change and removal signals are valid here.
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        for channel in ["xfce4-keyboard-shortcuts", backend.metadata_channel]:
            self.signal_ids.append(self.bus.signal_subscribe(
                "org.xfce.Xfconf", "org.xfce.Xfconf", None, "/org/xfce/Xfconf", channel,
                Gio.DBusSignalFlags.NONE, self.changed))
        self.connect("destroy", self.cleanup)
        self.connect("key-press-event", self.key_pressed)
        self.reload()

    def visible(self, model, iterator, _data=None):
        if not hasattr(self, "search") or not hasattr(self, "category"):
            return True
        selected = self.category.get_active_id()
        if selected != "all" and model.get_value(iterator, PROVIDER) != selected:
            return False
        text = " ".join(model.get_value(iterator, column) for column in [HOTKEY, DESCRIPTION, COMMAND])
        terms = self.search.get_text().casefold().split()
        return all(term in text.casefold() for term in terms)

    def description_cell(self, _column, renderer, model, iterator, _data=None):
        description = model.get_value(iterator, DESCRIPTION)
        renderer.set_property("text", description or "Add a description…")
        renderer.set_property("style", Pango.Style.NORMAL if description else Pango.Style.ITALIC)

    def selected_row(self):
        model, iterator = self.tree.get_selection().get_selected()
        return list(model[iterator]) if iterator is not None else None

    @staticmethod
    def binding(row):
        return Binding(row[PROVIDER], row[SHORTCUT], row[COMMAND], row[PROPERTY])

    def reload(self):
        if self.reload_id:
            GLib.source_remove(self.reload_id)
        self.reload_id = 0
        selected = self.selected_row()
        try:
            rows = self.backend.rows()
        except (GLib.Error, ValueError, OSError) as error:
            self.show_error("Could not refresh shortcuts", error)
            return False
        self.store.clear()
        for row in rows:
            self.store.append(row)
        self.refilter()
        if selected:
            for row in self.sorted:
                if (row[PROVIDER], row[SHORTCUT]) == (selected[PROVIDER], selected[SHORTCUT]):
                    self.tree.get_selection().select_path(row.path)
                    break
        return False

    def refilter(self, *_args):
        self.filtered.refilter()
        shown, total = len(self.sorted), len(self.store)
        self.count.set_text(f"{shown} of {total} shortcuts" if shown != total else f"{total} shortcuts")
        self.selection_changed()

    def changed(self, _connection, _sender, _path, _interface, signal, _parameters, _data=None):
        if signal not in ("PropertyChanged", "PropertyRemoved"):
            return
        if not self.reload_id:
            self.reload_id = GLib.timeout_add(100, self.reload_changed)

    def reload_changed(self):
        self.reload_id = 0
        return self.reload()

    def selection_changed(self, *_args):
        self.edit_button.set_sensitive(self.selected_row() is not None)

    def save_description(self, row, text):
        try:
            self.backend.save(self.binding(row), text)
            self.reload()
        except (GLib.Error, RuntimeError) as error:
            self.show_error("Could not save the description", error)

    def inline_description(self, _renderer, path, text):
        self.save_description(list(self.sorted[Gtk.TreePath.new_from_string(path)]), text)

    def edit_description(self):
        row = self.selected_row()
        if row is None:
            return
        dialog = Gtk.Dialog(title="Edit description", transient_for=self, modal=True)
        dialog.add_button("Reset to default", Gtk.ResponseType.REJECT)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_default_size(520, -1)
        box = dialog.get_content_area()
        box.set_spacing(12)
        box.set_border_width(18)
        box.pack_start(Gtk.Label(label=row[HOTKEY], xalign=0), False, False, 0)
        command = Gtk.Label(label=row[COMMAND], xalign=0, wrap=True, selectable=True)
        command.set_max_width_chars(65)
        command.get_style_context().add_class("dim-label")
        box.pack_start(command, False, False, 0)
        entry = Gtk.Entry(text=row[DESCRIPTION], activates_default=True)
        entry.set_placeholder_text("Describe what this shortcut does")
        box.pack_start(entry, False, False, 0)
        dialog.show_all()
        entry.grab_focus()
        entry.select_region(0, -1)
        response = dialog.run()
        text = entry.get_text()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.save_description(row, text)
        elif response == Gtk.ResponseType.REJECT:
            self.save_description(row, "")

    def show_error(self, title, error):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.CLOSE, text=title)
        dialog.format_secondary_text(str(error))
        dialog.run()
        dialog.destroy()

    def open_settings(self, command):
        try:
            subprocess.Popen([command], start_new_session=True)
        except OSError as error:
            self.show_error("Could not open shortcut settings", error)

    def key_pressed(self, _widget, event):
        from gi.repository import Gdk
        if event.keyval == Gdk.KEY_f and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
            return True
        if event.keyval == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text("")
            else:
                self.close()
            return True
        return False

    def cleanup(self, *_args):
        if self.reload_id:
            GLib.source_remove(self.reload_id)
            self.reload_id = 0
        for signal_id in self.signal_ids:
            self.bus.signal_unsubscribe(signal_id)
        self.signal_ids.clear()


class ShortcutApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.kalisetup.Shortcuts", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            try:
                window = ShortcutWindow(self, ShortcutStore())
            except (GLib.Error, OSError, ValueError, RuntimeError) as error:
                dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
                                           text="Could not open Shortcuts")
                dialog.format_secondary_text(str(error))
                dialog.run()
                dialog.destroy()
                self.quit()
                return
        window.show_all()
        window.present()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print the current shortcuts as JSON without opening a window")
    args = parser.parse_args()
    if args.list:
        rows = ShortcutStore().rows()
        print(json.dumps([{"hotkey": row[HOTKEY], "description": row[DESCRIPTION], "command": row[COMMAND],
                           "category": CATEGORIES[row[PROVIDER]], "shortcut": row[SHORTCUT]} for row in rows], indent=2))
        return 0
    return ShortcutApplication().run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
