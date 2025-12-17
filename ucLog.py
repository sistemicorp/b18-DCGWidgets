"""
MIT License...

TODOs
1. add option to discard filtered lines
2. add STOP/RECORD
"""
from threading import Thread, Event, Timer
import queue
import dearcygui as dcg
import colorsys
from enum import IntEnum
import traceback
from timeit import default_timer as timer

import logging
logger = logging.getLogger()


class UCLOG(Thread):
    """ ucLog GUI Instance

    """
    WINDOW_TITLE = "ucLog"
    TABLE_MAX_ROWS = 20000
    TABLE_ROWS_DELETE_CHUNK = int(TABLE_MAX_ROWS / 10)  # num rows to purge when MAX exceeded
    TABLE_SCROLL_TIMEOUT_SEC = 0.1

    class Events(IntEnum):
        EVENT_SHUTDOWN = 0
        EVENT_ADD_LOGLINE = 1
        EVENT_CLEAR = 2
        EVENT_APPLY_FILE_FILTER = 3
        EVENT_UPDATE_TABLE_SHOW = 4
        EVENT_EXPORT = 5
        EVENT_TIMER_CLEAR_TITLEBAR = 6
        EVENT_PURGE_LOG_LINES = 7

    NUM_FILENAME_COLORS = 100
    COMBO_LEVEL_WIDTH = 120
    COMBO_FILES_WIDTH = 200
    COMBO_FILES_ITEMS_DEFAULT = ["File Filter", "All ON", "All OFF"]
    BUTTON_CLEAR_WIDTH = 60
    BUTTON_EXPORT_WIDTH = BUTTON_CLEAR_WIDTH
    COMBO_SCALE_WIDTH = 90

    ROW_USERDATA_IDX_ROW = 0
    ROW_USERDATA_IDX_LEVEL = 1
    ROW_USERDATA_IDX_FILE = 2

    # levels, listed in the order of show precedence
    LOG_LEVEL_COLORS = {
        'DEBUG': (255, 255, 255),
        'INFO': (128, 255, 128),
        'WARN': (255, 255, 0),
        'ERROR': (255, 0, 0),
    }

    def _create_color_pallette(self) -> None:
        """ Programmatic Way to create background colors
        - AI generated code, takes into account WCAG contrast ratio
        - adjusts to the colors used in the LOG_LEVEL_COLORS dict
        - runs only once on init
        """
        # Vivid-but-dark backgrounds so LOG_LEVEL_COLORS stay readable.
        # We also enforce a minimum WCAG contrast ratio against all log-level text colors.
        phi = 0.618033988749895  # golden ratio conjugate

        def _srgb_to_linear(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        def _rel_luminance(rgb_255: tuple[int, int, int]) -> float:
            r, g, b = (x / 255.0 for x in rgb_255)
            r, g, b = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
            la = _rel_luminance(a)
            lb = _rel_luminance(b)
            lighter, darker = (la, lb) if la >= lb else (lb, la)
            return (lighter + 0.05) / (darker + 0.05)

        def _darken(rgb_255: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
            # factor in (0..1); smaller = darker
            return tuple(max(0, min(255, int(x * factor))) for x in rgb_255)

        min_contrast = 4.0  # slightly less strict -> allows more "pop" while staying readable
        text_colors = list(self.LOG_LEVEL_COLORS.values())

        saturation = 0.95  # a touch more vivid
        lightness_levels = (0.22, 0.28, 0.34)  # brighter than before -> more pop

        for i in range(self.NUM_FILENAME_COLORS):
            hue = (i * phi) % 1.0
            lightness = lightness_levels[i % len(lightness_levels)]

            rgb_float = colorsys.hls_to_rgb(hue, lightness, saturation)
            bg = tuple(int(max(0.0, min(1.0, x)) * 255) for x in rgb_float)

            # Enforce readability for ALL log-level text colors by darkening if needed
            for _ in range(12):
                if min(_contrast_ratio(bg, tc) for tc in text_colors) >= min_contrast:
                    break
                bg = _darken(bg, factor=0.92)  # gentler darkening -> keeps more pop

            self._palette.append(bg)

    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._q = queue.SimpleQueue()
        self._stop_event = Event()

        self._num_rows = 0
        self._num_rows_start = 0
        self._filenames = []
        self._filenames_filter = {
            "all_on": True,
            "all_off": False,

            # filenames will be keys here as follows
            # "filename": {"show": <True/False, ...}
        }
        self._scale = 1.0
        self._scroll = True
        self._scroll_last_object = None
        self._scroll_last_time = 0.0
        self._scroll_timer = None

        self._font = dcg.AutoFont.get_monospaced(self._ctx)
        self._theme_font = dcg.ThemeStyleImGui(self._ctx,
                                               frame_padding=(0,0),
                                               cell_padding=(-1,-1))

        self._theme_text_color_map = {
            "DEBUG": dcg.ThemeColorImGui(self._ctx, text=self.LOG_LEVEL_COLORS.get("DEBUG", (0,0,0))),
            "INFO": dcg.ThemeColorImGui(self._ctx, text=self.LOG_LEVEL_COLORS.get("INFO", (0,0,0))),
            "WARN": dcg.ThemeColorImGui(self._ctx, text=self.LOG_LEVEL_COLORS.get("WARN", (0,0,0))),
            "ERROR": dcg.ThemeColorImGui(self._ctx, text=self.LOG_LEVEL_COLORS.get("ERROR", (0,0,0))),
        }

        self._palette = []
        self._create_color_pallette()
        self._levels = list(self.LOG_LEVEL_COLORS.keys())
        self._show_levels = self._levels[self._levels.index("INFO"):]

        with dcg.Window(self._ctx,
                        label="ucLog",
                        horizontal_scrollbar=True,
                        width=800,
                        height=400) as self._window:

            with dcg.HorizontalLayout(self._ctx):
                _button_export = dcg.Button(self._ctx,
                                            label="Export",
                                            width=self.BUTTON_EXPORT_WIDTH,
                                            callback=self._cb_button_export)

                with dcg.Tooltip(self._ctx, target=_button_export):
                    dcg.Text(self._ctx, value="Export contents to csv file")

                self._combo_level = dcg.Combo(self._ctx,
                                              width=self.COMBO_LEVEL_WIDTH,
                                              label="",
                                              items=self._levels,
                                              value="INFO",
                                              callback=self._cb_set_level_filter)

                self._combo_files = dcg.Combo(self._ctx,
                                              width=self.COMBO_FILES_WIDTH,
                                              label="",
                                              items=self.COMBO_FILES_ITEMS_DEFAULT,
                                              value=self.COMBO_FILES_ITEMS_DEFAULT[0],
                                              callback=self._cb_set_file_filter)

                self._checkbox_scroll = dcg.Checkbox(self._ctx,
                                                     label="Scroll",
                                                     callback=self._cb_scroll,
                                                     value=True)

                self._button_clear = dcg.Button(self._ctx,
                                                label="Clear",
                                                width=self.BUTTON_CLEAR_WIDTH,
                                                callback=self._cb_button_clear)

                dcg.Combo(self._ctx,
                          label="",
                          items=["70%", "80%", "90%", "100%", "110%"],
                          width=self.COMBO_SCALE_WIDTH,
                          value="100%",
                          callback=self._cb_combo_scale)

            self._table = dcg.Table(self._ctx,
                                    header=False,
                                    width=-1,
                                    height=-1,
                                    font=self._font,
                                    theme=self._theme_font,
                                    flags=dcg.TableFlag.SCROLL_Y)

        self.name = "thread_uclog"
        self.start()

    def __show_levels(self, level: str = "INFO") -> list:
        """ Return a list of log levels to show
        :param level:
        :return:
        """
        return self._levels[self._levels.index(level):]

    def _cb_set_file_filter(self, sender, target, data) -> None:
        logger.info(f"sender {sender}, target {target}, data {data}")
        if data not in self.COMBO_FILES_ITEMS_DEFAULT:
            # remove suffix " ON" or " OFF"
            data = data.rsplit(" ")[0]

        self._q.put({"type": self.Events.EVENT_APPLY_FILE_FILTER, "item": data})

        # put back the title in the combo box
        self._combo_files.value = self.COMBO_FILES_ITEMS_DEFAULT[0]

    def _cb_click_text(self, sender, target, data):
        logger.info(f"sender {sender}, target {target}, data {data}")
        logger.info(f"user_data {target.user_data} : {target.value}")

    def _cb_set_level_filter(self, sender, target, data) -> None:
        logger.info(f"sender {sender}, target {target}, data {data}")
        self._show_levels = self._levels[self._levels.index(data):]
        self._q.put({"type": self.Events.EVENT_UPDATE_TABLE_SHOW, "item": data})

    def _cb_scroll(self, sender, target, data) -> None:
        logger.info(f"sender {sender}, target {target}, data {data}")
        self._scroll = data

        if self._scroll:
            self._scroll_last_object.focus()

    def _cb_combo_scale(self, sender, target, data) -> None:
        logger.info(f"sender {sender}, target {target}, data {data}")
        self._window.scaling_factor = float(data.replace('%','')) / 100.0

    def _cb_button_export(self, sender, target, data) -> None:
        logger.info(f"sender {sender}, target {target}, data {data}")
        self._q.put({"type": self.Events.EVENT_EXPORT})

    def _tmr_clear_titlebar(self):
        logger.info(f"start")
        self._q.put({"type": self.Events.EVENT_TIMER_CLEAR_TITLEBAR})

    def _event_timer_clear_titlebar(self):
        self._window.label = f"{self.WINDOW_TITLE}"

    def _event_purge_log_lines(self):
        logger.info(f"start total {self._num_rows - self._num_rows_start} rows, delete {self.TABLE_ROWS_DELETE_CHUNK} rows")
        for idx in range(self._num_rows_start, self._num_rows_start + self.TABLE_ROWS_DELETE_CHUNK):
            del self._table[idx, 0]

        self.TABLE_MAX_ROWS += self.TABLE_ROWS_DELETE_CHUNK
        self._num_rows_start += self.TABLE_ROWS_DELETE_CHUNK

        self._window.label = f"{self.WINDOW_TITLE} purged {self.TABLE_ROWS_DELETE_CHUNK} rows"
        Timer(5.0, self._tmr_clear_titlebar).start()

    def _cb_save_file(self, file_paths) -> None:
        logger.info(f"file_paths {file_paths}")
        if file_paths and len(file_paths) > 0:

            with open(file_paths[0], "w", newline="") as f:
                for idx in range(self._num_rows_start, self._num_rows):
                    row_data = self._table[idx, 0].content.value
                    t, lvl, file, line, msg = row_data.split(":", 4)
                    f.write(f"{t.strip()},{lvl.strip()},{file.strip()},{line.strip()},{msg.strip()}\n")

            self._window.label = f"{self.WINDOW_TITLE} exported to: {file_paths[0]}"
            Timer(5.0, self._tmr_clear_titlebar).start()

        self._ctx.viewport.wake()

    def _event_export(self) -> None:
        filters = [
            ("Text Files", "txt"),
            ("CSV Files", "csv"),
            ("All Files", "*")
        ]
        dcg.os.show_save_file_dialog(self._ctx,
                                     callback=self._cb_save_file,
                                     default_location="~/Documents/myfile.txt",
                                     filters=filters,
                                     title="Save File As")

    def _cb_button_clear(self, sender, target, data) -> None:
        logger.info(f"sender {sender}, target {target}, data {data}")
        self._q.put({"type": self.Events.EVENT_CLEAR})

    def _event_clear(self) -> None:
        self._num_rows = 0
        self._filenames = []
        self._filenames_filter["all_on"] = True
        self._filenames_filter["all_off"] = False
        self._table.clear()
        self._combo_file_rebuild()

    def _event_apply_file_filter(self, item) -> None:
        logger.info(f"item: {item}")

        if item == "All ON":
            self._filenames_filter["all_on"] = True
            self._filenames_filter["all_off"] = False
            for f in self._filenames:
                self._filenames_filter[f] = True

        elif item == "All OFF":
            self._filenames_filter["all_on"] = False
            self._filenames_filter["all_off"] = True
            for f in self._filenames:
                self._filenames_filter[f] = False

        else:
            self._filenames_filter["all_on"] = False
            self._filenames_filter["all_off"] = False
            self._filenames_filter[item] = not self._filenames_filter[item]

        self._combo_file_rebuild()
        self._q.put({"type": self.Events.EVENT_UPDATE_TABLE_SHOW})

    def _event_update_table_show(self):
        logger.info(f"start")
        start = timer()
        _show_levels = self.__show_levels(self._combo_level.value)

        for idx in range(self._num_rows_start, self._num_rows):
            #logger.info(f"idx {idx} {self._table[idx, 0].content.user_data}")
            row_data = self._table[idx, 0].content.user_data
            _show_file = self._filenames_filter[row_data[self.ROW_USERDATA_IDX_FILE]]
            _show_level = True if row_data[self.ROW_USERDATA_IDX_LEVEL] in _show_levels else False
            self._table.row_config[idx].show = _show_file and _show_level

        delta = timer() - start
        logger.info(f"apply level filter took {delta:.3f} seconds, {self._num_rows} rows")

    def add_log_line(self, item: tuple[int, float, str, str, int, str]) -> None:
        self._q.put({"type": self.Events.EVENT_ADD_LOGLINE, "item": item})

    def _combo_file_rebuild(self):
        logger.info(f"rebuild combo files")
        _new_files_combo = list(self.COMBO_FILES_ITEMS_DEFAULT)
        if self._filenames_filter["all_on"]:
            for f in self._filenames:
                _new_files_combo.append(f"{f} ON")

        elif self._filenames_filter["all_off"]:
            for f in self._filenames:
                _new_files_combo.append(f"{f} OFF")

        else:
            for f in self._filenames:
                if self._filenames_filter[f]:
                    _new_files_combo.append(f"{f} ON")
                else:
                    _new_files_combo.append(f"{f} OFF")

        self._combo_files.items = _new_files_combo

    def _event_add_logline(self, item: tuple[int, float, str, str, int, str]) -> None:
        startTime = timer()
        with self._table.next_row:
            _, t, lvl, file, line, msg = item

            # filenames are tracked to add row background color per filename
            if file not in self._filenames:
                self._filenames.append(file)
                if self._filenames_filter["all_off"]:
                    self._filenames_filter[file] = False
                self._filenames_filter[file] = True
                self._combo_file_rebuild()

            color_idx = self._filenames.index(file) % self.NUM_FILENAME_COLORS
            self._table.row_config[self._num_rows].bg_color = self._palette[color_idx]

            _color = self.LOG_LEVEL_COLORS.get(lvl, (0,0,0))

            self._scroll_last_object = dcg.Text(self._ctx,
                                                theme=self._theme_text_color_map[lvl],
                                                user_data=(self._num_rows, lvl, file),  # used for filtering
                                                value=f"{t:9.4f}:{lvl:5s}:{file:30s}:{line:5d}:{msg}")

            self._scroll_last_object.handlers = [dcg.ClickedHandler(self._ctx, callback=self._cb_click_text)]

        self._table.row_config[self._num_rows].show = self._filenames_filter[file] and lvl in self._show_levels

        if self._scroll and self._table.row_config[self._num_rows].show:
            # throttle scrolling to self.TABLE_SCROLL_TIMEOUT_SEC
            if timer() - self._scroll_last_time > self.TABLE_SCROLL_TIMEOUT_SEC:
                self._scroll_last_time= timer()
                self._scroll_last_object.focus()
                if self._scroll_timer: self._scroll_timer.cancel()

            elif self._scroll_timer is None:
                # if no events come in, have a timer to flush
                self._scroll_timer = Timer(self.TABLE_SCROLL_TIMEOUT_SEC, self._scroll_last_object.focus)

        self._num_rows += 1
        if self._num_rows > self.TABLE_MAX_ROWS:
            self.__q({"type": self.Events.EVENT_PURGE_LOG_LINES})

        # debug performance only
        if self._num_rows % 1000 == 0:
            delta = timer() - startTime
            logger.info(f"add_log_line took {delta:.3f} seconds, at {self._num_rows} rows")

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def shutdown(self):
        self._q.put({"type": self.Events.EVENT_SHUTDOWN})

    def _event_shutdown(self):
        self._stop_event.set()

    def __q(self, item_dict: dict):
        self._q.put(item_dict)

    def run(self):
        logger.info(f"{self.name} run thread started")

        while not self.is_stopped():

            try:
                item = self._q.get(block=True)
                #logger.debug(item)

                match item["type"]:
                    case self.Events.EVENT_SHUTDOWN:
                        self._event_shutdown()

                    case self.Events.EVENT_ADD_LOGLINE:
                        self._event_add_logline(item["item"])

                    case self.Events.EVENT_APPLY_FILE_FILTER:
                        self._event_apply_file_filter(item["item"])

                    case self.Events.EVENT_UPDATE_TABLE_SHOW:
                        self._event_update_table_show()

                    case self.Events.EVENT_CLEAR:
                        self._event_clear()

                    case self.Events.EVENT_EXPORT:
                        self._event_export()

                    case self.Events.EVENT_TIMER_CLEAR_TITLEBAR:
                        self._event_timer_clear_titlebar()

                    case self.Events.EVENT_PURGE_LOG_LINES:
                        self._event_purge_log_lines()

                    case _:
                        logger.error("Unknown event: {}".format(item["type"]))

            except queue.Empty:
                pass

            except Exception as e:
                logger.error("Error processing event {}, {}".format(e, item["type"]))
                traceback.print_exc()

        logger.info(f"{self.name} run thread stopped")
