from websocket import *
import hashlib

# Dipanggil ketika client mengirim data teks ke server
def message_received(client, server, message):
	if '!echo' in message:
		server._unicast_(client, message[6:])
	elif '!submission' in message:
		data_file = b''
		with open('Bariancrot.zip', "rb") as f:
			data_file = f.read()
		server._binary_unicast_(client, data_file)

# Dipanggil ketika client mengirim data continuation ke server
def continuation_received(client, server, message):
	print("masuk continuation")
	try:
		message = message.decode('utf-8')
		if '!echo' in message:
			server._unicast_(client, message[6:])
		elif '!submission' in message:
			data_file = b''
			with open('Bariancrot.zip', "rb") as f:
				data_file = f.read()
			server._binary_unicast_(client, data_file)
		else:
			data_file = b''
			with open('Bariancrot.zip', "rb") as f:
				data_file = f.read()
				data_hash = hashlib.md5(data_file).hexdigest()

				compared_hash = message.lower()
				if compared_hash == data_hash:
					server._unicast_(client, '1')
				else:
					server._unicast_(client, '0')
	except(UnicodeDecodeError) as err:
		print("masuk continuation error")
		with open('Bariancrot.zip', "rb") as f:
			data_file = f.read()
			data_hash = hashlib.md5(data_file).hexdigest()

			compared_hash = message.lower()
			if compared_hash == data_hash:
				server._unicast_(client, '1')
			else:
				server._unicast_(client, '0')

# Dipanggil ketika data binary sudah terkumpul semua
def binary_received(client, server, message):
	print("masuk binary")
	data_binary = b''
	data_binary += message
	# Menghasilkan md5 dari hasil data client yang sudah utuh
	compared_hash = hashlib.md5(message).hexdigest().lower()

	with open('Bariancrot.zip', 'rb') as f:
		data_file = f.read()
		data_hash = hashlib.md5(data_file).hexdigest().lower()

	if compared_hash == data_hash:
		server._unicast_(client, '1')
	else:
		server._unicast_(client, '0')

if __name__ == "__main__":
	PORT=6969
	server = WebsocketServer(PORT)
	server.set_fn_message_received(message_received)
	server.set_fn_continuation_received(continuation_received)
	server.set_fn_binary_received(binary_received)
	server.run_forever()