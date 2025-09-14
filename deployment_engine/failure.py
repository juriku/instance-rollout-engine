class FailureInjector:
    def __init__(self, fail_attempts=None, delay=0):
        self.fail_map = fail_attempts or {}
        self.delay = delay
        self.attempts = {}

    def delay_seconds(self):
        return self.delay

    def should_fail(self, instance):
        id = instance.instance_id
        self.attempts[id] = self.attempts.get(id, 0) + 1
        return self.attempts[id] <= self.fail_map.get(id, 0)
