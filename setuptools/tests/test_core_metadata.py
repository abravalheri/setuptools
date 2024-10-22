from __future__ import annotations

import functools
import importlib
import io
from email import message_from_string
from email.message import Message
from pathlib import Path
from unittest.mock import Mock

import pytest
from packaging.metadata import Metadata
from packaging.requirements import Requirement

from setuptools import _reqs, sic
from setuptools._core_metadata import rfc822_escape, rfc822_unescape
from setuptools.command.egg_info import egg_info, write_requirements
from setuptools.config import expand, setupcfg
from setuptools.dist import Distribution

from .config.downloads import retrieve_file, urls_from_file

EXAMPLE_BASE_INFO = dict(
    name="package",
    version="0.0.1",
    author="Foo Bar",
    author_email="foo@bar.net",
    long_description="Long\ndescription",
    description="Short description",
    keywords=["one", "two"],
)


@pytest.mark.parametrize(
    'content, result',
    (
        pytest.param(
            "Just a single line",
            None,
            id="single_line",
        ),
        pytest.param(
            "Multiline\nText\nwithout\nextra indents\n",
            None,
            id="multiline",
        ),
        pytest.param(
            "Multiline\n    With\n\nadditional\n  indentation",
            None,
            id="multiline_with_indentation",
        ),
        pytest.param(
            "  Leading whitespace",
            "Leading whitespace",
            id="remove_leading_whitespace",
        ),
        pytest.param(
            "  Leading whitespace\nIn\n    Multiline comment",
            "Leading whitespace\nIn\n    Multiline comment",
            id="remove_leading_whitespace_multiline",
        ),
    ),
)
def test_rfc822_unescape(content, result):
    assert (result or content) == rfc822_unescape(rfc822_escape(content))


def __read_test_cases():
    base = EXAMPLE_BASE_INFO

    params = functools.partial(dict, base)

    return [
        ('Metadata version 1.0', params()),
        (
            'Metadata Version 1.0: Short long description',
            params(
                long_description='Short long description',
            ),
        ),
        (
            'Metadata version 1.1: Classifiers',
            params(
                classifiers=[
                    'Programming Language :: Python :: 3',
                    'Programming Language :: Python :: 3.7',
                    'License :: OSI Approved :: MIT License',
                ],
            ),
        ),
        (
            'Metadata version 1.1: Download URL',
            params(
                download_url='https://example.com',
            ),
        ),
        (
            'Metadata Version 1.2: Requires-Python',
            params(
                python_requires='>=3.7',
            ),
        ),
        pytest.param(
            'Metadata Version 1.2: Project-Url',
            params(project_urls=dict(Foo='https://example.bar')),
            marks=pytest.mark.xfail(
                reason="Issue #1578: project_urls not read",
            ),
        ),
        (
            'Metadata Version 2.1: Long Description Content Type',
            params(
                long_description_content_type='text/x-rst; charset=UTF-8',
            ),
        ),
        (
            'License',
            params(
                license='MIT',
            ),
        ),
        (
            'License multiline',
            params(
                license='This is a long license \nover multiple lines',
            ),
        ),
        pytest.param(
            'Metadata Version 2.1: Provides Extra',
            params(provides_extras=['foo', 'bar']),
            marks=pytest.mark.xfail(reason="provides_extras not read"),
        ),
        (
            'Missing author',
            dict(
                name='foo',
                version='1.0.0',
                author_email='snorri@sturluson.name',
            ),
        ),
        (
            'Missing author e-mail',
            dict(
                name='foo',
                version='1.0.0',
                author='Snorri Sturluson',
            ),
        ),
        (
            'Missing author and e-mail',
            dict(
                name='foo',
                version='1.0.0',
            ),
        ),
        (
            'Bypass normalized version',
            dict(
                name='foo',
                version=sic('1.0.0a'),
            ),
        ),
    ]


@pytest.mark.parametrize('name,attrs', __read_test_cases())
def test_read_metadata(name, attrs):
    dist = Distribution(attrs)
    metadata_out = dist.metadata
    dist_class = metadata_out.__class__

    # Write to PKG_INFO and then load into a new metadata object
    PKG_INFO = io.StringIO()

    metadata_out.write_pkg_file(PKG_INFO)
    PKG_INFO.seek(0)
    pkg_info = PKG_INFO.read()
    assert _valid_metadata(pkg_info)

    PKG_INFO.seek(0)
    metadata_in = dist_class()
    metadata_in.read_pkg_file(PKG_INFO)

    tested_attrs = [
        ('name', dist_class.get_name),
        ('version', dist_class.get_version),
        ('author', dist_class.get_contact),
        ('author_email', dist_class.get_contact_email),
        ('metadata_version', dist_class.get_metadata_version),
        ('provides', dist_class.get_provides),
        ('description', dist_class.get_description),
        ('long_description', dist_class.get_long_description),
        ('download_url', dist_class.get_download_url),
        ('keywords', dist_class.get_keywords),
        ('platforms', dist_class.get_platforms),
        ('obsoletes', dist_class.get_obsoletes),
        ('requires', dist_class.get_requires),
        ('classifiers', dist_class.get_classifiers),
        ('project_urls', lambda s: getattr(s, 'project_urls', {})),
        ('provides_extras', lambda s: getattr(s, 'provides_extras', {})),
    ]

    for attr, getter in tested_attrs:
        assert getter(metadata_in) == getter(metadata_out)


