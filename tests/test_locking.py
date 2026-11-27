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

from qmcp.locking import LeaderLock, _lock_file_path, try_singleflight

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


class TestLeaderLock:
    """Tests for the long-held leader lock."""

    def test_acquire_without_contention(self, tmp_path):
        """The first caller becomes the leader and holds the lock."""
        lock = LeaderLock("watcher:/repo", tmp_path)

        assert lock.acquire() is True
        assert lock.is_held is True

    def test_second_caller_stays_standby(self, tmp_path):
        """While a leader holds the lock, another instance cannot acquire."""
        leader = LeaderLock("watcher:/repo", tmp_path)
        standby = LeaderLock("watcher:/repo", tmp_path)
        leader.acquire()

        assert standby.acquire() is False
        assert standby.is_held is False

    def test_release_allows_promotion(self, tmp_path):
        """A released lock is immediately acquirable by a standby."""
        leader = LeaderLock("watcher:/repo", tmp_path)
        standby = LeaderLock("watcher:/repo", tmp_path)
        leader.acquire()
        leader.release()

        assert leader.is_held is False
        assert standby.acquire() is True

    def test_reacquire_after_external_release(self, tmp_path):
        """A dead leader's flock is dropped by the OS; standbys take over."""
        # Simulate a foreign leader process by holding the flock manually
        lock_dir = tmp_path
        lock_dir.mkdir(exist_ok=True)
        lock_file = _lock_file_path(lock_dir, "watcher:/repo")
        with open(lock_file, "w") as foreign_handle:
            fcntl.flock(foreign_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            standby = LeaderLock("watcher:/repo", lock_dir)
            assert standby.acquire() is False

            # The foreign process dies -> the OS releases its flock
            fcntl.flock(foreign_handle, fcntl.LOCK_UN)

        assert standby.acquire() is True

    def test_release_is_idempotent(self, tmp_path):
        """Releasing an unheld lock is a no-op."""
        lock = LeaderLock("watcher:/repo", tmp_path)

        lock.release()
        lock.release()

        assert lock.is_held is False

    def test_reacquire_swaps_handles(self, tmp_path):
        """Acquiring twice in a row keeps exactly one open handle."""
        lock = LeaderLock("watcher:/repo", tmp_path)
        lock.acquire()
        first_handle = lock._handle

        assert lock.acquire() is True
        assert lock._handle is not first_handle
        assert first_handle.closed is True

    def test_different_keys_do_not_contend(self, tmp_path):
        """Watch sets are independent - one leader per key."""
        first = LeaderLock("watcher:/repo-a", tmp_path)
        second = LeaderLock("watcher:/repo-b", tmp_path)
        first.acquire()

        assert second.acquire() is True

    def test_creates_lock_dir(self, tmp_path):
        """The lock directory is created on first acquire."""
        lock_dir = tmp_path / "nested" / "locks"
        lock = LeaderLock("watcher:/repo", lock_dir)

        assert lock.acquire() is True
        assert lock_dir.is_dir()
