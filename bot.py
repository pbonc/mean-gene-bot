import socket
import os

server = 'irc.chat.twitch.tv'
port = 6667
nickname = os.getenv('TWITCH_BOT_USERNAME', 'MeanGeneBot')
token = os.getenv('TWITCH_OAUTH_TOKEN')  # e.g. 'oauth:xxxxx'
channel = os.getenv('TWITCH_CHANNEL', '#yourchannel')

sock = socket.socket()
sock.connect((server, port))
sock.send(f"PASS {token}\n".encode('utf-8'))
sock.send(f"NICK {nickname}\n".encode('utf-8'))
sock.send(f"JOIN {channel}\n".encode('utf-8'))

print(f"{nickname} has joined {channel}!")

while True:
    resp = sock.recv(2048).decode('utf-8')
    if resp.startswith('PING'):
        sock.send("PONG :tmi.twitch.tv\n".encode('utf-8'))
    elif "PRIVMSG" in resp:
        print(resp.strip())
