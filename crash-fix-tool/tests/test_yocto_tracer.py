"""Unit tests for the Yocto recipe tracer."""

import subprocess

import pytest

from crash_fix.yocto_tracer import YoctoTracer


@pytest.fixture
def tracer(tmp_path):
    return YoctoTracer(cache_dir=str(tmp_path / "cache"))


class TestExtractVar:
    """Tests for _extract_var."""

    def test_extract_src_uri(self):
        output = '''SRC_URI="git://github.com/example/repo.git;branch=main;protocol=https"'''
        result = YoctoTracer._extract_var(output, "SRC_URI")
        assert result == "git://github.com/example/repo.git;branch=main;protocol=https"

    def test_extract_srcrev(self):
        output = '''SRCREV="abc123def456"'''
        result = YoctoTracer._extract_var(output, "SRCREV")
        assert result == "abc123def456"

    def test_missing_var(self):
        output = '''FOO="bar"'''
        result = YoctoTracer._extract_var(output, "SRC_URI")
        assert result is None


class TestExtractGitUrl:
    """Tests for _extract_git_url."""

    def test_git_protocol(self):
        src_uri = "git://github.com/example/repo.git;branch=main;protocol=https"
        result = YoctoTracer._extract_git_url(src_uri)
        assert result == "git://github.com/example/repo.git"

    def test_https_git(self):
        src_uri = "https://github.com/example/repo.git;branch=dev"
        result = YoctoTracer._extract_git_url(src_uri)
        assert result == "https://github.com/example/repo.git"

    def test_tarball_no_git(self):
        src_uri = "https://example.com/release-1.0.tar.gz"
        result = YoctoTracer._extract_git_url(src_uri)
        assert result is None


class TestExtractBranch:
    """Tests for _extract_branch."""

    def test_branch_present(self):
        src_uri = "git://example.com/repo.git;branch=dunfell;protocol=https"
        result = YoctoTracer._extract_branch(src_uri)
        assert result == "dunfell"

    def test_no_branch(self):
        src_uri = "git://example.com/repo.git;protocol=https"
        result = YoctoTracer._extract_branch(src_uri)
        assert result == "main"


class TestFindRecipe:
    """Tests for find_recipe with mocked subprocess."""

    def test_bitbake_not_available(self, tracer, mocker):
        mocker.patch("shutil.which", return_value=None)
        result = tracer.find_recipe("libfoo.so")
        assert result is None

    def test_component_not_found(self, tracer, mocker):
        mocker.patch("shutil.which", return_value="/usr/bin/bitbake")
        mocker.patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            ),
        )
        result = tracer.find_recipe("libunknown.so")
        assert result is None


class TestExtractSourceInfo:
    """Tests for extract_source_info with mocked subprocess."""

    def test_git_source(self, tracer, mocker):
        bitbake_output = (
            'SRC_URI="git://github.com/example/wpeframework.git;branch=main;protocol=https"\n'
            'SRCREV="abc123def456789"\n'
            'S="/work/build/wpeframework"\n'
        )
        mocker.patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=bitbake_output, stderr=""
            ),
        )
        result = tracer.extract_source_info("wpeframework")
        assert result is not None
        assert result["repo_url"] == "git://github.com/example/wpeframework.git"
        assert result["srcrev"] == "abc123def456789"
        assert result["branch"] == "main"

    def test_tarball_source(self, tracer, mocker):
        bitbake_output = 'SRC_URI="https://example.com/foo-1.0.tar.gz"\n'
        mocker.patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=bitbake_output, stderr=""
            ),
        )
        result = tracer.extract_source_info("foo")
        assert result is None

    def test_bitbake_not_found(self, tracer, mocker):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError)
        result = tracer.extract_source_info("anything")
        assert result is None