def __maintainer_test_cases():
    attrs = {"name": "package", "version": "1.0", "description": "xxx"}

    def merge_dicts(d1, d2):
        d1 = d1.copy()
        d1.update(d2)

        return d1

    return [
        ('No author, no maintainer', attrs.copy()),
        (
            'Author (no e-mail), no maintainer',
            merge_dicts(attrs, {'author': 'Author Name'}),
        ),
        (
            'Author (e-mail), no maintainer',
            merge_dicts(
                attrs, {'author': 'Author Name', 'author_email': 'author@name.com'}
            ),
        ),
        (
            'No author, maintainer (no e-mail)',
            merge_dicts(attrs, {'maintainer': 'Maintainer Name'}),
        ),
        (
            'No author, maintainer (e-mail)',
            merge_dicts(
                attrs,
                {
                    'maintainer': 'Maintainer Name',
                    'maintainer_email': 'maintainer@name.com',
                },
            ),
        ),
        (
            'Author (no e-mail), Maintainer (no-email)',
            merge_dicts(
                attrs, {'author': 'Author Name', 'maintainer': 'Maintainer Name'}
            ),
        ),
        (
            'Author (e-mail), Maintainer (e-mail)',
            merge_dicts(
                attrs,
                {
                    'author': 'Author Name',
                    'author_email': 'author@name.com',
                    'maintainer': 'Maintainer Name',
                    'maintainer_email': 'maintainer@name.com',
                },
            ),
        ),
        (
            'No author (e-mail), no maintainer (e-mail)',
            merge_dicts(
                attrs,
                {
                    'author_email': 'author@name.com',
                    'maintainer_email': 'maintainer@name.com',
                },
            ),
        ),
        ('Author unicode', merge_dicts(attrs, {'author': '鉄沢寛'})),
        ('Maintainer unicode', merge_dicts(attrs, {'maintainer': 'Jan Łukasiewicz'})),
    ]


@pytest.mark.parametrize('name,attrs', __maintainer_test_cases())
def test_maintainer_author(name, attrs, tmpdir):
    tested_keys = {
        'author': 'Author',
        'author_email': 'Author-email',
        'maintainer': 'Maintainer',
        'maintainer_email': 'Maintainer-email',
    }

    # Generate a PKG-INFO file
    dist = Distribution(attrs)
    fn = tmpdir.mkdir('pkg_info')
    fn_s = str(fn)

    dist.metadata.write_pkg_info(fn_s)

    with open(str(fn.join('PKG-INFO')), 'r', encoding='utf-8') as f:
        pkg_info = f.read()

    assert _valid_metadata(pkg_info)

    # Drop blank lines and strip lines from default description
    raw_pkg_lines = pkg_info.splitlines()
    pkg_lines = list(filter(None, raw_pkg_lines[:-2]))

    pkg_lines_set = set(pkg_lines)

    # Duplicate lines should not be generated
    assert len(pkg_lines) == len(pkg_lines_set)

    for fkey, dkey in tested_keys.items():
        val = attrs.get(dkey, None)
        if val is None:
            for line in pkg_lines:
                assert not line.startswith(fkey + ':')
        else:
            line = '%s: %s' % (fkey, val)
            assert line in pkg_lines_set


