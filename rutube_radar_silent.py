import rutube_radar

_ORIGINAL_NOTIFY = rutube_radar.main.notify_telegram


def _quiet_notify(text: str):
    message = str(text or "")
    if "BAY-S RUTUBE RADAR tamamlandı" in message and "Yeni aday yok" in message:
        print("RUTUBE_EMPTY_SILENT", message.replace("\n", " | "))
        return None
    return _ORIGINAL_NOTIFY(message)


rutube_radar.main.notify_telegram = _quiet_notify


def run():
    return rutube_radar.run()


if __name__ == "__main__":
    run()
