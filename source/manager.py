import string
import random

from . import room, event


class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.event_bus = event.EventBus()

    def create_room(self, model_pros, model_cons):
        room_id = self.generate_room_id(2)
        self.rooms[room_id] = room.Room(
            room_id=room_id,
            event_bus=self.event_bus,
            model_pros=model_pros,
            model_cons=model_cons
        )
        self.rooms[room_id].start_threads()
        return room_id

    def get_room(self, room_id):
        return self.rooms.get(room_id)

    def remove_room(self, room_id):
        room = self.get_room(room_id)
        if room:
            room.stop_threads()
            self.rooms.pop(room_id, None)

    def list_rooms(self):
        return list(self.rooms.keys())

    def generate_room_id(self, length=2):
        while True:
            code = ""
            for _ in range(length):
                code += random.choice(string.ascii_uppercase)
            if code not in self.rooms:
                break
        return code
