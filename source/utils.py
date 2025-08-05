import random

from datetime import datetime, timezone


def get_utc_timestamp() -> str:
    # 현재 UTC 시간을 ISO 8601 형식으로 반환
    return datetime.now(timezone.utc).isoformat()


def get_random_time() -> float:
    # 베타 분포에서 랜덤한 값을 얻음
    value = random.betavariate(1, 3)
    # 값을 0.01과 0.7 사이의 범위로 스케일링
    return 0.01 + value * (0.35 - 0.01)


def log_event(
    event_type,
    username,
    additional_info=""
) -> None:
    # 이벤트를 로그에 기록
    line = f"{get_utc_timestamp()} - {username} - {event_type}: {additional_info}\n"
    with open("events.log", "a", encoding="utf-8") as log_file:
        log_file.write(line)
