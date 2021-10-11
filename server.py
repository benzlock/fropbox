#!/usr/bin/env python3

import logging
import os
import pathlib
import sys

import flask

log = logging.getLogger("client")
log.addHandler(logging.StreamHandler(sys.stderr))
log.setLevel(logging.DEBUG)

def make_app(dest):
    "create a Flask app that will download files and write them to `dest`"

    app = flask.Flask("Fropbox server")

    @app.route("/upload/<file_name>", methods=["POST"])
    def upload(file_name):
        file = dest/file_name
        data = flask.request.data

        # create `file` if it does not exist
        if not file.exists():
            file.touch()
        # append the data we received to the end of `file`
        with file.open("ab") as f:
            f.write(data)

        return flask.make_response({}, 200)

    @app.route("/copy", methods=["POST"])
    def copy():
        file_name = flask.request.json["file_name"]
        other_file = flask.request.json["other_file"]
        offset = flask.request.json["offset"]
        length = flask.request.json["length"]

        src_file = dest/other_file
        dst_file = dest/file_name
        # create the destination file if it does not exist
        # the source file may not exist but we assume this will never happen
        if not dst_file.exists():
            dst_file.touch()
        with src_file.open("rb") as src, dst_file.open("ab") as dst:
            # read from src and write the data into dst
            src.seek(offset)
            chunk = src.read(length)
            dst.write(chunk)

        return flask.make_response({}, 200)

    return app

if __name__ == "__main__":
    dest = pathlib.Path("./dest")
    app = make_app(dest)
    app.run(port=11000, host="127.0.0.1")
