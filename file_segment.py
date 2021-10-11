#!/usr/bin/env python3

# https://helloacm.com/algorithm-to-remove-a-interval-from-segments/

class FileSegment:
    """
    A FileSegment object represents a file as a list of bytes. This is done using an
    internal list of segments, which contains pairs of the form (start, stop). A file
    with length 10 will be represented by segment list [(0, 9)]. We can check if a
    segment is contained in our segment list:

        (2, 7) in [(0, 9)]
        (2, 7) not in [(0, 3), (6, 9)]

    Segment endpoints are inclusive, so (0, 9) is in [(0, 9)].

    Segments can be removed from the list:

        [(0, 9)].remove(4, 5) -> [(0, 3), (6, 9)]
    """

    def __init__(self, length):
        self.segments = [(0, length - 1)]

    def remove(self, start, stop):
        "remove some segment R (start, stop) from the list of segments"

        new_segments = []
        for seg_start, seg_stop in self.segments:
            if seg_start < start:
                new_segments += [(seg_start, min(start - 1, seg_stop))]
            if seg_stop > stop:
                new_segments += [(max(stop + 1, seg_start), seg_stop)]

        self.segments = new_segments

    def __contains__(self, R):
        "return True if segment R (start, stop) is fully contained within one of the existing segments"
        start, stop = R
        for seg_start, seg_stop in self.segments:
            if start >= seg_start and stop <= seg_stop:
                return True
        return False