class TestParityWithMetadataFromPyPaWheel:
    def base_example(self):
        attrs = dict(
            **EXAMPLE_BASE_INFO,
            # Example with complex requirement definition
            python_requires=">=3.8",
            install_requires="""
            packaging==23.2
            more-itertools==8.8.0; extra == "other"
            jaraco.text==3.7.0
            importlib-resources==5.10.2; python_version<"3.8"
            importlib-metadata==6.0.0 ; python_version<"3.8"
            colorama>=0.4.4; sys_platform == "win32"
            """,
            extras_require={
                "testing": """
                    pytest >= 6
                    pytest-checkdocs >= 2.4
                    tomli ; \\
                            # Using stdlib when possible
                            python_version < "3.11"
                    ini2toml[lite]>=0.9
                    """,
                "other": [],
            },
        )
        # Generate a PKG-INFO file using setuptools
        return Distribution(attrs)

    def test_requires_dist(self, tmp_path):
        dist = self.base_example()
        pkg_info = _get_pkginfo(dist)
        assert _valid_metadata(pkg_info)

        # Ensure Requires-Dist is present
        expected = [
            'Metadata-Version:',
            'Requires-Python: >=3.8',
            'Provides-Extra: other',
            'Provides-Extra: testing',
            'Requires-Dist: tomli; python_version < "3.11" and extra == "testing"',
            'Requires-Dist: more-itertools==8.8.0; extra == "other"',
            'Requires-Dist: ini2toml[lite]>=0.9; extra == "testing"',
        ]
        for line in expected:
            assert line in pkg_info

    HERE = Path(__file__).parent
    EXAMPLES_FILE = HERE / "config/setupcfg_examples.txt"

    @pytest.fixture(params=[None, *urls_from_file(EXAMPLES_FILE)])
    def dist(self, request, monkeypatch, tmp_path):
        """Example of distribution with arbitrary configuration"""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(expand, "read_attr", Mock(return_value="0.42"))
        monkeypatch.setattr(expand, "read_files", Mock(return_value="hello world"))
        if request.param is None:
            yield self.base_example()
        else:
            # Real-world usage
            config = retrieve_file(request.param)
            yield setupcfg.apply_configuration(Distribution({}), config)

    def test_equivalent_output(self, tmp_path, dist):
        """Ensure output from setuptools is equivalent to the one from `pypa/wheel`"""
        # Generate a METADATA file using pypa/wheel for comparison
        wheel_metadata = importlib.import_module("wheel.metadata")
        pkginfo_to_metadata = getattr(wheel_metadata, "pkginfo_to_metadata", None)

        if pkginfo_to_metadata is None:
            pytest.xfail(
                "wheel.metadata.pkginfo_to_metadata is undefined, "
                "(this is likely to be caused by API changes in pypa/wheel"
            )

        # Generate an simplified "egg-info" dir for pypa/wheel to convert
        pkg_info = _get_pkginfo(dist)
        egg_info_dir = tmp_path / "pkg.egg-info"
        egg_info_dir.mkdir(parents=True)
        (egg_info_dir / "PKG-INFO").write_text(pkg_info, encoding="utf-8")
        write_requirements(egg_info(dist), egg_info_dir, egg_info_dir / "requires.txt")

        # Get pypa/wheel generated METADATA but normalize requirements formatting
        metadata_msg = pkginfo_to_metadata(egg_info_dir, egg_info_dir / "PKG-INFO")
        metadata_str = _normalize_metadata(metadata_msg)
        pkg_info_msg = message_from_string(pkg_info)
        pkg_info_str = _normalize_metadata(pkg_info_msg)

        # Compare setuptools PKG-INFO x pypa/wheel METADATA
        assert metadata_str == pkg_info_str


def _normalize_metadata(msg: Message) -> str:
    """Allow equivalent metadata to be compared directly"""
    # The main challenge regards the requirements and extras.
    # Both setuptools and wheel already apply some level of normalization
    # but they differ regarding which character is chosen, according to the
    # following spec it should be "-":
    # https://packaging.python.org/en/latest/specifications/name-normalization/

    # Related issues:
    # https://github.com/pypa/packaging/issues/845
    # https://github.com/pypa/packaging/issues/644#issuecomment-2429813968

    extras = {x.replace("_", "-"): x for x in msg.get_all("Provides-Extra", [])}
    reqs = [
        _normalize_req(req, extras)
        for req in _reqs.parse(msg.get_all("Requires-Dist", []))
    ]
    del msg["Requires-Dist"]
    del msg["Provides-Extra"]

    for req in sorted(reqs):
        msg["Requires-Dist"] = req
    for extra in sorted(extras):
        msg["Provides-Extra"] = extra

    return msg.as_string()


def _normalize_req(req: Requirement, extras: dict[str, str]) -> str:
    """Allow equivalent requirement objects to be compared directly"""
    as_str = str(req).replace(req.name, req.name.replace("_", "-"))
    for norm, orig in extras.items():
        as_str = as_str.replace(orig, norm)
    return as_str


def _get_pkginfo(dist: Distribution):
    with io.StringIO() as fp:
        dist.metadata.write_pkg_file(fp)
        return fp.getvalue()


def _valid_metadata(text: str) -> bool:
    metadata = Metadata.from_email(text, validate=True)  # can raise exceptions
    return metadata is not None
