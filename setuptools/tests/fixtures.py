import contextlib
import sys
import shutil
import subprocess
from pathlib import Path

import pytest

from . import contexts


@pytest.fixture
def user_override(monkeypatch):
    """
    Override site.USER_BASE and site.USER_SITE with temporary directories in
    a context.
    """
    with contexts.tempdir() as user_base:
        monkeypatch.setattr('site.USER_BASE', user_base)
        with contexts.tempdir() as user_site:
            monkeypatch.setattr('site.USER_SITE', user_site)
            with contexts.save_user_site_setting():
                yield


@pytest.fixture
def tmpdir_cwd(tmpdir):
    with tmpdir.as_cwd() as orig:
        yield orig


@pytest.fixture
def tmp_src(request, tmp_path):
    """Make a copy of the source dir under `$tmp/src`.

    This fixture is useful whenever it's necessary to run `setup.py`
    or `pip install` against the source directory when there's no
    control over the number of simultaneous invocations. Such
    concurrent runs create and delete directories with the same names
    under the target directory and so they influence each other's runs
    when they are not being executed sequentially.
    """
    tmp_src_path = tmp_path / 'src'
    tmp_src_path.mkdir(exist_ok=True, parents=True)
    for item in Path(request.config.rootdir).glob("*"):
        name = item.name
        if str(name).startswith(".") or name in ("dist", "build", "docs"):
            # Avoid copying unnecessary folders, specially the .git one
            # that can contain lots of files and is error prone
            continue
        copy = shutil.copy2 if item.is_file() else shutil.copytree
        copy(item, tmp_src_path / item.name)

    yield tmp_src_path


@pytest.fixture(autouse=True, scope="session")
def workaround_xdist_376(request):
    """
    Workaround pytest-dev/pytest-xdist#376

    ``pytest-xdist`` tends to inject '' into ``sys.path``,
    which may break certain isolation expectations.
    Remove the entry so the import
    machinery behaves the same irrespective of xdist.
    """
    if not request.config.pluginmanager.has_plugin('xdist'):
        return

    with contextlib.suppress(ValueError):
        sys.path.remove('')


@pytest.fixture
def sample_project(tmp_path):
    """
    Clone the 'sampleproject' and return a path to it.
    """
    cmd = ['git', 'clone', 'https://github.com/pypa/sampleproject']
    try:
        subprocess.check_call(cmd, cwd=str(tmp_path))
    except Exception:
        pytest.skip("Unable to clone sampleproject")
    return tmp_path / 'sampleproject'


# sdist and wheel artifacts should be stable across a round of tests
# so we can build them once per session and use the files as "readonly"


@pytest.fixture(scope="session")
def setuptools_sdist(tmp_path_factory, request):
    with contexts.session_locked_tmp_dir(tmp_path_factory, "sdist_build") as tmp:
        dist = next(tmp.glob("*.tar.gz"), None)
        if dist:
            return dist

        subprocess.check_call([
            sys.executable, "-m", "build", "--sdist",
            "--outdir", str(tmp), str(request.config.rootdir)
        ])
        return next(tmp.glob("*.tar.gz"))


@pytest.fixture(scope="session")
def setuptools_wheel(tmp_path_factory, request):
    with contexts.session_locked_tmp_dir(tmp_path_factory, "wheel_build") as tmp:
        dist = next(tmp.glob("*.whl"), None)
        if dist:
            return dist

        subprocess.check_call([
            sys.executable, "-m", "build", "--wheel",
            "--outdir", str(tmp) , str(request.config.rootdir)
        ])
        return next(tmp.glob("*.whl"))
