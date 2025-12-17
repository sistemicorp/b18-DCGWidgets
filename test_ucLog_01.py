import time
import asyncio
import random
import dearcygui as dcg
from dearcygui.utils.asyncio_helpers import AsyncPoolExecutor, run_viewport_loop
from timeit import default_timer as timer
from ucLog import UCLOG
from threading import Thread
from test_stats import build_viewport_menu_bar
from collections import deque

import logging
logger = logging.getLogger()
FORMAT = "%(asctime)s: %(filename)22s %(funcName)25s %(levelname)-5.5s :%(lineno)4s: %(message)s"
formatter = logging.Formatter(FORMAT)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)
logger.setLevel(logging.INFO)

# Sample log lines that are repeated by the multiplier below
# _, _, lvl, file, line, msg = item
log_lines = [
    (1, 0.0258556, 'INFO', 'Core/Src/main.c', 432, 'uptics: 255181, reset reason PO BO PIN SFT '),
    (2, 0.0263501, 'INFO', 'Core/Src/main.c', 432, 'uptics: 260181, reset reason PO BO PIN SFT '),
    (3, 0.0266459, 'INFO', 'Core/Src/main.c', 432, 'uptics: 265181, reset reason PO BO PIN SFT '),
    (4, 0.0268601, 'INFO', 'Core/Src/drvr_tmp102.c', 241, 'TMP102 @0x92 25 -> 26 DegC'),
    (5, 0.0270886, 'INFO', 'Core/Src/drvr_tmp102.c', 241, 'TMP102 @0x90 27 -> 28 DegC'),
    (6, 0.0272637, 'INFO', 'Core/Src/main.c', 432, 'uptics: 270181, reset reason PO BO PIN SFT '),
    (7, 0.0275047, 'DEBUG', 'Core/Src/main.c', 432, 'uptics: 275181, reset reason PO BO PIN SFT '),
    (8, 0.0277473, 'INFO', 'Core/Src/main.c', 432, 'uptics: 280181, reset reason PO BO PIN SFT '),
    (9, 0.0279855, 'INFO', 'Core/Src/main.c', 432, 'uptics: 285181, reset reason PO BO PIN SFT '),
    (10, 0.0282229, 'INFO', 'Core/Src/main.c', 432, 'uptics: 290181, reset reason PO BO PIN SFT '),
    (11, 0.0284705, 'INFO', 'Core/Src/main.c', 432, 'uptics: 295181, reset reason PO BO PIN SFT '),
    (12, 0.0287109, 'INFO', 'Core/Src/main.c', 432, 'uptics: 300181, reset reason PO BO PIN SFT '),
    (13, 0.028947, 'INFO', 'Core/Src/main.c', 432, 'uptics: 305181, reset reason PO BO PIN SFT '),
    (14, 0.0292323, 'INFO', 'Core/Src/main.c', 432, 'uptics: 310181, reset reason PO BO PIN SFT '),
    (15, 0.0294779, 'INFO', 'Core/Src/main.c', 432, 'uptics: 315181, reset reason PO BO PIN SFT '),
    (16, 0.0297162, 'ERROR', 'Core/Src/main.c', 432, 'uptics: 320181, reset reason PO BO PIN SFT '),
    (17, 0.0299487, 'INFO', 'Core/Src/main1.c', 432, 'uptics: 325181, reset reason PO BO PIN SFT '),
    (18, 0.0301822, 'INFO', 'Core/Src/main2.c', 432, 'uptics: 330181, reset reason PO BO PIN SFT '),
    (19, 0.0304183, 'INFO', 'Core/Src/main3.c', 432, 'uptics: 335181, reset reason PO BO PIN SFT '),
    (20, 0.0306585, 'WARN', 'Core/Src/main4.c', 432, 'uptics: 340181, reset reason PO BO PIN SFT '),
    (21, 0.0308912, 'INFO', 'Core/Src/drvr_tmp102.c', 241, 'TMP102 @0x96 33 -> 34 DegC'),
    (22, 0.0310774, 'INFO', 'Core/Src/main.c', 432, 'uptics: 345181, reset reason PO BO PIN SFT '),
    (23, 0.0312848, 'INFO', 'Core/Src/drvr_tmp102.c', 241, 'TMP102 @0x94 25 -> 26 DegC'),
    (24, 0.0314919, 'INFO', 'Core/Src/main.c', 432, 'uptics: 350181, reset reason PO BO PIN SFT '),
]
log_lines *= 100  # make larger to load the widget
log_lines = deque(log_lines)  # uses less CPU

run_thread = True
def thrd_send_lines(uclog):
    logger.info(f"start, log lines {len(log_lines)}")
    timer_started = timer()
    while run_thread and log_lines:
        line_to_add = list(log_lines.popleft())
        line_to_add[1] = timer() - timer_started
        uclog.add_log_line(line_to_add)
        delay = random.uniform(0.01, 0.2)
        time.sleep(delay)

    logger.info("end")


def main() -> None:
    global run_thread

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    C = dcg.Context()
    C.queue = AsyncPoolExecutor(loop=loop)

    C.viewport.wait_for_input = True
    C.viewport.initialize(title="My App", width=900, height=600)
    #C.viewport.wait_for_input = True

    build_viewport_menu_bar(C)

    with dcg.Window(C, label="Main", primary=True):
        dcg.Text(C, value="Now showing CPU, FPS, and Max FPS in the viewport menu bar.")

    uclog = UCLOG(C)

    Thread(target=thrd_send_lines, args=(uclog,), daemon=True).start()

    try:
        loop.run_until_complete(run_viewport_loop(C.viewport))
    finally:
        uclog.shutdown()
        run_thread = False
        C.running = False
        C.queue.shutdown()
        C.viewport.destroy()
        loop.stop()
        loop.close()


if __name__ == "__main__":
    main()
