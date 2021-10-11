#!/usr/bin/env python3

import collections
import inspect
import itertools
import os
import pathlib
import random
import tempfile
import unittest

from file_segment import FileSegment

import client
import server

# recipe from itertools
def grouper(iterable, n, fillvalue=None):
    "Collect data into non-overlapping fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)

class CallLogger:
    """
    A CallLogger object wraps a class and produces a log of methods called on the
    object, as well as their arguments
    """

    Call = collections.namedtuple("Call", ("name", "args"))

    def __init__(self, cls):
        self.calls = []
        self.cls = cls

    def __getattr__(self, name):
        """
        If C is an instance of CallLogger, C.method(arg1, arg2) will call
        C.__getattr__(name='method'). We return a dummy function that logs the name
        'method' and the args.
        """

        def logger_func(*args, **kwargs):
            # get the function being called in the wrapped class by looking in its
            # __dict__
            func = self.cls.__dict__[name]
            # add a None to the list of args, to stand in for 'self'
            args = (None,) + args
            # convert a list of args and a dict of kwargs to a dict of kwargs, so we can
            # know which of the arguments passed in the method call corresponds to which
            # of the method's arguments
            args = inspect.getcallargs(func, *args, **kwargs)
            self.calls += [CallLogger.Call(name, args)]

            # this function will return None; if necessary, CallLogger could be extended
            # to wrap instances of a class instead, and actually call that instance's
            # methods
            # IOW returning to the example above, C.method(...) will return None
            # regargdless of what calling 'method' on an instance of the wrapped class
            # would return
            return None

        return logger_func

