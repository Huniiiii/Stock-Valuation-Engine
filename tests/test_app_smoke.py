"""End-to-end smoke test for the default Streamlit page."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_default_demo_page_renders_without_exceptions():
    entrypoint = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(entrypoint, default_timeout=60).run()

    assert not app.exception
    assert not app.error
    assert [metric.label for metric in app.metric] == [
        "Current Price",
        "Implied Value",
        "Upside / Downside",
        "WACC",
        "Enterprise Value",
    ]
