from free_frontier.cooldowns import CooldownTracker


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_cooldown_expires_automatically() -> None:
    clock = FakeClock()
    cooldowns = CooldownTracker(clock=clock)

    cooldowns.start("route-a", 30)
    assert cooldowns.is_cooling_down("route-a") is True
    assert cooldowns.remaining("route-a") == 30

    clock.advance(29)
    assert cooldowns.is_cooling_down("route-a") is True

    clock.advance(1)
    assert cooldowns.is_cooling_down("route-a") is False
    assert cooldowns.remaining("route-a") == 0
