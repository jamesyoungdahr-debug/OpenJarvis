"""Tests for the docker_shell_exec tool's confirmation requirement."""

from __future__ import annotations

from openjarvis.tools.docker_shell_exec import DockerShellExecTool


def test_docker_shell_exec_requires_confirmation():
    spec = DockerShellExecTool().spec
    assert spec.name == "docker_shell_exec"
    assert spec.requires_confirmation is True
