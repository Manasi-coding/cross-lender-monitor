"""The SEC client never exceeds max_requests_per_second from config.yaml.

The limiter is tested on a simulated clock (sleep advances the clock) so the check is exact and fast.
A real clock adds a few milliseconds of scheduling jitter between the limiter and the request."""
import pipeline.ingest as ingest
from pipeline.config import load_config
from pipeline.ingest import SecClient


class _Resp:
    status_code = 200

    def raise_for_status(self):
        return None


class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _client(monkeypatch, cfg):
    clock = _FakeClock()
    monkeypatch.setattr(ingest.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(ingest.time, "sleep", clock.sleep)
    client = SecClient(user_agent="Test Agent test@example.com", sec_config=cfg)
    stamps: list[float] = []

    class _Session:
        headers: dict = {}

        def get(self, url, timeout=None):
            stamps.append(clock.now)
            return _Resp()

    client.session = _Session()
    return client, stamps


def test_requests_stay_within_configured_rate(monkeypatch):
    cfg = load_config()["sec"]
    limit = float(cfg["max_requests_per_second"])
    client, stamps = _client(monkeypatch, cfg)
    n = 40
    for i in range(n):
        client.get(f"https://example.test/{i}")

    assert len(stamps) == n
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert min(gaps) >= (1.0 / limit) - 1e-9
    # no one second window holds more than the limit
    for i, start in enumerate(stamps):
        in_window = sum(1 for s in stamps[i:] if s - start < 1.0)
        assert in_window <= limit


def test_backoff_follows_config(monkeypatch):
    cfg = load_config()["sec"]
    clock = _FakeClock()
    monkeypatch.setattr(ingest.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(ingest.time, "sleep", clock.sleep)
    client = SecClient(user_agent="Test Agent test@example.com", sec_config=cfg)
    waits: list[float] = []
    real_sleep = clock.sleep

    def spy(seconds):
        waits.append(seconds)
        real_sleep(seconds)

    monkeypatch.setattr(ingest.time, "sleep", spy)

    class _Fail:
        status_code = 503

        def raise_for_status(self):
            raise RuntimeError("503")

    class _Session:
        headers: dict = {}

        def get(self, url, timeout=None):
            return _Fail()

    client.session = _Session()
    try:
        client.get("https://example.test/x")
    except RuntimeError:
        pass
    backoffs = [float(s) for s in cfg["backoff_seconds"]]
    assert [w for w in waits if w in backoffs][: len(backoffs)] == backoffs


def test_user_agent_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Env Agent env@example.com")
    client = SecClient()
    assert client.session.headers["User-Agent"] == "Env Agent env@example.com"
