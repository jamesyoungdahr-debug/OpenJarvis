"""Tests for the [tools.send_email] config section."""

from __future__ import annotations

from openjarvis.core.config import SendEmailToolConfig, ToolsConfig, load_config


def test_send_email_defaults():
    config = SendEmailToolConfig()

    assert config.backend == "smtp"
    assert config.smtp_host == ""
    assert config.smtp_port == 587
    assert config.smtp_security == "starttls"
    assert config.from_address == ""
    assert config.max_recipients == 10
    assert isinstance(ToolsConfig().send_email, SendEmailToolConfig)


def test_send_email_section_loads_from_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[tools.send_email]\n"
        'backend = "gmail"\n'
        'smtp_host = "smtp.example.com"\n'
        "smtp_port = 465\n"
        'smtp_security = "ssl"\n'
        'from_address = "me@example.com"\n'
        "max_recipients = 3\n",
        encoding="utf-8",
    )

    config = load_config(path)

    send_email = config.tools.send_email
    assert send_email.backend == "gmail"
    assert send_email.smtp_host == "smtp.example.com"
    assert send_email.smtp_port == 465
    assert send_email.smtp_security == "ssl"
    assert send_email.from_address == "me@example.com"
    assert send_email.max_recipients == 3
