# sim/socket_listener.py
import socket
import json
import threading
from queue import Queue

def start_socket_listener(host: str, port: int, command_queue: Queue):
    def handle_client(conn, addr):
        print(f"[INFO] Connection from {addr}")
        buffer = ""
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                buffer += data.decode("utf-8")
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    try:
                        command = json.loads(line.strip())
                        command_queue.put(command)
                        print(f"[RECV] {command}")
                        conn.sendall(b"ACK: Command received\n")
                    except json.JSONDecodeError as e:
                        error_msg = f"ERROR: Invalid JSON - {str(e)}\n"
                        print(f"[ERROR] {error_msg.strip()}")
                        conn.sendall(error_msg.encode('utf-8'))
        except Exception as e:
            print(f"[ERROR] Unexpected error with {addr}: {str(e)}")
        finally:
            conn.close()
            print(f"[INFO] Disconnected {addr}")

    def server_thread():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen()
            print(f"[LISTENING] on {host}:{port}")
            while True:
                conn, addr = server.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

    thread = threading.Thread(target=server_thread, daemon=True)
    thread.start()
    return thread
