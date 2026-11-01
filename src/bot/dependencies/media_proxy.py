import atexit
import base64
import ipaddress
import secrets
import selectors
import socket
import socketserver
import threading
import time
from typing import Any, cast
from urllib.parse import urlsplit

_TRUSTED_HOSTS = frozenset(
    {
        "youtube.com",
        "youtube-nocookie.com",
        "youtu.be",
        "googlevideo.com",
        "ytimg.com",
        "ggpht.com",
        "googleusercontent.com",
        "youtubei.googleapis.com",
    }
)
_MAX_HEADER_BYTES = 16_384

class MediaProxyScope:
    def __init__(self, token: str, proxy_url: str) -> None:
        self.token = token
        self.proxy_url = proxy_url
        self._lock = threading.Lock()
        self._sockets: set[socket.socket] = set()
        self._cancelled = False

    def register(self, connection: socket.socket) -> bool:
        with self._lock:
            if self._cancelled:
                return False
            self._sockets.add(connection)
            return True

    def unregister(self, connection: socket.socket) -> None:
        with self._lock:
            self._sockets.discard(connection)

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            sockets = tuple(self._sockets)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self) -> None:
        self.cancel()
        with _scope_lock:
            _scopes.pop(self.token, None)


_scope_lock = threading.Lock()
_scopes: dict[str, MediaProxyScope] = {}



def is_trusted_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "youtubei.googleapis.com":
        return True
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in _TRUSTED_HOSTS - {"youtubei.googleapis.com"}
    )


def validate_media_url(url: str, *, resolve: bool = True) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise ValueError("Media URL contains control characters")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only HTTPS YouTube media URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials are not allowed in media URLs")
    if parsed.port not in (None, 443):
        raise ValueError("Non-standard media URL ports are not allowed")
    if not is_trusted_host(parsed.hostname):
        raise ValueError("Media URL host is not trusted")
    if resolve:
        resolve_public_addresses(parsed.hostname)
    return url


