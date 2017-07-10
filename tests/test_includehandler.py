# kas - setup tool for bitbake based projects
#
# Copyright (c) Siemens AG, 2017
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# pylint: disable=missing-docstring,no-self-use

import os
import io
import textwrap
import contextlib

import pytest

from kas import includehandler


@pytest.fixture(autouse=True)
def fixed_version(monkeypatch):
    monkeypatch.setattr(includehandler, '__version__', '0.5.0')
    monkeypatch.setattr(includehandler, '__compatible_version__', '0.5')


class MockFileIO(io.StringIO):
    def close(self):
        self.seek(0)


def mock_file(indented_content):
    return MockFileIO(textwrap.dedent(indented_content))


@contextlib.contextmanager
def patch_open(component, string='', dictionary=None):
    dictionary = dictionary or {}
    old_attr = getattr(component, 'open', None)
    component.open = lambda f, *a, **k: mock_file(dictionary.get(f, string))
    yield
    if old_attr:
        component.open = old_attr
    else:
        del component.open


class TestLoadConfig(object):
    def test_err_invalid_ext(self):
        # Test for invalid file extension:
        exception = includehandler.LoadConfigException
        with pytest.raises(exception):
            includehandler.load_config('x.xyz')

    def util_exception_content(self, testvector):
        for string, exception in testvector:
            with patch_open(includehandler, string=string):
                with pytest.raises(exception):
                    includehandler.load_config('x.yml')

    def test_err_header_missing(self):
        exception = includehandler.LoadConfigException
        testvector = [
            ('', exception),
            ('a', exception),
            ('1', exception),
            ('a:', exception)
            ]

        self.util_exception_content(testvector)

    def test_err_header_invalid_type(self):
        exception = includehandler.LoadConfigException
        testvector = [
            ('header:', exception),
            ('header: 1', exception),
            ('header: a', exception),
            ('header: []', exception),
        ]

        self.util_exception_content(testvector)

    def test_err_version_missing(self):
        exception = includehandler.LoadConfigException
        testvector = [
            ('header: {}', exception),
            ('header: {a: 1}', exception),
        ]

        self.util_exception_content(testvector)

    def test_err_version_invalid_type(self):
        exception = includehandler.LoadConfigException
        testvector = [
            ('header: {version: 1}', exception),
            ('header: {version: a}', exception),
            ('header: {version: 0.4}', exception),
            ('header: {version: 0.5}', exception),
            ('header: {version: 0.6}', exception),
        ]

        self.util_exception_content(testvector)

    def test_err_version_invalid_format(self):
        exception = includehandler.LoadConfigException
        testvector = [
            ('header: {version: "0.4"}', exception),
            ('header: {version: "0.4.5"}', exception),
            ('header: {version: "0.5a"}', exception),
            ('header: {version: "0.5.a"}', exception),
            ('header: {version: "0.5.4.3"}', exception),
            ('header: {version: "0.50"}', exception),
            ('header: {version: "0.6a"}', exception),
            ('header: {version: "0.6"}', exception),
        ]

        self.util_exception_content(testvector)

    def test_header_valid(self):
        testvector = [
            'header: {version: "0.5"}',
            'header: {version: "0.5.0"}',
            'header: {version: "0.5.1"}',
            'header: {version: "0.5.10"}',
            'header: {version: "0.5"}',
            ]
        for string in testvector:
            with patch_open(includehandler, string=string):
                includehandler.load_config('x.yml')


