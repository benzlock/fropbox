#!/usr/bin/env python3

import collections
import difflib
import logging
import pathlib
import sys
import time

import file_segment
import server_wrapper

INTERVAL = 0.1

log = logging.getLogger("client")
log.addHandler(logging.StreamHandler(sys.stderr))
log.setLevel(logging.DEBUG)

Chunk = collections.namedtuple("Chunk", ("length", "start", "other_file_start", "other_file"))

class Client:
    "watches a directory and periodically uploads any new files it contains"
    def __init__(self, server, source, server_interface):
        # server should be a string with the server's URL
        # server_interface can be either requests (the package) or a Flask test_client,
        # both happen to have the same interface
        self.server = server_wrapper.Server(server, server_interface)
        self.source = source
        self.uploaded_files = set()

    def check(self):
        "check the source directory for new files and upload them"
        new_files = set(self.source.iterdir())

        for file in new_files - self.uploaded_files:
            log.info(f"Uploading {file}")
            upload_file(file, self.uploaded_files, self.server)
            self.uploaded_files.add(file)

    def loop(self, interval):
        "check the source directory forever"
        while True:
            time.sleep(interval)
            self.check()

def get_chunks(file, min_size, uploaded_files):
    "return a list of Chunks, at least `min_size` in length, that are shared by `file` and any of the files in `uploaded_files`"
    for other_file in uploaded_files:
        s = difflib.SequenceMatcher(None, file.read_bytes(), other_file.read_bytes())
        for chunk in s.get_matching_blocks():
            if chunk.size >= min_size:
                yield Chunk(chunk.size, chunk.a, chunk.b, other_file)

def get_file_parts(file, uploaded_files):
    "return a list of Chunks that, when reassembled, produces a copy of `file`"
    file_size = file.stat().st_size

    # get a list of chunks shared with other files and sort them by size
    chunks = get_chunks(file, 32, uploaded_files)
    chunks = sorted(chunks, key=lambda c: c.length, reverse=True)

    used_chunks = []
    # initialise a FileSegment object to track which parts of the file are still missing
    file_segments = file_segment.FileSegment(file_size)
    for chunk in chunks:
        # R is the chunk in (start, stop) form
        # if R represents a part of the file that is not already accounted for, then
        # add the chunk to our list of chunks and remove it from the file
        if (R := (chunk.start, chunk.start + chunk.length - 1)) in file_segments:
            file_segments.remove(*R)
            used_chunks += [chunk]
    # sort the chunks by their start position, i.e. their position in `file`
    used_chunks = sorted(used_chunks, key=lambda c: c.start)

    # at this point, there are some sections of `file` that are not accounted for by
    # chunks in `used_chunks`

    # used idx to track our position in file
    idx = 0
    while idx < file_size - 1:
        # if there is a chunk from another file starting at the current index, use that
        if used_chunks and used_chunks[0].start == idx:
            chunk = used_chunks.pop(0)
            yield chunk
            idx += chunk.length
        else:
            # otherwise, read from `file` until ...
            if used_chunks:
                # ... the start of the next chunk, if there is one available
                yield Chunk(used_chunks[0].start - idx, idx, None, None)
                idx = used_chunks[0].start
            else:
                # ... the end of the file, if no chunks are available
                yield Chunk(file_size - idx, idx, None, None)
                idx += file_size - idx

def upload_file(file: pathlib.Path, uploaded_files, wrapper):
    "upload a file to the server"

    with file.open("rb") as orig_file:
        for chunk in get_file_parts(file, uploaded_files):
            if chunk.other_file is None:
                # if chunk.other_file is none, we read data out of `file`
                orig_file.seek(chunk.start)
                chunk = orig_file.read(chunk.length)
                wrapper.upload(chunk, file)
            else:
                # if chunk.other_file is a file, there is no need to read anything, as
                # the server already has the data (unless the file that the server has
                # access to has been deleted, but we pretend this won't happen)
                wrapper.copy(file, chunk.other_file, chunk.other_file_start, chunk.length)

if __name__ == "__main__":
    source = pathlib.Path(sys.argv[1])

    log.info(f"Started Fropbox client, watching {source}")

    c = Client("http://127.0.0.1:11000", source, server_wrapper.requests)
    c.loop(INTERVAL)
