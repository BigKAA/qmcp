# Copyright 2024 Artur
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for cross-process single-flight locking."""

import pytest

from qmcp.locking import _lock_file_path, try_singleflight

fcntl = pytest.importorskip("fcntl")


class TestTrySingleflight:
    """Tests for the try_singleflight context manager."""

    def test_first_caller_acquires(self, tmp_path):
        """With no contention the caller gets the lock."""
        with try_singleflight("key", tmp_path) as acquired:
            assert acquired is True

    def test_same_key_contends(self, tmp_path):
        """A second acquisition of the same key while held yields False."""
        with try_singleflight("key", tmp_path):
            with try_singleflight("key", tmp_path) as acquired:
                assert acquired is False

    def test_lock_released_after_context(self, tmp_path):
        """Leaving the context releases the lock for the next caller."""
        with try_singleflight("key", tmp_path):
            pass

        with try_singleflight("key", tmp_path) as acquired:
            assert acquired is True

    def test_different_keys_do_not_contend(self, tmp_path):
        """Locks are independent per key."""
        with try_singleflight("a", tmp_path):
            with try_singleflight("b", tmp_path) as acquired:
                assert acquired is True

    def test_creates_lock_dir(self, tmp_path):
        """The lock directory is created on first use."""
        lock_dir = tmp_path / "nested" / "locks"
        with try_singleflight("key", lock_dir) as acquired:
            assert acquired is True
        assert lock_dir.is_dir()


class TestLockFilePath:
    """Tests for lock key to file name mapping."""

    def test_name_is_stable(self, tmp_path):
        """Same key maps to the same lock file."""
        assert _lock_file_path(tmp_path, "code:/x.py") == _lock_file_path(tmp_path, "code:/x.py")

    def test_name_hides_raw_key(self, tmp_path):
        """File names are digests - raw paths never leak into them."""
        name = _lock_file_path(tmp_path, "code:/Users/secret/project/x.py").name
        assert "secret" not in name
        assert "x.py" not in name