class TestGlobalIncludes(object):
    header = '''
header:
  version: "0.5"
{}'''

    def util_include_content(self, testvector):
        for test in testvector:
            with patch_open(includehandler, dictionary=test['fdict']):
                ginc = includehandler.GlobalIncludes('x.yml')
                config, missing = ginc.get_config(repos=test['rdict'])

                # Remove header, because we dont want to compare it:
                config.pop('header')

                assert test['conf'] == config
                assert test['rmiss'] == missing

    def test_valid_includes_none(self):
        header = self.__class__.header
        testvector = [
            {
                'fdict': {
                    'x.yml': header.format('')
                },
                'rdict': {
                },
                'conf': {
                },
                'rmiss': [
                ]
            },
        ]

        self.util_include_content(testvector)

    def test_valid_includes_some(self):
        header = self.__class__.header
        testvector = [
            # Include one file from the same repo:
            {
                'fdict': {
                    'x.yml': header.format('  includes: ["y.yml"]'),
                    os.path.abspath('y.yml'): header.format('\nv:')
                },
                'rdict': {
                },
                'conf': {
                    'v': None
                },
                'rmiss': [
                ]
            },
            # Include one file from another not available repo:
            {
                'fdict': {
                    'x.yml': header.format(
                        '  includes: [{repo: rep, file: y.yml}]'),
                },
                'rdict': {
                },
                'conf': {
                },
                'rmiss': [
                    'rep',
                ]
            },
            # Include one file from the same repo and one from another
            # not available repo:
            {
                'fdict': {
                    'x.yml': header.format('  includes: ["y.yml", '
                                           '{repo: rep, file: y.yml}]'),
                    os.path.abspath('y.yml'): header.format('\nv:')
                },
                'rdict': {
                },
                'conf': {
                    'v': None
                },
                'rmiss': [
                    'rep',
                ]
            },
            # Include one file from another available repo:
            {
                'fdict': {
                    'x.yml': header.format(
                        '  includes: [{repo: rep, file: y.yml}]'),
                    '/rep/y.yml': header.format('\nv:')
                },
                'rdict': {
                    'rep': '/rep'
                },
                'conf': {
                    'v': None
                },
                'rmiss': [
                ]
            },
        ]

        self.util_include_content(testvector)

    def test_valid_overwriting(self):
        header = self.__class__.header
        testvector = [
            {
                'fdict': {
                    'x.yml': header.format('''  includes: ["y.yml"]
v: x'''),
                    os.path.abspath('y.yml'): header.format('''
v: y''')
                },
                'rdict': {
                },
                'conf': {
                    'v': 'x'
                },
                'rmiss': [
                ]
            },
            {
                'fdict': {
                    'x.yml': header.format('''  includes: ["y.yml"]
v: {v: x}'''),
                    os.path.abspath('y.yml'): header.format('''
v: {v: y}''')
                },
                'rdict': {
                },
                'conf': {
                    'v': {'v': 'x'}
                },
                'rmiss': [
                ]
            },
            {
                'fdict': {
                    'x.yml': header.format('''  includes: ["y.yml"]
v1:
v2: []
v3:
  - a: c'''),
                    os.path.abspath('y.yml'): header.format('''
v1: a
v2: [a]
v3:
  - a: b
  - d: c}]''')
                },
                'rdict': {
                },
                'conf': {
                    'v1': None,
                    'v2': [],
                    'v3': [{'a': 'c'}]
                },
                'rmiss': [
                ]
            },
        ]

        self.util_include_content(testvector)

    def test_valid_merging(self):
        header = self.__class__.header
        testvector = [
            {
                'fdict': {
                    'x.yml': header.format('''  includes: ["y.yml"]
v1: x
v3:
  a: b
  b:
    e:
  c: d'''),
                    os.path.abspath('y.yml'): header.format('''
v2: y
v3:
  d: e
  b:
    c:
  e: f''')
                },
                'rdict': {
                },
                'conf': {
                    'v1': 'x',
                    'v2': 'y',
                    'v3': {
                        'a': 'b',
                        'b': {'c': None, 'e': None},
                        'c': 'd',
                        'd': 'e',
                        'e': 'f'}
                },
                'rmiss': [
                ]
            },
        ]

        self.util_include_content(testvector)

    def test_valid_ordering(self):
        header = self.__class__.header
        with patch_open(includehandler, dictionary={
            'x.yml': header.format('''  includes: ["y.yml", "z.yml"]
v: {v1: x, v2: x}'''),
            os.path.abspath('y.yml'): header.format('''  includes: ["z.yml"]
v: {v2: y, v3: y, v5: y}'''),
            os.path.abspath('z.yml'): header.format('''
v: {v3: z, v4: z}''')}):
            ginc = includehandler.GlobalIncludes('x.yml')
            config, _ = ginc.get_config()
            keys = list(config['v'].keys())
            index = {keys[i]: i for i in range(len(keys))}

            # Check for vars in z.yml:
            assert index['v3'] < index['v1']
            assert index['v3'] < index['v2']
            assert index['v3'] < index['v5']
            assert index['v4'] < index['v1']
            assert index['v4'] < index['v2']
            assert index['v4'] < index['v5']

            # Check for vars in y.yml:
            assert index['v2'] < index['v1']
            assert index['v3'] < index['v1']
            assert index['v5'] < index['v1']