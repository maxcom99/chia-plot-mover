import os
import shutil
import threading
import time
import shlex
import subprocess
from typing import Dict, List

import yaml

from src.lock import Lock
from src.logger import logger


class PlotMover:
    CONFIG_FILE_NAME = 'config.yaml'
    SLEEP_PERIOD = 60
    MIN_K32_PLOT_SIZE = 108 * 10 ** 9

    _config: Dict

    def __init__(self):
        self._config = self._read_config()
        self._lock = Lock()
        self._mutex = threading.Lock()

    def _read_config(self):
        current_dir = os.path.dirname(__file__)
        config_path = os.path.join(current_dir, '..', self.CONFIG_FILE_NAME)
        filename = os.path.abspath(os.path.realpath(config_path))

        with open(filename, 'r') as stream:
            try:
                return yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

    def _look_for_plots(self) -> List[Dict]:
        result = []

        for dir_ in self._config.get('source'):
            if dir_ not in self._lock.sour:
                for file in os.listdir(dir_):
                    if file.endswith(".plot") and file not in self._lock.plot:
                        plot_path = os.path.join(dir_, file)
                        size = os.path.getsize(plot_path)

                        if size < self.MIN_K32_PLOT_SIZE:
                            logger.warning(f'Main thread: Plot file {plot_path} size is to small. Is it real plot?')
                        else:
                            result.append({'dir': dir_, 'file': file, 'size': size})
                            break

        return result

    def _look_for_destination(self, needed_space) -> str:
        for dir_ in self._config.get('dest'):
            _, _, free = shutil.disk_usage(dir_)
            if free > needed_space and dir_ not in self._lock.dest:
                return dir_

    @staticmethod
    def move_plot(self, src_dir, plot_file, dst_dir, size, lock):
        src_path = os.path.join(src_dir, plot_file)
        dst_path = os.path.join(dst_dir, plot_file)
        temp_dst_path = dst_path + '.move'

        move_mode = config.get('mode')

        if os.path.isfile(dst_path):
            raise Exception(f'Copy thread: Plot file {dst_path} already exists. Duplicate?')

        self._mutex.acquire()
        if dst_dir not in self._lock.dest:
            lock.plot.append(plot_file)
            lock.dest.append(dst_dir)
            lock.sour.append(src_dir)
        self._mutex.release()

        logger.info(f'Copy thread: Starting to move plot from {src_path} to {dst_path}')
        start = time.time()
        #duration = round(time.time() - start, 1)
        if move_mode == 'rsync':
            rsync_param = "rsync -i -vIWhcCca --compress-level=0 --numeric-ids --inplace --remove-source-files {src_path} {dst_path}" 
            sub_call = shlex.split(rsync_param)
            subprocess.call(sub_call)
        else:
            shutil.move(src_path, temp_dst_path)
            shutil.move(temp_dst_path, dst_path)
        #speed = (size / duration) // (2 ** 20)
        #logger.info(f'Copy thread: Plot file {src_path} moved, time: {duration} s, avg speed: {speed} MiB/s')

        lock.plot.remove(plot_file)
        lock.dest.remove(dst_dir)
        lock.sour.remove(src_dir)

    def main(self):
        while True:
            plots = self._look_for_plots()

            for plot in plots:
                src_dir = plot.get("dir")
                file = plot.get("file")
                size = plot.get("size")
                plot_path = os.path.join(src_dir, file)

                #logger.info(f'Main thread: Found plot {plot_path} of size {size // (2 ** 30)} GiB')

                time.sleep(self._config.get('debounce'))

                dst_dir = self._look_for_destination(size)

                if dst_dir:
                    thread = threading.Thread(target=self.move_plot, args=(src_dir, file, dst_dir, size, self._lock, self._config))
                    thread.start()
                else:
                    logger.warning(f'Main thread: No destination available for plot {plot_path}')
                    time.sleep(self._config.get('sleep'))
            else:
                logger.info(f"Main thread: No plots found. Sleep for {self._config.get('sleep')}s")
                time.sleep(self._config.get('sleep'))
