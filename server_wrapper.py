#!/usr/bin/env python3

import requests

class Server:

    def __init__(self, hostname, server_interface):
        "server_interface must be `requests` or a Flask test_client"
        self.hostname = hostname
        self.server_interface = server_interface

    def upload(self, data, file):
        self.server_interface.post(f"{self.hostname}/upload/{file.name}", data=data)

    def copy(self, file, other_file, offset, length):
        data = {
                "file_name": file.name,
                "other_file": other_file.name,
                "offset": offset,
                "length": length
                }
        self.server_interface.post(f"{self.hostname}/copy", json=data)
