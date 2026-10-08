"""Interactive terminal dashboard for Akasia Doctor."""

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, OptionList, RichLog, Static
from textual.widgets.option_list import Option


class ResetConfirmation(ModalScreen[bool]):
    CSS = """
    ResetConfirmation { align: center middle; }
    #dialog { width: 64; max-width: 90%; height: auto; background: #193039;
              border: round #dbab65; padding: 1 2; }
    #warning { height: auto; margin-bottom: 1; }
    #dialog-actions { height: 3; align: right middle; }
    #dialog-actions Button { margin-left: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold]Back up and reset corrupted settings?[/bold]", id="warning")
            yield Static("A backup will be made before renaming each damaged user.config. POS business data is not changed.")
            with Horizontal(id="dialog-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Back up and reset", id="confirm", variant="warning")

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm")
    def confirm(self) -> None:
        self.dismiss(True)


class DoctorApp(App):
    TITLE = "Akasia Doctor"
    SUB_TITLE = "ClickOnce diagnostics"
    CSS = """
    Screen { background: #101d25; color: #e7eceb; }
    Header { background: #1f5552; color: #f5f2e9; }
    Footer { background: #193039; }
    #body { height: 1fr; }
    #sidebar { width: 29; background: #152b32; border-right: solid #3a6662; padding: 1; }
    #brand { height: 4; padding: 1; color: #f0bb74; text-style: bold; }
    #nav { height: 1fr; background: #152b32; }
    #main { width: 1fr; padding: 1 2; }
    #heading { height: 3; padding: 1; color: #f0bb74; text-style: bold; }
    #status { height: 4; background: #193039; padding: 0 1; }
    #items { height: 1fr; background: #101d25; margin-top: 1; }
    #actions { height: 4; align: left middle; }
    #actions Button { margin-right: 1; min-width: 14; }
    #activity-title { height: 2; color: #f0bb74; text-style: bold; }
    #activity { height: 8; border: solid #3a6662; background: #152b32; }
    """
    BINDINGS = [("q", "quit_doctor", "Quit"), ("s", "scan", "Scan"), ("r", "refresh", "Refresh")]

    def __init__(self, service, operations):
        super().__init__()
        self.service = service
        self.operations = operations
        self.view = "installations"
        self.busy = False
        self.config_items = []
        self.rows = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("AKASIA\nDOCTOR  /  01", id="brand")
                yield OptionList(
                    Option("01  Versions", id="installations"),
                    Option("02  Shortcuts", id="shortcuts"),
                    Option("03  Configuration", id="config"),
                    Option("04  Network", id="network"),
                    Option("05  History", id="history"),
                    Option("06  Reports", id="report"),
                    id="nav",
                )
            with Vertical(id="main"):
                yield Static(id="heading")
                yield Static(id="status")
                yield OptionList(id="items")
                with Horizontal(id="actions"):
                    yield Button("Scan", id="primary", variant="primary")
                    yield Button("Select", id="select")
                    yield Button("Launch", id="launch", variant="success")
                yield Static("ACTIVITY", id="activity-title")
                yield RichLog(id="activity", wrap=True, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()
        if not self.service.installations():
            self.start_operation("scan")

    def action_quit_doctor(self) -> None:
        if self.busy:
            self.notify("Wait for the current operation to finish.", severity="warning")
        else:
            self.exit()

    def action_scan(self) -> None:
        self.start_operation("scan")

    def action_refresh(self) -> None:
        if not self.busy:
            self.refresh_view()

    def refresh_view(self) -> None:
        titles = {"installations": "Discovered versions", "shortcuts": "ClickOnce shortcuts",
                  "config": "Configuration health", "network": "Network diagnostics",
                  "history": "Launch history", "report": "Diagnostic reports"}
        self.query_one("#heading", Static).update(titles[self.view].upper())
        selected = self.service.get("selected_exe") or "<none>"
        tested = self.service.get("last_tested") or "<none>"
        working = self.service.get("last_working") or "<none>"
        self.query_one("#status", Static).update(f"Selected: {selected}\nLast tested: {tested}\nLast working: {working}")
        items = self.query_one("#items", OptionList)
        items.clear_options()
        if self.view == "installations":
            self.rows = self.service.installations()
            for index, row in enumerate(self.rows):
                marker = "  *" if row["path"] == selected else ""
                items.add_option(Option(f"{row['version'] or 'Unknown version'}  |  {row['last_result'] or 'not tested'}{marker}\n{row['path']}", id=str(index)))
        elif self.view == "shortcuts":
            self.rows = self.service.shortcuts()
            for index, row in enumerate(self.rows):
                items.add_option(Option(row["path"], id=str(index)))
        elif self.view == "config":
            self.rows = []
            for item in self.config_items:
                items.add_option(Option(f"{'VALID' if item['valid'] else 'CORRUPTED'}  |  {item['path']}", id=str(item["path"])))
        elif self.view == "history":
            self.rows = []
            for row in self.service.launch_history():
                items.add_option(Option(f"{row['created']}  |  {row['result']}  |  {row['exit_hex'] or '-'}\n{row['path']}"))
        else:
            self.rows = []
        if not items.option_count:
            messages = {"installations": "No versions found. Run a scan.", "shortcuts": "No shortcuts found. Run a scan.",
                        "config": "Analyze configuration to see results.", "network": "Run a DNS test to check connectivity.",
                        "history": "No launches recorded yet.", "report": "Export a JSON report with diagnostic history."}
            items.add_option(Option(messages[self.view], disabled=True))
        elif self.rows:
            items.highlighted = 0
        primary = self.query_one("#primary", Button)
        primary.label = {"installations": "Scan", "shortcuts": "Scan", "config": "Analyze",
                         "network": "Test DNS", "history": "Refresh", "report": "Export JSON"}[self.view]
        self.query_one("#select", Button).display = self.view in ("installations", "shortcuts", "config")
        self.query_one("#select", Button).label = "Reset damaged" if self.view == "config" else "Select"
        self.query_one("#launch", Button).display = self.view in ("installations", "shortcuts")

    @on(OptionList.OptionSelected, "#nav")
    def navigate(self, event: OptionList.OptionSelected) -> None:
        if not self.busy:
            self.view = event.option.id
            self.refresh_view()

    @on(OptionList.OptionSelected, "#items")
    def choose(self, event: OptionList.OptionSelected) -> None:
        if not self.busy and self.view in ("installations", "shortcuts"):
            self.select_row(event.option_index)

    def select_row(self, index):
        if index is None or index >= len(self.rows):
            self.notify("Choose an item first.", severity="warning")
            return
        key = "selected_exe" if self.view == "installations" else "selected_shortcut"
        self.service.set(key, self.rows[index]["path"])
        self.log_message(f"Selected: {self.rows[index]['path']}")
        self.refresh_view()

    @on(Button.Pressed, "#primary")
    def primary(self) -> None:
        if self.view in ("installations", "shortcuts"):
            self.start_operation("scan")
        elif self.view == "config":
            self.start_operation("config")
        elif self.view == "network":
            self.start_operation("network")
        elif self.view == "report":
            self.start_operation("report")
        else:
            self.refresh_view()

    @on(Button.Pressed, "#select")
    def select(self) -> None:
        if self.busy:
            return
        if self.view == "config":
            if any(not item["valid"] for item in self.config_items):
                self.push_screen(ResetConfirmation(), self.confirm_reset)
            else:
                self.notify("Analyze configuration first; no damaged files are listed.", severity="warning")
        else:
            self.select_row(self.query_one("#items", OptionList).highlighted)

    def confirm_reset(self, confirmed: bool) -> None:
        if confirmed:
            self.start_operation("reset")

    @on(Button.Pressed, "#launch")
    def launch(self) -> None:
        self.start_operation("exe" if self.view == "installations" else "shortcut")

    def log_message(self, message):
        self.query_one("#activity", RichLog).write(message)

    def start_operation(self, action):
        if self.busy:
            self.notify("An operation is already running.", severity="warning")
            return
        self.busy = True
        self.log_message(f"Working: {action}...")
        self.perform_action(action)

    @work(thread=True, exclusive=True)
    def perform_action(self, action):
        try:
            if action == "scan":
                executables, shortcuts = self.operations.scan()
                result = f"Found {executables} executable(s) and {shortcuts} shortcut(s)."
            elif action == "config":
                items = self.operations.config_health()
                result = "\n".join(f"{'VALID' if item['valid'] else 'CORRUPTED'}: {item['path']}" +
                                   (f" ({item['error']})" if not item["valid"] else "") for item in items) or "No Akasia user.config files were found."
                self.call_from_thread(self.set_config_items, items)
            elif action == "reset":
                results, folder = self.operations.reset_configs()
                result = "\n".join(f"{state.upper()}: {path}" + (f" ({error})" if error else "") for path, state, error in results) or "No corrupted configuration was found."
                if folder:
                    result += f"\nBackups: {folder}"
                self.call_from_thread(self.set_config_items, [])
            elif action == "network":
                result = "\n".join(f"{host}: {', '.join(addresses) if not error else 'FAILED - ' + error}" for host, addresses, error in self.operations.network_test())
            elif action == "report":
                result = f"Report: {self.operations.export_report()}"
            elif action == "exe":
                result = self.operations.launch_exe(self.service.get("selected_exe"))
            else:
                result = self.operations.launch_shortcut(self.service.get("selected_shortcut"))
        except Exception as exc:
            result = f"Operation failed: {exc}"
        self.call_from_thread(self.finish_action, result)

    def set_config_items(self, items):
        self.config_items = items

    def finish_action(self, result):
        self.busy = False
        self.log_message(result)
        self.refresh_view()