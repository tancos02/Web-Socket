import sys
import struct
from base64 import b64encode
from hashlib import sha1
import logging
from socket import error as SocketError
import errno
from socketserver import ThreadingMixIn, TCPServer, StreamRequestHandler

FIN    = 0x80
OPCODE = 0x0f
MASKED = 0x80
PAYLOAD_LEN = 0x7f
PAYLOAD_LEN_EXT16 = 0x7e
PAYLOAD_LEN_EXT64 = 0x7f

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT         = 0x1
OPCODE_BINARY       = 0x2
OPCODE_CLOSE_CONN   = 0x8
OPCODE_PING         = 0x9
OPCODE_PONG         = 0xA

# API untuk menjalankan server web socket
class API:
    def run_forever(self):
        try:
            self.serve_forever()
        except KeyboardInterrupt:
            self.server_close()
        except Exception as e:
            exit(1)

    def message_received(self, client, server, message):
        pass

    def binary_received(self, client, server, message):
        pass

    def continuation_received(self, client, server, message):
        pass

    def set_fn_message_received(self, fn):
        self.message_received = fn
    
    def set_fn_binary_received(self, fn):
        self.binary_received = fn
    
    def set_fn_continuation_received(self, fn):
        self.continuation_received = fn

    
# Kelas untuk web socket server yang dapat menghandle beberapa client
class WebsocketServer(ThreadingMixIn, TCPServer, API):
    # tempat queue untuk client
    clients = []

    def __init__(self, port, host='0.0.0.0'):
        TCPServer.__init__(self, (host, port), WebSocketHandler)
        self.port = self.socket.getsockname()[1]

    def _message_received_(self, handler, msg):
        self.message_received(self.handler_to_client(handler), self, msg)
    
    def _binary_received_(self, handler, msg):
        self.binary_received(self.handler_to_client(handler), self, msg)

    def _continuation_received_(self, handler, msg):
        self.continuation_received(self.handler_to_client(handler), self, msg)

    def _ping_received_(self, handler, msg):
        handler.send_pong(msg)

    def _pong_received_(self, handler, msg):
        pass

    def _new_client_(self, handler):
        client = {
            'handler': handler,
            'address': handler.client_address
        }
        self.clients.append(client)

    def _client_left_(self, handler):
        client = self.handler_to_client(handler)
        if client in self.clients:
            self.clients.remove(client)

    def _unicast_(self, to_client, msg):
        to_client['handler'].send_message(msg)
    
    def _binary_unicast_(self, to_client, msg):
        to_client['handler'].send_binary(msg)
    
    def handler_to_client(self, handler):
        for client in self.clients:
            if client['handler'] == handler:
                return client

