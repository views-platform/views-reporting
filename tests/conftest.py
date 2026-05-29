def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "red_team: adversarial tests (ADR-005)")
    config.addinivalue_line("markers", "green_team: correctness tests (ADR-005)")
    config.addinivalue_line("markers", "beige_team: realistic usage tests (ADR-005)")
