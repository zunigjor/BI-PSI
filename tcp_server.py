# Jorge Zuniga (zunigjor)
# PSI homework
# TCP/IP server
########################################################################################################################
# imports
import sys
import os
import threading
import socketserver
import socket
import re
from typing import Any


########################################################################################################################
# for terminal colored text usage: print(f"{Colors.OK_BLUE}colored text{Colors.END_C}")
class Colors:
    OK_BLUE = '\033[94m'
    OK_CYAN = '\033[96m'
    OK_GREEN = '\033[92m'
    WARNING_YELLOW = '\033[93m'
    FAIL_RED = '\033[91m'
    END_C = '\033[0m'


########################################################################################################################
# constants
# address and port
HOST = socket.gethostbyname(socket.gethostname())
PORT = 9000
# Messages suffix
SUFFIX = b'\x07\x08'
# timeouts in seconds
TIMEOUT = 1.0
TIMEOUT_RECHARGING = 5.0
# directions on the x, y axis.
DIRECTIONS = {
    "UP":       (0, 1),
    "DOWN":     (0, -1),
    "LEFT":     (-1, 0),
    "RIGHT":    (1, 0),
    "UNKNOWN":   (0, 0)
}
DIRECTIONS_PRINT = {
    (0, 1):     "UP",
    (0, -1):    "DOWN",
    (-1, 0):    "LEFT",
    (1, 0):     "RIGHT",
    (0, 0):     "UNKNOWN"
}
DIRECTIONS_TURN_RIGHT = {
    DIRECTIONS["UP"]:       DIRECTIONS["RIGHT"],
    DIRECTIONS["RIGHT"]:    DIRECTIONS["DOWN"],
    DIRECTIONS["DOWN"]:     DIRECTIONS["LEFT"],
    DIRECTIONS["LEFT"]:     DIRECTIONS["UP"],
    DIRECTIONS["UNKNOWN"]: DIRECTIONS["UNKNOWN"]
}
DIRECTIONS_TURN_LEFT = {
    DIRECTIONS["UP"]:       DIRECTIONS["LEFT"],
    DIRECTIONS["LEFT"]:     DIRECTIONS["DOWN"],
    DIRECTIONS["DOWN"]:     DIRECTIONS["RIGHT"],
    DIRECTIONS["RIGHT"]:    DIRECTIONS["UP"],
    DIRECTIONS["UNKNOWN"]: DIRECTIONS["UNKNOWN"]
}
# Key ID pairs. FORMAT =  KEY_ID : (SERVER_KEY, CLIENT_KEY)
SERVER_CLIENT_KEYS = {
    0: (23019, 32037),
    1: (32037, 29295),
    2: (18789, 13603),
    3: (16443, 29533),
    4: (18189, 21952)
}
# Client messages and their lengths
CLIENT_MESSAGES = {
    "CLIENT_RECHARGING": b"RECHARGING" + SUFFIX,
    "CLIENT_FULL_POWER": b"FULL POWER" + SUFFIX
}
CLIENT_MESSAGES_MAX_LEN = {
    "CLIENT_USERNAME":      20,
    "CLIENT_KEY_ID":        5,
    "CLIENT_CONFIRMATION":  7,
    "CLIENT_OK":            12,
    "CLIENT_RECHARGING":    12,
    "CLIENT_FULL_POWER":    12,
    "CLIENT_MESSAGE":       100
}
SERVER_MESSAGES = {
    "SERVER_MOVE":                      b"102 MOVE" + SUFFIX,
    "SERVER_TURN_LEFT":                 b"103 TURN LEFT" + SUFFIX,
    "SERVER_TURN_RIGHT	":              b"104 TURN RIGHT" + SUFFIX,
    "SERVER_PICK_UP":                   b"105 GET MESSAGE" + SUFFIX,
    "SERVER_LOGOUT":                    b"106 LOGOUT" + SUFFIX,
    "SERVER_KEY_REQUEST":               b"107 KEY REQUEST" + SUFFIX,
    "SERVER_OK":                        b"200 OK" + SUFFIX,
    "SERVER_LOGIN_FAILED":              b"300 LOGIN FAILED" + SUFFIX,
    "SERVER_SYNTAX_ERROR":              b"301 SYNTAX ERROR" + SUFFIX,
    "SERVER_LOGIC_ERROR":               b"302 LOGIC ERROR" + SUFFIX,
    "SERVER_KEY_OUT_OF_RANGE_ERROR":    b"303 KEY OUT OF RANGE" + SUFFIX
}


# SERVER_CONFIRMATION_MESSAGE
def get_server_confirmation_message_from_int(confirmation_number: int) -> bytes:
    """Generates a confirmation message from an int. Does not check for int size!"""
    return str(confirmation_number).encode() + SUFFIX