class TestFileSegment(unittest.TestCase):

    def test_init(self):
        "check that FileSegment objects initialise correctly"
        s = FileSegment(10)
        self.assertEqual(s.segments, [(0, 9)])

    def test_unaffected_segment(self):
        "check cases where the removed segment does not overlap with an existing segment"
        s = FileSegment(10)

        s.remove(-5, -1)
        self.assertEqual(s.segments, [(0, 9)])

        s.remove(10, 15)
        self.assertEqual(s.segments, [(0, 9)])

    def test_removed_segment(self):
        "check cases where an existing segment is fully inside the removed segment"
        s = FileSegment(10)
        s.remove(0, 9)
        self.assertEqual(s.segments, [])

        s = FileSegment(10)
        s.remove(-1, 10)
        self.assertEqual(s.segments, [])

    def test_split_segment(self):
        "check cases where an existing segment is split into two parts by the removal"
        s = FileSegment(10)
        s.remove(1, 8)
        self.assertEqual(s.segments, [(0, 0), (9, 9)])

    def test_edges(self):
        "check cases where one end of an existing segment is covered by the removed segment"
        s = FileSegment(10)
        s.remove(-5, 5)
        self.assertEqual(s.segments, [(6, 9)])

        s = FileSegment(10)
        s.remove(5, 15)
        self.assertEqual(s.segments, [(0, 4)])

    def test_random(self):
        "randomised test of FileSegment"
        # this test works by creating a FileSegment object and remove some
        # segments from it while performing the same calculation with a set
        # of indices, then checking at the end that the results match. For
        # example, a FileSegment object with length 5 would be represented
        # by {0,1,2,3,4}. Removing segment (2,3) from this would be
        # represented by segment list [(0,1),(4,4)]
        # and set {0,1,4}
        for _ in range(1000):
            # initialise a random-length FileSegment object
            seg_length = random.randint(10, 1000)
            s = FileSegment(seg_length)
            # create also a set containing every index represented by the
            # FileSegment
            indexes = set(range(seg_length))

            # removals must be non-overlapping, so the maximum number of
            # removals is floor(length of segment / 2). This would be
            # equivalent to removing (0,1), (2,3), (4,5), etc.
            max_removals = seg_length // 2

            # each removed segment has two ends. The total number of segment
            # ends is a random even number that is less than max_removals
            num_seg_ends = 2 * random.randint(1, max_removals // 2)
            # choose the actual segment ends we will be using by sampling
            # without duplicates
            seg_ends = random.sample(range(seg_length), k=num_seg_ends)
            # sort the segment ends, then pair them up into tuples, each of
            # which will represent one removal
            seg_ends = sorted(seg_ends)
            removals = grouper(seg_ends, 2, None)

            for start, stop in removals:
                # remove each of the segments
                s.remove(start, stop)

                # execute the same removal on the set of indices
                for i in range(start, stop+1):
                    indexes.remove(i)

            # iterate over the remaining segments in the FileSegment object,
            # removing them from the index set
            for start, stop in s.segments:
                for i in range(start, stop+1):
                    indexes.remove(i)

            # if everything worked correctly, the indices represented by the
            # FileSegment object should be exactly equal to the indices in
            # the index set, and removing the indices in the FileSegment
            # object should leave us with an empty index set
            self.assertEqual(indexes, set())

class TestClient(unittest.TestCase):

    def setUp(self):
        "before each client test is run, create some files to use for the tests"
        # create a temporary directory to store the files in
        self.tempdir = tempfile.TemporaryDirectory()
        tempdir = pathlib.Path(self.tempdir.name)
        self.files = {}

        # create two files that have nothing in common with each other
        different_1 = tempdir/"different-1"
        different_2 = tempdir/"different-2"
        self.files["different"] = (different_1, different_2)
        with different_1.open("wb") as file:
            file.write(random.randbytes(2**10))
        with different_2.open("wb") as file:
            file.write(random.randbytes(2**10))

        # create two files that are duplicates of each other
        duplicates_1 = tempdir/"duplicates-1"
        duplicates_2 = tempdir/"duplicates-2"
        self.files["duplicates"] = (duplicates_1, duplicates_2)
        duplicated_file = random.randbytes(2**10)
        with duplicates_1.open("wb") as file:
            file.write(duplicated_file)
        with duplicates_2.open("wb") as file:
            file.write(duplicated_file)

        # create two files with some shared sections
        shared_section_1 = tempdir/"shared-section-1"
        shared_section_2 = tempdir/"shared-section-2"
        self.files["shared_section"] = (shared_section_1, shared_section_2)
        # generate the shared sections themselves
        duplicated_sections = [random.randbytes(2**8) for _ in range(10)]
        # section_positions_1 maps a position in file 1 to the section that starts there
        self.section_positions_1 = {}
        with shared_section_1.open("wb") as file:
            file.write(random.randbytes(2**6))
            for section in duplicated_sections:
                self.section_positions_1[file.tell()] = section
                # write the section into the file, followed by some padding before the
                # next section
                file.write(section)
                file.write(random.randbytes(2**6))

        # reorder the sections
        random.shuffle(duplicated_sections)
        # section_positions_2 maps sections to their positions in file 2
        self.section_positions_2 = {}
        with shared_section_2.open("wb") as file:
            file.write(random.randbytes(2**6))
            for section in duplicated_sections:
                self.section_positions_2[section] = file.tell()
                file.write(section)
                file.write(random.randbytes(2**6))

    def tearDown(self):
        "after each test, remove the temporary directory"
        self.tempdir.cleanup()

    def test_get_chunks_full_file(self):
        "when the file we are uploading has nothing in common with the already-uploaded files, get_chunks returns nothing"
        file_1, file_2 = self.files["different"]
        chunks = client.get_chunks(file_1, 32, [file_2])
        chunks = tuple(chunks)
        self.assertEqual(chunks, tuple())

    def test_get_chunks_duplicate(self):
        "when the file being uploaded is a duplicate, get_chunks should return one full-length chunk"
        file_1, file_2 = self.files["duplicates"]
        chunks = client.get_chunks(file_1, 32, [file_2])
        chunks = tuple(chunks)
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk.length, file_1.stat().st_size)
        self.assertEqual(chunk.other_file, file_2)

    def test_get_chunks_sections(self):
        "check that shared file sections are identified correctly"
        file_1, file_2 = self.files["shared_section"]
        chunks = client.get_chunks(file_1, 32, [file_2])

        for chunk in chunks:
            # get the contents of the section using section_positions_1
            section = self.section_positions_1[chunk.start]
            # get the start position in file 2 of the section using section_positions_2,
            # and check that this matches the section's start position as given by
            # chunk.other_file_start
            self.assertEqual(chunk.other_file_start, self.section_positions_2[section])
            # sections shorter than 32 bytes should have been filtered out
            self.assertGreater(chunk.length, 32)

    def test_parts_full_file(self):
        "when the file we are uploading has nothing in common wiith the already-uploaded files, get_file_parts returns one full-length part"
        file_1, file_2 = self.files["different"]
        parts = client.get_file_parts(file_1, [file_2])
        parts = tuple(parts)
        self.assertEqual(len(parts), 1)
        part = parts[0]
        self.assertEqual(part.length, file_1.stat().st_size)
        self.assertEqual(part.start, 0)
        self.assertEqual(part.other_file_start, None)
        self.assertEqual(part.other_file, None)

    def test_parts_duplicate(self):
        "when the file being uploaded is a duplicate, get_file_parts returns one full-length chunk from the already-uploaded file"
        file_1, file_2 = self.files["duplicates"]
        parts = client.get_file_parts(file_1, [file_2])
        parts = tuple(parts)
        self.assertEqual(len(parts), 1)
        part = parts[0]
        self.assertEqual(part.length, file_1.stat().st_size)
        self.assertEqual(part.start, 0)
        self.assertEqual(part.other_file_start, 0)
        self.assertEqual(part.other_file, file_2)

    def test_parts_sections(self):
        "check get_file_parts for files with some shared sections"
        file_1, file_2 = self.files["shared_section"]
        parts = client.get_file_parts(file_1, [file_2])

        with file_1.open("rb") as file:
            for part in parts:
                # our current position in the file must equal the start position of the
                # part
                self.assertEqual(file.tell(), part.start)
                self.assertGreater(part.length, 0)
                if part.other_file is None:
                    # if we are reading from the file being uploaded, the chunk will
                    # match the file being uploaded, so we do not need to check this.
                    # we ensure that other_file_start is None and advance the cursor
                    self.assertEqual(part.other_file_start, None)
                    file.read(part.length)
                else:
                    # if we are reading from a differrent file, open it,
                    with part.other_file.open("rb") as other_file:
                        # seek to the start location of this chunk,
                        other_file.seek(part.other_file_start)
                        # read the chunk, and
                        chunk = other_file.read(part.length)
                        # assert that the chunk is equal to the same chunk in the
                        # uploading file
                        self.assertEqual(chunk, file.read(part.length))

            # once we have checked all of the parts, the cursor should be at the end of
            # the file
            self.assertEqual(file.tell(), file_1.stat().st_size)

    # the tests below use CallLogger, defined above, to test the behaviour of
    # upload_file
    def test_upload_full_file(self):
        "when the file being uploaded has no common sections, we expect one call to Server.upload"
        file_1, file_2 = self.files["different"]
        logger = CallLogger(client.server_wrapper.Server)
        client.upload_file(file_1, [file_2], logger)
        calls = logger.calls

        self.assertEqual(len(calls), 1)

        call = calls[0]
        self.assertEqual(call.name, "upload")
        self.assertEqual(call.args["file"], file_1)
        self.assertEqual(call.args["data"],  file_1.read_bytes())

    def test_upload_duplicate(self):
        "when the file being uploaded is a duplicate, we expect one call to Server.copy"
        file_1, file_2 = self.files["duplicates"]
        logger = CallLogger(client.server_wrapper.Server)
        client.upload_file(file_1, [file_2], logger)
        calls = logger.calls

        self.assertEqual(len(calls), 1)

        call = calls[0]
        self.assertEqual(call.name, "copy")
        self.assertEqual(call.args["file"], file_1)
        self.assertEqual(call.args["other_file"], file_2)
        self.assertEqual(call.args["offset"], 0)
        self.assertEqual(call.args["length"], file_1.stat().st_size)

    def test_upload_sections(self):
        "when the file being uploaded has some shared sectioins, we expect... something"
        file_1, file_2 = self.files["shared_section"]
        logger = CallLogger(client.server_wrapper.Server)
        client.upload_file(file_1, [file_2], logger)
        calls = logger.calls

        with file_1.open("rb") as file:
            for call in calls:
                if call.name == "upload":
                    self.assertEqual(call.args["file"], file_1)

                    # if the call is to Server.upload (i.e. a new chunk, not present in
                    # another file) is being uploaded, we assert that the chunk being
                    # uploaded matches the next section of the file
                    chunk = call.args["data"]
                    self.assertEqual(chunk, file.read(len(chunk)))
                if call.name == "copy":
                    self.assertEqual(call.args["file"], file_1)
                    self.assertEqual(call.args["other_file"], file_2)

                    # if the call is to Server.copy (i.e. a chunk is being copied from a
                    # file that has already been uploaded) then we open the file we are
                    # reading from and check that the section being indicated matches
                    # the file being uploaded
                    with call.args["other_file"].open("rb") as other_file:
                        other_file.seek(call.args["offset"])
                        chunk = other_file.read(call.args["length"])
                        self.assertEqual(chunk, file.read(len(chunk)))

            self.assertEqual(file.tell(), file_1.stat().st_size)

