"""
Small lib to snoop on notifications.

Usage:

import notif_snoop

...
notif_snoop.start_monitor()
...

def process():
    while True:
        notif = notif_snoop.queue.get()  # block till we get one
        # use the notification
"""

from dataclasses import dataclass
from queue import Queue
from threading import Thread

from jeepney import HeaderFields, MatchRule, Message
from jeepney.io.blocking import open_dbus_connection
import subprocess as sp


@dataclass(slots=True)
class Notif:
    app_name: str
    replaces_id: int
    app_icon: str
    summary: str
    body: str
    actions: list
    hints: dict
    timeout: int


conn = open_dbus_connection()

mr = MatchRule(
    type="method_call",
    interface="org.freedesktop.Notifications",
    path="/org/freedesktop/Notifications",
    member="Notify",
    eavesdrop=True,
)
conn.bus_proxy.AddMatch(mr)

queue: Queue[Notif] = Queue(100)
"""The main public data structure. New notifs will be put into this."""


def monitor():
    while True:
        msg = conn.receive()
        if notif := parse_msg(msg):
            queue.put(notif)


def parse_msg(msg: Message) -> Notif | None:
    if msg.header.fields[HeaderFields.signature] != "susssasa{sv}i":
        print(f"unknown msg {msg}")
        return
    return Notif(*msg.body)


def start_monitor():
    """Starts a daemon thread to snoop on the notifcations"""
    mon_thread = Thread(target=monitor, name="monitor", daemon=True)
    mon_thread.start()


def main():
    """Example consumer that simply prints the notification"""

    def ping_phone(notif: Notif):
        try: 
            sp.check_call(["kdeconnect-cli", "--ping-msg", f"Custom ping {notif.summary}!\n{notif.body}", "-n", "devicename"])
        except sp.CalledProcessError as e:
            print(f"error calling kdeconnect-cli {e}")


    def play_sound(notif: Notif):
        _ = notif
        try: 
            sp.check_call(["mpv", "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        except sp.CalledProcessError as e:
            print(f"error calling mpv {e}")

    start_monitor()

    on_notif = [ping_phone, play_sound]
    while True:
        notif = queue.get()
        if "urgent" in notif.summary:
            threads = [Thread(target=func, args=(notif,)) for func in on_notif]
            for t in threads: t.start()
            for t in threads: t.join()


if __name__ == "__main__":
    main()
