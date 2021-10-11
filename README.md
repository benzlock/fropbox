# Fropbox

## Specification

Build an application, consisting of two separate components, to synchronise a _destination_ folder from a _source_ folder over IP:

*1.1*: A simple command line client which takes one directory (the source) as argument, keeps monitoring changes in that directory, and uploads any change to its server

*1.2*: A simple server which takes one directory (the destination) as argument and receives any change from its client

*Bonus 1*: Optimise data transfer by avoiding uploading the same file multiple times.

*Bonus 2*: Optimise data transfer by avoiding uploading the same partial files (files sharing partially the same content) multiple times.

## Design

Most of the design of this application is informed by the requirements of Bonus 2. A natural approach to this would be to break each file into fixed-size chunks and instruct the server to copy any chunks that have already been uploaded. However, this will not catch any repeated sections that are smaller than one chunk, and repeated sections that do not line up to chunk boundaries will be ignored entirely.

```
file 1 ..... XXXXX XXX..
file 2 ....Y YYYYY Y....
file 3 ...YY YYYYY .....
file 4 ..... ..ZZZ ..ZZZ
```

The example above shows four files, each 15 bytes long, broken into 5-byte chunks. The dots represent random non-repeated data, and the letters represent sequences of repeated data.
 * In file 1, the repeated section in the last chunk will not be caught because the chunk also contains some bytes of non-repeated data.
 * Files 2 and 3 share a 7-byte sequence but this will not be caught because the sequences are offset differently relative to the chunk boundaries, so the two files do not actually contain any duplicate chunks.

Instead, we search for repeated sections at any point within the file. This can be done using Python's built-in [`difflib.SequenceMatcher.get_matching_blocks`](https://docs.python.org/3/library/difflib.html?highlight=difflib#difflib.SequenceMatcher.get_matching_blocks), which returns lists of non-overlapping matching subsequences taken from its inputs. When uploading some file F, `get_matching_blocks` is called once for every file that has already been uploaded, to find common sequences between the uploaded file and F.

This makes the file transfer process much slower than a chunk-based approach (especially for large files and large numbers of files), but it should be more efficient, as the repeated sections in real files are unlikely to align to chunk boundaries. There are two main disadvantages to using `get_matching_blocks`:
 * Repeated sequences within the same file, as shown in file 4, will not be caught unless the sequence also appears in another file. This is because calling `get_matching_block` with the same file for both inputs only returns one full-length match.
 * The algorithm used by `get_matching_blocks` identifies blocks in an unspecified order, and since the blocks must be non-overlapping, some long blocks will not be recognised because a shorter block is recognised inside them first.

## Implementation

Data is transmitted from the client to the server over HTTP.

### Server

The server provides a web API with two endpoints:
 * `/upload/<file_name>` appends data from the body of the request to a file called `file_name`. If the file does not exist, it is created.
 * `/copy` takes four arguments, provided in its body and encoded in JSON: `file_name`, `other_file`, `offset`, and `length`. When called, this method reads `length` bytes from `other_file` starting at `offset` and writes them to `file_name`. As before, if `file_name` does not exist, it is created.

The web server is implemented using [Flask](https://flask.palletsprojects.com/en/2.0.x/).

### Client

The client maintains a list of files that have already been uploaded. At some interval (0.1 s by default) it checks for new files in its designated source directory and uploads them.

The first step in the process of uploading some file F is to identify the sequences in F that are present in other files that have already been uploaded. Sequences that are especially short (less than 32 bytes by default) are filtered out to avoid a large number of 1-byte copy instructions. The matched sequences are then ordered by size, and sequences are chosen for use in descending order of size. Any sequences that overlap with a sequence that has already been chosen are discarded. The final list of sequences will be sent to the `/copy` endpoint.

The gaps in the file that are not covered by repeated sequences will be filled in using the `/upload` endpoint. The final sequence of API calls is represented by a sequence of chunks, where each chunk contains
 * `length`, the length of that chunk in bytes,
 * `start`, the position in F where this chunk starts,
 * `other_file`, the file to read from if this is a repeated chunk; if not, this is null and the client reads from F, and
 * `other_file_start`, the position in `other_file` where this chunk starts. If `other_file` is null, this is null as well.

Communication with the server is handled by [Requests](https://docs.python-requests.org/en/latest/).

## Usage

To ensure that it works on all platforms, this project was designed to be used with Docker. The project can be built and start by running

```
$ docker build . -t fropbox ; docker run fropbox
```

The test suite can be run as follows:

```
$ python3 -m unittest
```

## Extensions

There are a number of issues with this implementation of Fropbox, as well as features that could be added in the future.

### Issues

 * Many corner and edge cases are not handled, including but not limited to file names that are not URL-safe and copying from files with a negative start index or length.
 * The project currently has no security measures, so it would possible for an untrusted third party write junk data to the server. This could be fixed by requiring users to authentica themselves with a key for each file transfer.
 * If an uploaded file is delete from the source or desination directory, Fropbox will still try to read from it. There are a number of ways to plug this hole including having the client check the list of available files before each upload, and querying the server for a list of files available in the destination directory before each upload.

 * what happens when a chunk ends one byte before the end of a file?

### Additional features

Below are some proposals for features that could be added to improve Fropbox.

 * Synchronise changes to files instead of only uploading new ones. `rsync` is probably better suited for doing this.
 * Memory efficiency - several parts of the code require arbitrarily large parts of files to be read into memory. This becomes inefficient for large files, and could easily be avoided by reading files in small fixed-size chunks. A custom implementation would have to be used instead of `difflib.SequenceMatcher.get_matching_blocks`.
 * As mentioned above, the algorithm used by `get_matching_blocks` does not identify the most optimial (i.e. longest) repeated subsequences, nor does it identify subsequences repeated in one file. The latter problem could be solved by using an algorithm based on [suffix trees](https://stackoverflow.com/questions/37499968).
 * Similar to the previous feature, Fropbox's bandwidth could be reduced by compressing data before transmitting it.
 * Allow multiple file uploads at the same time. No part of the code prevents this from happening, but it has not been tested.
