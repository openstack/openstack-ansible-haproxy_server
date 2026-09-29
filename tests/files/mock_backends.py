#!/usr/bin/env python3
# Copyright 2026, Cleura AB.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Lightweight configurable mock backend listener for HAProxy Molecule functional tests.
Allows configuring arbitrary listener ports and protocols via command-line arguments:
  --http-ports PORT [PORT ...]
  --https-ports PORT [PORT ...]
  --tcp-ports PORT [PORT ...]
  --app-ports PORT:NAME [PORT:NAME ...]
"""

import argparse
import http.server
import json
import os
import socketserver
import ssl
import sys
import threading

DEFAULT_HOST = "127.0.0.1"


class HTTPMockHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        headers_dict = {k: v for k, v in self.headers.items()}
        data = {
            "status": "OK",
            "path": self.path,
            "headers": headers_dict,
        }
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_POST(self):
        self.do_GET()

    def log_message(self, format, *args):
        # Suppress noisy standard logging
        pass


def create_app_handler(app_name):
    class CustomAppHandler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "app": app_name,
                "status": "OK",
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    return CustomAppHandler


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class TCPBannerHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.sendall(b"OK-TCP\n")
            self.request.settimeout(1.0)
            self.request.recv(1024)
        except Exception:
            pass


def start_http_server(host, port, handler_class, ssl_cert=None, ssl_key=None):
    server = ThreadedTCPServer((host, port), handler_class)
    if ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=ssl_cert, keyfile=ssl_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


def start_tcp_server(host, port):
    server = ThreadedTCPServer((host, port), TCPBannerHandler)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Configurable mock backend listener")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Host address to bind (default: %(default)s)",
    )
    parser.add_argument(
        "--cert",
        default="/etc/ssl/certs/mock_backend.crt",
        help="Path to SSL certificate for HTTPS mock",
    )
    parser.add_argument(
        "--key",
        default="/etc/ssl/private/mock_backend.key",
        help="Path to SSL private key for HTTPS mock",
    )
    parser.add_argument(
        "--http-ports",
        nargs="*",
        type=int,
        default=[],
        help="List of HTTP listener ports",
    )
    parser.add_argument(
        "--https-ports",
        nargs="*",
        type=int,
        default=[],
        help="List of HTTPS listener ports",
    )
    parser.add_argument(
        "--tcp-ports",
        nargs="*",
        type=int,
        default=[],
        help="List of L4 TCP listener ports",
    )
    parser.add_argument(
        "--app-ports",
        nargs="*",
        type=str,
        default=[],
        help="List of named application listener ports in format PORT:NAME (e.g. 10081:APP1)",
    )
    args = parser.parse_args()

    http_ports = set(args.http_ports)
    https_ports = set(args.https_ports)
    tcp_ports = set(args.tcp_ports)

    threads = []

    # HTTP listeners
    for port in sorted(http_ports):
        threads.append(
            threading.Thread(
                target=start_http_server,
                args=(args.host, port, HTTPMockHandler),
                daemon=True,
            )
        )

    # TCP listeners
    for port in sorted(tcp_ports):
        threads.append(
            threading.Thread(
                target=start_tcp_server,
                args=(args.host, port),
                daemon=True,
            )
        )

    # Named app listeners
    for entry in args.app_ports:
        if ":" in entry:
            p_str, app_name = entry.split(":", 1)
        else:
            p_str, app_name = entry, f"APP-{entry}"
        port = int(p_str)
        handler = create_app_handler(app_name)
        threads.append(
            threading.Thread(
                target=start_http_server,
                args=(args.host, port, handler),
                daemon=True,
            )
        )

    # HTTPS listeners
    for port in sorted(https_ports):
        if not (os.path.exists(args.cert) and os.path.exists(args.key)):
            print(
                f"Warning: SSL certificate or key not found ({args.cert}, {args.key}), skipping HTTPS on {port}",
                file=sys.stderr,
            )
            continue
        threads.append(
            threading.Thread(
                target=start_http_server,
                args=(
                    args.host,
                    port,
                    HTTPMockHandler,
                    args.cert,
                    args.key,
                ),
                daemon=True,
            )
        )

    if not threads:
        print("No listeners configured to start.", file=sys.stderr)
        return

    for t in threads:
        t.start()

    # Block indefinitely
    threading.Event().wait()


if __name__ == "__main__":
    main()
