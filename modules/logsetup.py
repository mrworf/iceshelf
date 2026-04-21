"""Shared logging setup helpers for iceshelf commands."""

import logging
import os
import shutil
import tempfile


class LoggingSession:
    """Manage logger handlers and optional capture log files."""

    def __init__(
        self,
        *,
        logger,
        level,
        formatter,
        stream=None,
        logfile_path=None,
        capture_to_temp=False,
    ):
        self.logger = logger
        self.level = level
        self.formatter = formatter
        self.stream = stream
        self.logfile_path = logfile_path
        self._handlers = []
        self._owned_capture_path = None
        self.capture_path = None

        self._configure_logger()
        if stream is not None:
            self._add_stream_handler(stream)
        if logfile_path:
            self._add_file_handler(logfile_path)
        if capture_to_temp:
            self._add_temp_capture_handler()

    def _configure_logger(self):
        self.logger.handlers = []
        self.logger.setLevel(self.level)

    def _add_stream_handler(self, stream):
        handler = logging.StreamHandler(stream)
        handler.setLevel(self.level)
        handler.setFormatter(self.formatter)
        self.logger.addHandler(handler)
        self._handlers.append(handler)

    def _add_file_handler(self, path):
        handler = logging.FileHandler(path)
        handler.setLevel(self.level)
        handler.setFormatter(self.formatter)
        self.logger.addHandler(handler)
        self._handlers.append(handler)

    def _add_temp_capture_handler(self):
        fd, path = tempfile.mkstemp(prefix="iceshelf-log.", suffix=".log")
        os.close(fd)
        self._owned_capture_path = path
        self.capture_path = path
        self._add_file_handler(path)

    @property
    def artifact_source_path(self):
        if self.logfile_path:
            return self.logfile_path
        return self.capture_path

    def flush(self):
        for handler in self._handlers:
            try:
                handler.flush()
            except Exception:
                pass

    def snapshot(self, destination):
        source = self.artifact_source_path
        if not source:
            raise ValueError("No logfile source is configured for snapshotting")

        self.flush()

        if os.path.abspath(source) == os.path.abspath(destination):
            return destination

        shutil.copyfile(source, destination)
        return destination

    def cleanup(self):
        for handler in list(self._handlers):
            try:
                handler.flush()
            except Exception:
                pass
            self.logger.removeHandler(handler)
            handler.close()
        self._handlers = []

        if self._owned_capture_path and os.path.exists(self._owned_capture_path):
            try:
                os.unlink(self._owned_capture_path)
            except OSError:
                pass
        self._owned_capture_path = None
        self.capture_path = None


def create_logging_session(*, debug=False, logfile_path=None, stream=None, capture_to_temp=False):
    """Create a logging session using iceshelf's existing log formatting rules."""
    level = logging.DEBUG if debug else logging.INFO
    if debug:
        fmt = '%(asctime)s - %(filename)s@%(lineno)d - %(levelname)s - %(message)s'
    elif logfile_path:
        fmt = '%(asctime)s - %(levelname)s - %(message)s'
    else:
        fmt = '%(message)s'

    formatter = logging.Formatter(fmt)
    logger = logging.getLogger()
    return LoggingSession(
        logger=logger,
        level=level,
        formatter=formatter,
        stream=stream,
        logfile_path=logfile_path,
        capture_to_temp=capture_to_temp,
    )
