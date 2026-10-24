//go:build darwin

package main

import (
	"context"
	"crypto/rand"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"

	"golang.org/x/sys/unix"
)

// cloneFixture lays out one 1 MiB file, two APFS clones that still share every
// block, one clone with a byte rewritten (it owns blocks now) and one
// unrelated file of the same size.
type cloneFixture struct {
	root, orig, clone1, clone2, edited, plain string
}

func newCloneFixture(t *testing.T) cloneFixture {
	t.Helper()
	root := t.TempDir()
	f := cloneFixture{
		root:   root,
		orig:   filepath.Join(root, "a", "orig.bin"),
		clone1: filepath.Join(root, "b", "clone1.bin"),
		clone2: filepath.Join(root, "b", "clone2.bin"),
		edited: filepath.Join(root, "c", "edited.bin"),
		plain:  filepath.Join(root, "c", "plain.bin"),
	}
	for _, p := range []string{f.orig, f.clone1, f.clone2, f.edited, f.plain} {
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	// Random bytes, so no block is zero-filled or deduplicated some other way.
	for _, p := range []string{f.orig, f.plain} {
		data := make([]byte, 1<<20)
		if _, err := rand.Read(data); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, data, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	for _, dst := range []string{f.clone1, f.clone2, f.edited} {
		if err := unix.Clonefile(f.orig, dst, 0); err != nil {
			if errors.Is(err, unix.ENOTSUP) || errors.Is(err, unix.EXDEV) {
				t.Skipf("this volume cannot clone files: %v", err)
			}
			t.Fatalf("clonefile %s: %v", dst, err)
		}
	}
	rw, err := os.OpenFile(f.edited, os.O_RDWR, 0)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := rw.WriteAt([]byte{0xAA}, 100); err != nil {
		rw.Close() //nolint:errcheck
		t.Fatal(err)
	}
	if err := rw.Close(); err != nil {
		t.Fatal(err)
	}
	return f
}

func TestCloneIdentitySeparatesSharedAndEditedClones(t *testing.T) {
	f := newCloneFixture(t)

	origID, origShares, ok := cloneIdentity(f.orig)
	if !ok || !origShares {
		t.Fatalf("the original still shares all its blocks: id=%d shares=%v ok=%v", origID, origShares, ok)
	}
	cloneID, cloneShares, ok := cloneIdentity(f.clone1)
	if !ok || !cloneShares || cloneID != origID {
		t.Fatalf("clone must report the original's id %d, got id=%d shares=%v ok=%v", origID, cloneID, cloneShares, ok)
	}
	if id, shares, ok := cloneIdentity(f.edited); !ok || shares {
		t.Fatalf("an edited clone owns blocks and must not read as sharing all: id=%d shares=%v ok=%v", id, shares, ok)
	}
	if id, shares, ok := cloneIdentity(f.plain); !ok || shares || id == origID {
		t.Fatalf("an unrelated file must not join the group: id=%d shares=%v ok=%v", id, shares, ok)
	}
	if _, _, ok := cloneIdentity(filepath.Join(f.root, "missing")); ok {
		t.Fatal("a missing path has no clone identity")
	}
}

func TestCountableFileSizeCountsSharedBlockClonesOnce(t *testing.T) {
	f := newCloneFixture(t)
	paths := []string{f.clone2, f.orig, f.plain, f.clone1, f.edited}

	count := func(seen *sync.Map) (total int64, deduped int) {
		for _, p := range paths {
			info, err := os.Lstat(p)
			if err != nil {
				t.Fatal(err)
			}
			size, dup := countableFileSize(p, info, seen)
			total += size
			if dup {
				deduped++
			}
		}
		return total, deduped
	}
	one := int64(1 << 20)

	total, deduped := count(&sync.Map{})
	// orig, clone1 and clone2 are one set of blocks and count once (whichever is
	// met first); the edited copy and the plain file count in full.
	if want := 3 * one; total != want || deduped != 2 {
		t.Fatalf("shared-block clones must count once: total=%d (want %d) deduped=%d (want 2)", total, want, deduped)
	}

	// A nil seen map keeps the plain per-file sizes, as hardlink dedup does.
	total, deduped = count(nil)
	if total != 5*one || deduped != 0 {
		t.Fatalf("without a seen map every file counts in full: total=%d deduped=%d", total, deduped)
	}
}

func TestScanPathConcurrentCountsSharedBlockClonesOnce(t *testing.T) {
	f := newCloneFixture(t)

	var filesScanned, dirsScanned, bytesScanned int64
	current := &atomic.Value{}
	current.Store("")
	result, err := scanPathConcurrent(context.Background(), f.root, &filesScanned, &dirsScanned, &bytesScanned, current)
	if err != nil {
		t.Fatal(err)
	}

	size := func(p string) int64 {
		info, err := os.Lstat(p)
		if err != nil {
			t.Fatal(err)
		}
		return getActualFileSize(p, info)
	}
	// orig, clone1 and clone2 are one set of blocks; edited and plain are their own.
	want := size(f.orig) + size(f.edited) + size(f.plain)
	if result.TotalSize != want {
		t.Fatalf("folder total %d, want %d (three clones summed to %d before)", result.TotalSize, want, want+2*size(f.orig))
	}
	if !result.dedupedHardlink {
		t.Fatal("a clone-deduplicated total depends on scan order and must not be cached per folder")
	}
}

func TestCountableFileSizeDeduplicatesClonesWithHardlinks(t *testing.T) {
	f := newCloneFixture(t)
	link := filepath.Join(f.root, "hardlink")
	if err := os.Link(f.orig, link); err != nil {
		t.Fatal(err)
	}
	for _, paths := range [][]string{{f.orig, f.clone1, link}, {f.clone1, link, f.orig}} {
		var seen sync.Map
		var total int64
		for _, path := range paths {
			info, err := os.Lstat(path)
			if err != nil {
				t.Fatal(err)
			}
			size, _ := countableFileSize(path, info, &seen)
			total += size
		}
		if total != 1<<20 {
			t.Fatalf("hardlinks and clones counted %d, want %d", total, 1<<20)
		}
	}
}