# Kelas yang berisi fungsi-fungsi untuk membantu fungsionalitas pada web socket server
class WebSocketHandler(StreamRequestHandler):

    def __init__(self, socket, addr, server):
        self.server = server
        StreamRequestHandler.__init__(self, socket, addr, server)

    def setup(self):
        StreamRequestHandler.setup(self)
        self.keep_alive = True
        self.valid_client = False
        self.handshake_done = False

    def handle(self):
        while self.keep_alive:
            if not self.handshake_done:
                self.handshake()
            elif self.valid_client:
                self.read_next_data()

    def read_bytes(self, num):
        byte = self.rfile.read(num)
        return byte

    def read_next_data(self):
        # melakukan pembacaan bytes data dari client
        try:
            b1, b2 = self.read_bytes(2)
        except SocketError as e: 
            b1, b2 = 0, 0
        except ValueError as e:
            b1, b2 = 0, 0
        
        # mengambil nilai FIN, OPCODE dan PAYLOAD LENGTH
        fin    = b1 & FIN
        opcode = b1 & OPCODE
        masked = b2 & MASKED
        payload_length = b2 & PAYLOAD_LEN

        print(opcode)

        # jika client ingin close connection
        if opcode == OPCODE_CLOSE_CONN:
            print("Client disconected")
            self.keep_alive = 0
            return
        
        # handle berdasarkan tipe frame
        if opcode == OPCODE_BINARY:
            opcode_handler = self.server._binary_received_
        elif opcode == OPCODE_TEXT:
            opcode_handler = self.server._message_received_
        elif opcode == OPCODE_PING:
            opcode_handler = self.server._ping_received_
        elif opcode == OPCODE_PONG:
            opcode_handler = self.server._pong_received_
        else:
            # koneksi diputus
            self.keep_alive = 0
            return

        # handle payload yang lebih dari 125
        if payload_length == 126:
            payload_length = struct.unpack(">H", self.rfile.read(2))[0]
        elif payload_length == 127:
            payload_length = struct.unpack(">Q", self.rfile.read(8))[0]

        if masked:
            # encode payload text dengan mask
            masks = self.read_bytes(4)
            message_bytes = bytearray()
            for message_byte in self.read_bytes(payload_length):
                message_byte ^= masks[len(message_bytes) % 4]
                message_bytes.append(message_byte)
        else:
            message_bytes = bytearray()
            for message_byte in self.read_bytes(payload_length):
                message_bytes.append(message_byte)

        # handle untuk paket yang lebih dari 1 frame
        temp = b''
        if opcode == OPCODE_CONTINUATION:
            temp += message_bytes
            opcode_handler = self.server._continuation_received_
        
        if opcode == OPCODE_BINARY:
            opcode_handler(self, message_bytes)
        elif opcode == OPCODE_CONTINUATION and fin == 1:
            # hapus jika paket frame sudah dilengkap dan telah diproses server
            opcode_handler(self, temp)
            temp = b''
        elif opcode == OPCODE_PONG or opcode == OPCODE_PING or opcode == OPCODE_TEXT:
            opcode_handler(self, message_bytes.decode('utf8'))

    def send_message(self, message):
        self.send_text(message, OPCODE_TEXT)

    def send_binary(self, message):
        self.send_text(message, OPCODE_BINARY)

    def send_pong(self, message):
        self.send_text(message, OPCODE_PONG)

    def send_text(self, message, opcode):
        header  = bytearray()

        if opcode == OPCODE_BINARY: 
            payload = message
        elif opcode == OPCODE_TEXT or opcode == OPCODE_PONG:
            payload = message.encode('utf-8')
        payload_length = len(payload)

        # handle panjang payload
        if payload_length <= 125:
            header.append(FIN | opcode)
            header.append(payload_length)
        elif payload_length > 125 and payload_length <= 65536:
            header.append(FIN | opcode)
            header.append(PAYLOAD_LEN_EXT16)
            header.extend(struct.pack(">H", payload_length))
        elif payload_length < 18446744073709551616:
            header.append(FIN | opcode)
            header.append(PAYLOAD_LEN_EXT64)
            header.extend(struct.pack(">Q", payload_length))

        self.request.send(header + payload)
    
    def read_http_headers(self):
        headers = {}
        # baris pertama harus http GET
        http_get = self.rfile.readline().decode().strip()
        assert http_get.upper().startswith('GET')

        # setelahnya harus header
        while True:
            header = self.rfile.readline().decode().strip()
            if not header:
                break
            head, value = header.split(':', 1)
            headers[head.lower().strip()] = value.strip()
        return headers

    # Fungsi untuk melakukan menerima handshake dari client
    def handshake(self):
        headers = self.read_http_headers()

        try:
            assert headers['upgrade'].lower() == 'websocket'
        except AssertionError:
            self.keep_alive = False
            return

        try:
            key = headers['sec-websocket-key']
        except KeyError:
            self.keep_alive = False
            return

        response = self.make_handshake_response(key)

        self.handshake_done = self.request.send(response.encode())
        self.valid_client = True
        self.server._new_client_(self)

    @classmethod
    def make_handshake_response(cls, key):
        return \
          'HTTP/1.1 101 Switching Protocols\r\n'\
          'Upgrade: websocket\r\n'              \
          'Connection: Upgrade\r\n'             \
          'Sec-WebSocket-Accept: %s\r\n'        \
          '\r\n' % cls.make_key(key)

    @classmethod
    # Fungsi untuk membuat key response sesuai standar rfc
    def make_key(cls, key):
        GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        hash = sha1(key.encode() + GUID.encode())
        response_key = b64encode(hash.digest()).strip()
        return response_key.decode('ASCII')

    def finish(self):
        self.server._client_left_(self)