def resolve_public_addresses(host: str) -> list[tuple[int, tuple[str, int]]]:
    addresses = socket.getaddrinfo(
        host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    vetted: list[tuple[int, tuple[str, int]]] = []
    for family, _, _, _, sockaddr in addresses:
        address = ipaddress.ip_address(sockaddr[0])
        if not address.is_global:
            raise ValueError("Media host resolved to a non-public address")
        vetted.append((family, (str(address), 443)))
    if not vetted:
        raise ValueError("Media host did not resolve")
    return vetted


class _ConnectHandler(socketserver.BaseRequestHandler):
    def finish(self) -> None:
        scope = getattr(self, "_scope", None)
        if scope is not None:
            scope.unregister(self.request)
            upstream = getattr(self, "_upstream", None)
            if upstream is not None:
                scope.unregister(upstream)
        super().finish()

    def handle(self) -> None:
        deadline = time.monotonic() + 10
        request = b""
        while b"\r\n\r\n" not in request and len(request) <= _MAX_HEADER_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.request.settimeout(remaining)
            chunk = self.request.recv(4096)
            if not chunk:
                return
            request += chunk
        if b"\r\n\r\n" not in request:
            self.request.sendall(
                b"HTTP/1.1 431 Request Header Fields Too Large\r\n"
                b"Connection: close\r\n\r\n"
            )
            return
        try:
            first_line = request.split(b"\r\n", 1)[0].decode("ascii")
            method, authority, version = first_line.split(" ")
            host, separator, port = authority.rpartition(":")
            if method != "CONNECT" or version not in {"HTTP/1.0", "HTTP/1.1"}:
                raise ValueError("Only HTTP CONNECT is supported")
            if not separator or port != "443" or not is_trusted_host(host):
                raise ValueError("CONNECT destination is not trusted")
            authorization = next(
                (
                    line.split(":", 1)[1].strip()
                    for line in request.decode("iso-8859-1").splitlines()[1:]
                    if line.lower().startswith("proxy-authorization:")
                ),
                "",
            )
            scheme, _, encoded = authorization.partition(" ")
            if scheme.lower() != "basic":
                raise ValueError("Missing proxy authorization")
            credentials = base64.b64decode(encoded, validate=True).decode()
            token, separator, _ = credentials.partition(":")
            if not separator:
                raise ValueError("Invalid proxy authorization")
            with _scope_lock:
                scope = _scopes.get(token)
            if scope is None or not scope.register(self.request):
                raise ValueError("Cancelled proxy scope")
            self._scope = scope
            addresses = resolve_public_addresses(host)
        except (UnicodeDecodeError, ValueError, OSError):
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            return

        upstream: socket.socket | None = None
        for family, address in addresses:
            candidate = socket.socket(family, socket.SOCK_STREAM)
            if not scope.register(candidate):
                candidate.close()
                break
            candidate.settimeout(10)
            try:
                candidate.connect(address)
            except OSError:
                scope.unregister(candidate)
                candidate.close()
                continue
            upstream = candidate
            break
        if upstream is None:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            return
        self._upstream = upstream

        _, _, initial_upstream_data = request.partition(b"\r\n\r\n")
        with upstream:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.request.setblocking(False)
            upstream.setblocking(False)
            sockets = (self.request, upstream)
            peer = {self.request: upstream, upstream: self.request}
            pending = {self.request: bytearray(), upstream: bytearray(initial_upstream_data)}
            reading = {self.request: True, upstream: True}
            selector = selectors.DefaultSelector()
            with selector:
                selector.register(self.request, selectors.EVENT_READ)
                selector.register(upstream, selectors.EVENT_READ)
                while any(reading.values()) or any(pending.values()):
                    for sock in sockets:
                        events = 0
                        if reading[sock] and len(pending[peer[sock]]) < 262_144:
                            events |= selectors.EVENT_READ
                        if pending[sock]:
                            events |= selectors.EVENT_WRITE
                        try:
                            if events:
                                selector.modify(sock, events)
                            else:
                                selector.unregister(sock)
                        except KeyError:
                            if events:
                                selector.register(sock, events)
                    for key, mask in selector.select():
                        sock = cast(socket.socket, key.fileobj)
                        if mask & selectors.EVENT_READ:
                            try:
                                data = sock.recv(65_536)
                            except (BrokenPipeError, ConnectionResetError):
                                return
                            except BlockingIOError:
                                data = None
                            if data:
                                pending[peer[sock]].extend(data)
                            elif data == b"":
                                reading[sock] = False
                                destination = peer[sock]
                                if not pending[destination]:
                                    try:
                                        destination.shutdown(socket.SHUT_WR)
                                    except OSError:
                                        pass
                        if mask & selectors.EVENT_WRITE and pending[sock]:
                            try:
                                sent = sock.send(pending[sock])
                            except (BrokenPipeError, ConnectionResetError):
                                return
                            except BlockingIOError:
                                sent = 0
                            del pending[sock][:sent]
                            source = peer[sock]
                            if not pending[sock] and not reading[source]:
                                try:
                                    sock.shutdown(socket.SHUT_WR)
                                except OSError:
                                    pass


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    _admission = threading.BoundedSemaphore(64)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._admission.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._admission.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._admission.release()


_lock = threading.Lock()
_server: _ProxyServer | None = None
_thread: threading.Thread | None = None


def media_proxy_url() -> str:
    global _server, _thread
    with _lock:
        if _server is None:
            _server = _ProxyServer(("127.0.0.1", 0), _ConnectHandler)
            _thread = threading.Thread(
                target=_server.serve_forever, name="media-egress-proxy", daemon=True
            )
            _thread.start()
        port = _server.server_address[1]
    return f"http://127.0.0.1:{port}"

def create_media_proxy_scope() -> MediaProxyScope:
    base_url = media_proxy_url()
    token = secrets.token_urlsafe(24)
    proxy_url = base_url.replace("://", f"://{token}:x@", 1)
    scope = MediaProxyScope(token, proxy_url)
    with _scope_lock:
        _scopes[token] = scope
    return scope


def _shutdown() -> None:
    if _server is not None:
        _server.shutdown()
        _server.server_close()


atexit.register(_shutdown)