########################################################################################################################
# Custom exceptions
class ServerLoginFailed(Exception):
    def __init__(self, message):
        self.message = message


class ServerSyntaxError(Exception):
    def __init__(self, message):
        self.message = message


class ServerLogicError(Exception):
    def __init__(self, message):
        self.message = message


class ServerKeyOutOfRangeError(Exception):
    def __init__(self, message):
        self.message = message


########################################################################################################################
# Point in space class
class Point:
    def __init__(self):
        self.x = None
        self.y = None

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __str__(self):
        return f"({self.x}, {self.y})"


# Client robot class
class ClientRobot:
    def __init__(self):
        self.username: str = ""
        self.keyID: int = -1
        self.recharging: bool = False
        self.coords: Point = Point()
        self.coords_last: Point = Point()
        self.direction: tuple = (0, 0)
        self.obstacle: str = ""


########################################################################################################################
# Functions
def suffix_check(data: bytes):
    """Checks if suffix is okay"""
    if data[-2:] != SUFFIX:
        raise ServerSyntaxError("Bad message syntax.")


def key_id_check(data: bytes):
    """Checks if key ID is okay"""
    key_id_without_suffix = data[:-2].decode()
    if not key_id_without_suffix.isnumeric():
        raise ServerSyntaxError("Key is not a number.")
    if int(key_id_without_suffix) < 0 or int(key_id_without_suffix) > 4:
        raise ServerKeyOutOfRangeError("Server key out of range.")


def get_coords_from_message(message: bytes):
    message_str = message.decode()
    suffix_str = SUFFIX.decode()
    regex_str = "OK [-0-9]+ [-0-9]+" + suffix_str
    if not re.match(regex_str, message_str):
        raise ServerSyntaxError("Bad CLIENT_OK format")
    return int(message[:-2][3:].decode().split(" ")[0]), int(message[:-2][3:].decode().split(" ")[1])


def get_direction(new: Point, old: Point):
    return new.x - old.x, new.y - old.y