class TestServer(unittest.TestCase):

    def setUp(self):
        "create a server app and a tempdir to upload files to"
        self.tempdir_obj = tempfile.TemporaryDirectory()
        self.tempdir = pathlib.Path(self.tempdir_obj.name)
        self.app = server.make_app(self.tempdir)

    def tearDown(self):
        self.tempdir_obj.cleanup()

    def test_upload_new_file(self):
        "upload data to a file that does not yet exist"
        with self.app.test_client() as client:
            filename = "myfile"
            data = random.randbytes(2**10)
            client.post(f"/upload/{filename}", data=data)

            self.assertEqual(data, (self.tempdir/filename).read_bytes())

    def test_upload_append(self):
        "upload data to the end of an existing file"
        with self.app.test_client() as client:
            filename = "myfile"
            data_1 = random.randbytes(2**10)
            data_2 = random.randbytes(2**10)

            (self.tempdir/filename).write_bytes(data_1)

            client.post(f"/upload/{filename}", data=data_2)

            self.assertEqual(data_1 + data_2, (self.tempdir/filename).read_bytes())

    def test_copy_new_file(self):
        "copy data into a new file"
        with self.app.test_client() as client:
            data = random.randbytes(2**10)
            (self.tempdir/"myfile-1").write_bytes(data)

            json = {
                    "file_name": "myfile-2",
                    "other_file": "myfile-1",
                    "offset": 0,
                    "length": 2**10
                    }
            client.post("/copy", json=json)

            self.assertEqual(data, (self.tempdir/"myfile-2").read_bytes())

    def test_copy_append(self):
        "copy data to the end of an existing file"
        with self.app.test_client() as client:
            file_1 = "myfile-1"
            file_2 = "myfile-2"
            data_1 = random.randbytes(2**10)
            data_2 = random.randbytes(2**10)

            # write data_1 to file_1 and data_2 to file_2
            (self.tempdir/file_1).write_bytes(data_1)
            (self.tempdir/file_2).write_bytes(data_2)

            # instruct the server to append 2**10 bytes from index 0 of file_1 onto the
            # end of file_2
            json = {
                    "file_name": file_2,
                    "other_file": file_1,
                    "offset": 0,
                    "length": 2**10
                    }
            client.post("/copy", json=json)

            # assert that the result of the operation above is data_2 + data_1
            self.assertEqual(data_2 + data_1, (self.tempdir/file_2).read_bytes())

    def test_copy_offset(self):
        "test that /copy interprets the offset and length parameters correctly"
        file_1 = "myfile-1"
        file_2 = "myfile-2"
        for _ in range(1000):
            # clean up any files that we may have created
            if (self.tempdir/file_1).exists():
                (self.tempdir/file_1).unlink()
            if (self.tempdir/file_2).exists():
                (self.tempdir/file_2).unlink()

            with self.app.test_client() as client:
                # generate some data and write it to file_1
                data = random.randbytes(2**10)
                (self.tempdir/file_1).write_bytes(data)

                # choose a random chunk of this data
                offset = random.randint(0, 2**10-1)
                length = random.randint(1, 2**10 - offset)

                # write the chunk into file_2
                json = {
                        "file_name": file_2,
                        "other_file": file_1,
                        "offset": offset,
                        "length": length
                        }
                client.post("/copy", json=json)

                # check that /copy and the corresponding slice of the data produced
                # the same result
                self.assertEqual((self.tempdir/file_2).read_bytes(), data[offset:offset+length])

    def test_random(self):
        "randomised test of /copy and /upload"
        filename = "myfile"
        # file_copy maintains a local copy of what we expect to be happening in the
        # upload directory
        file_copy = b""

        # create 10 random files
        files = {}
        for i in range(10):
            file = self.tempdir/f"file-{i:02d}"
            data = random.randbytes(2**10)
            file.write_bytes(data)
            files[file] = data

        with self.app.test_client() as client:
            for _ in range(1000):
                # in each iteration we either ...
                if random.random() < 0.5:
                    # ... upload some amount of random data to the file
                    data = random.randbytes(random.randint(1, 2**10))
                    client.post(f"/upload/{filename}", data=data)
                    file_copy += data
                else:
                    # ... pick one of the other files and a chunk of it
                    file_from = random.choice(tuple(files.keys()))
                    offset = random.randint(0, 2**10-1)
                    length = random.randint(1, 2**10 - offset)

                    # read the chunk out of the local file and add it to our local copy
                    with file_from.open("rb") as file:
                        file.seek(offset)
                        data = file.read(length)
                        file_copy += data

                    # remotely copy the chunk into the file
                    json = {
                            "file_name": filename,
                            "other_file": file_from.name,
                            "offset": offset,
                            "length": length
                            }
                    client.post("/copy", json=json)

        # assert that our copy of the file matches the one created by the server
        self.assertEqual(file_copy, (self.tempdir/filename).read_bytes())

class TestAll(unittest.TestCase):
    "test an upload using the real client and a real server"

    def setUp(self):
        "create a server app and source and destination directories"
        self.source_obj = tempfile.TemporaryDirectory()
        self.source = pathlib.Path(self.source_obj.name)
        self.dest_obj = tempfile.TemporaryDirectory()
        self.dest = pathlib.Path(self.dest_obj.name)

        self.app = server.make_app(self.dest)
        # instead of requests, use a test client to commincate with the server
        server_interface = self.app.test_client()
        self.client = client.Client("http://127.0.0.1:11000", self.source, server_interface)

    def tearDown(self):
        self.source_obj.cleanup()
        self.dest_obj.cleanup()

    def test_upload(self):
        "this only tests one file upload case, I will cross my fingers and hope that the other tests ensure that the other cases work"
        filename = "myfile"

        data = random.randbytes(2**10)
        (self.source/filename).write_bytes(data)

        self.client.check()

        self.assertEqual(data, (self.dest/filename).read_bytes())

if __name__ == "__main__":
    unittest.main()
