from urllib.parse import urlparse


def same_origin(left: str, right: str) -> bool:
    a, b = urlparse(left), urlparse(right)
    return a.scheme == b.scheme and a.hostname == b.hostname and a.port == b.port


def test_lookalike_host_is_not_same_origin():
    assert not same_origin("https://chat.deepseek.com.evil.example/", "https://chat.deepseek.com/")
    assert same_origin("https://chat.deepseek.com/chat/1", "https://chat.deepseek.com/")