########################################################################################################################
# socketserver setup for threaded TCP server
# Handling of TCP clients
class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
    request: socket.socket

    # redefine init to add robot and incoming data buffer ##############################################################
    def __init__(self, request: Any, client_address: Any, server: socketserver.BaseServer):
        self.robot = ClientRobot()
        self.data_buffer = b''
        super().__init__(request, client_address, server)

    # read a message, messages end in \a\b #############################################################################
    def get_message(self, client_message_len: int):
        """Returns a single message received from the client. Messages end in \a\b and have their max length
        specified in the CLIENT_MESSAGES_MAX_LEN dictionary"""
        message = b''
        max_message_len = max(client_message_len, CLIENT_MESSAGES_MAX_LEN["CLIENT_RECHARGING"])
        while True:
            if len(self.data_buffer) == 0:
                self.data_buffer += self.request.recv(1024)
            else:
                message += self.data_buffer[:1]
                self.data_buffer = self.data_buffer[1:]
                if message[-2:] == SUFFIX:
                    break
                if len(message) == max_message_len:
                    break
        suffix_check(message)
        self.request.settimeout(TIMEOUT)
        # print(f"Received {message} from client {threading.current_thread().name[7:]}")
        if self.robot.recharging is False and message == CLIENT_MESSAGES["CLIENT_FULL_POWER"]:
            raise ServerLogicError(f"{Colors.FAIL_RED}CLIENT_FULL_POWER without prior CLIENT_RECHARGING{Colors.END_C}")
        if message == CLIENT_MESSAGES["CLIENT_RECHARGING"]:
            self.request.settimeout(TIMEOUT_RECHARGING)
            self.robot.recharging = True
            message = self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_FULL_POWER"])
            if message != CLIENT_MESSAGES["CLIENT_FULL_POWER"]:
                raise ServerLogicError(f"{Colors.FAIL_RED}Server did not send CLIENT_FULL_POWER after CLIENT_RECHARGING{Colors.END_C}")
            self.request.settimeout(TIMEOUT)
            self.robot.recharging = False
            message = self.get_message(client_message_len)
        return message

    # authentication methods ###########################################################################################
    def calculate_server_confirmation_key(self):
        """Calculates server identification number"""
        server_key, client_key = SERVER_CLIENT_KEYS[self.robot.keyID]
        username_to_ascii_value = [ord(c) for c in self.robot.username]
        result = ((sum(username_to_ascii_value) * 1000) % 65536 + server_key) % 65536
        return result

    def client_confirmation_check(self, message: bytes):
        """Checks whether the client sent a valid identification number"""
        message_no_suffix_str = message[:-2].decode()
        if not message_no_suffix_str.isnumeric():
            raise ServerSyntaxError("Client confirmation is not a number")
        client_robot_confirmation = int(message_no_suffix_str)
        if client_robot_confirmation > 99999:
            raise ServerSyntaxError("Client confirmation number has too many digits")
        server_key, client_key = SERVER_CLIENT_KEYS[self.robot.keyID]
        username_to_ascii_value = [ord(c) for c in self.robot.username]
        result = ((sum(username_to_ascii_value) * 1000) % 65536 + client_key) % 65536
        if result != client_robot_confirmation:
            raise ServerLoginFailed("Client confirmation failed")

    def authentication(self):
        """Handles client-server authentication"""
        message: bytes
        # RECEIVE USERNAME #############################################################################################
        message = self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_USERNAME"])
        self.robot.username = message[:-2].decode()
        # SEND KEY REQUEST #############################################################################################
        self.request.sendall(SERVER_MESSAGES["SERVER_KEY_REQUEST"])
        # RECEIVE KEY ID ###############################################################################################
        message = self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_KEY_ID"])
        key_id_check(message)
        self.robot.keyID = int(message[:-2])
        server_confirmation = get_server_confirmation_message_from_int(self.calculate_server_confirmation_key())
        # SEND SERVER CONFIRMATION #####################################################################################
        self.request.sendall(server_confirmation)
        # RECEIVE CLIENT CONFIRMATION ##################################################################################
        message = self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_CONFIRMATION"])
        self.client_confirmation_check(message)
        # SEND SERVER OK ###############################################################################################
        self.request.sendall(SERVER_MESSAGES["SERVER_OK"])
        return

    # navigation methods ###############################################################################################
    def check_goal_reached(self):
        if self.robot.coords.x == 0 and self.robot.coords.y == 0:
            self.request.sendall(SERVER_MESSAGES["SERVER_PICK_UP"])
            print(f"Client {threading.current_thread().name[7:]}: PICKUP AT {self.robot.coords}, {DIRECTIONS_PRINT[self.robot.direction]}")
            message = self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_MESSAGE"])
            print(f"{Colors.OK_GREEN}Client {threading.current_thread().name[7:]}: {message}{Colors.END_C}")
            self.request.sendall(SERVER_MESSAGES["SERVER_LOGOUT"])
            sys.exit(200)

    def robot_turn_left(self):
        print(f"Client {threading.current_thread().name[7:]}: TURN LEFT")
        self.request.sendall(SERVER_MESSAGES["SERVER_TURN_LEFT"])
        self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_OK"])
        self.robot.direction = DIRECTIONS_TURN_LEFT[self.robot.direction]
        print(f"Client {threading.current_thread().name[7:]}: {self.robot.coords}, {DIRECTIONS_PRINT[self.robot.direction]}")

    def robot_turn_right(self):
        print(f"Client {threading.current_thread().name[7:]}: TURN RIGHT")
        self.request.sendall(SERVER_MESSAGES["SERVER_TURN_RIGHT	"])
        self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_OK"])
        self.robot.direction = DIRECTIONS_TURN_RIGHT[self.robot.direction]
        print(f"Client {threading.current_thread().name[7:]}: {self.robot.coords}, {DIRECTIONS_PRINT[self.robot.direction]}")

    def robot_move(self):
        print(f"Client {threading.current_thread().name[7:]}: MOVE")
        self.request.sendall(SERVER_MESSAGES["SERVER_MOVE"])
        message = self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_OK"])
        self.robot.coords_last.x, self.robot.coords_last.y = self.robot.coords.x, self.robot.coords.y
        self.robot.coords.x, self.robot.coords.y = get_coords_from_message(message)
        self.check_goal_reached()
        print(f"Client {threading.current_thread().name[7:]}: {self.robot.coords}, {DIRECTIONS_PRINT[self.robot.direction]}")

    def get_initial_direction_position(self):
        while self.robot.direction == (0, 0):
            print(f"Client {threading.current_thread().name[7:]}: MOVE")
            self.request.sendall(SERVER_MESSAGES["SERVER_MOVE"])
            message = self.get_message(CLIENT_MESSAGES_MAX_LEN["CLIENT_OK"])
            self.robot.coords.x, self.robot.coords.y = get_coords_from_message(message)
            print(f"Client {threading.current_thread().name[7:]}: {self.robot.coords}, {DIRECTIONS_PRINT[self.robot.direction]}")
            self.check_goal_reached()
            self.robot_move()
            self.robot.direction = get_direction(self.robot.coords, self.robot.coords_last)
            if self.robot.direction == (0, 0):
                self.robot_turn_left()

    def robot_evade(self):
        self.robot_turn_right()
        self.robot_move()
        self.robot_turn_left()

    def navigation(self):
        """Handles navigation of the client robot towards the goal."""
        # Get initial coords and direction
        self.get_initial_direction_position()
        print(f"Client {threading.current_thread().name[7:]} {self.robot.coords}, {DIRECTIONS_PRINT[self.robot.direction]}")
        while True:
            # movement directions scheme
            ##################################
            #  TOP LEFT    | TOP RIGHT       #
            #         >    v     v           #
            #  ------->----|-----<------     #
            #         ^    ^     <           #
            #  BOTTOM LEFT | BOTTOM RIGHT    #
            ##################################
            # figure out in which quadrant the robot is
            if self.robot.coords.x >= 0 and self.robot.coords.y > 0:
                while self.robot.direction != DIRECTIONS["DOWN"]:
                    self.robot_turn_left()
            elif self.robot.coords.x < 0 and self.robot.coords.y >= 0:
                while self.robot.direction != DIRECTIONS["RIGHT"]:
                    self.robot_turn_left()
            elif self.robot.coords.x <= 0 and self.robot.coords.y < 0:
                while self.robot.direction != DIRECTIONS["UP"]:
                    self.robot_turn_left()
            elif self.robot.coords.x > 0 and self.robot.coords.y <= 0:
                while self.robot.direction != DIRECTIONS["LEFT"]:
                    self.robot_turn_left()
            # move in the right direction
            self.robot_move()
            if self.robot.coords == self.robot.coords_last:
                self.robot_evade()

# thread main method, gets called with every new client ################################################################
    def handle(self):
        """Handles each client"""
        print(f"{Colors.OK_BLUE}Client {threading.current_thread().name[7:]}: START: from {self.client_address}{Colors.END_C}")
        self.request.settimeout(TIMEOUT)
        try:
            # Authentication ###########################################################################################
            print(f"{Colors.OK_CYAN}Client {threading.current_thread().name[7:]}: AUTHENTICATION{Colors.END_C}")
            self.authentication()
            # Navigation ###############################################################################################
            print(f"{Colors.OK_CYAN}Client {threading.current_thread().name[7:]}: NAVIGATION{Colors.END_C}")
            self.navigation()
        # Error handling ###############################################################################################
        except ServerLoginFailed as serverLoginFailed:
            print(f"{Colors.FAIL_RED}Client {threading.current_thread().name[7:]}: LOGIN_FAILED (300) : {serverLoginFailed.message}{Colors.END_C}")
            self.request.sendall(SERVER_MESSAGES["SERVER_LOGIN_FAILED"])
            sys.exit(300)
        except ServerSyntaxError as serverSyntaxError:
            print(f"{Colors.FAIL_RED}Client {threading.current_thread().name[7:]}: SYNTAX_ERROR (301) : {serverSyntaxError.message}{Colors.END_C}")
            self.request.sendall(SERVER_MESSAGES["SERVER_SYNTAX_ERROR"])
            sys.exit(301)
        except ServerLogicError as serverLogicError:
            print(f"{Colors.FAIL_RED}Client {threading.current_thread().name[7:]}: LOGIC_ERROR (302) : {serverLogicError.message}{Colors.END_C}")
            self.request.sendall(SERVER_MESSAGES["SERVER_LOGIC_ERROR"])
            sys.exit(302)
        except ServerKeyOutOfRangeError as serverKeyOutOfRangeError:
            print(f"{Colors.FAIL_RED}Client {threading.current_thread().name[7:]}: KEYID_ERROR (303) : {serverKeyOutOfRangeError.message}{Colors.END_C}")
            self.request.sendall(SERVER_MESSAGES["SERVER_KEY_OUT_OF_RANGE_ERROR"])
            sys.exit(303)
        except socket.timeout:
            print(f"{Colors.FAIL_RED}Client {threading.current_thread().name[7:]}: TIMED OUT{Colors.END_C}")
            sys.exit(408)
        sys.exit(200)


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


########################################################################################################################
# main, server setup
if __name__ == '__main__':
    try:
        server_tcp = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
        print(f"{Colors.OK_GREEN}Server START{Colors.END_C}")
    except OSError as os_error:
        print(f"{Colors.FAIL_RED}OSError: [Errno 98] Address already in use (Server could not start, try waiting...){Colors.END_C}")
        sys.exit(98)
    with server_tcp:
        print(f"HOST: {server_tcp.server_address[0]}, PORT: {server_tcp.server_address[1]}")
        try:
            server_tcp.serve_forever()
        except KeyboardInterrupt:
            print(f"{Colors.WARNING_YELLOW}Shutdown requested...{Colors.END_C}")
            print(f"{Colors.FAIL_RED}Server SHUTDOWN{Colors.END_C}")
            os._exit(200)
