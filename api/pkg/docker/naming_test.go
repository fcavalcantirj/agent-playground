package docker

import (
	"fmt"
	"testing"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestBuildContainerName_Format(t *testing.T) {
	u1 := uuid.New()
	u2 := uuid.New()
	got := BuildContainerName(u1, u2)
	want := fmt.Sprintf("playground-%s-%s", u1.String(), u2.String())
	assert.Equal(t, want, got)
	assert.Len(t, got, 84, "playground- (11) + uuid (36) + - (1) + uuid (36) = 84")
}

func TestParseContainerName_RoundTrip(t *testing.T) {
	for i := 0; i < 100; i++ {
		u1 := uuid.New()
		u2 := uuid.New()
		name := BuildContainerName(u1, u2)
		gotU1, gotU2, err := ParseContainerName(name)
		require.NoError(t, err)
		assert.Equal(t, u1, gotU1)
		assert.Equal(t, u2, gotU2)
	}
}

func TestParseContainerName_RejectsBadPrefix(t *testing.T) {
	u1 := uuid.New()
	u2 := uuid.New()
	bad := fmt.Sprintf("notplayground-%s-%s", u1.String(), u2.String())
	_, _, err := ParseContainerName(bad)
	assert.Error(t, err)
}

func TestParseContainerName_RejectsBadLength(t *testing.T) {
	_, _, err := ParseContainerName("playground-tooshort")
	assert.Error(t, err)
}

func TestParseContainerName_RejectsNonUUID(t *testing.T) {
	// Right shape (11 + 36 + 1 + 36 = 84) but non-UUID content.
	name := "playground-" + "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" + "-" + "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
	_, _, err := ParseContainerName(name)
	assert.Error(t, err)
}

func TestBuildContainerName_PassesValidator(t *testing.T) {
	name := BuildContainerName(uuid.New(), uuid.New())
	assert.NoError(t, validateContainerID(name))
}

func TestIsPlaygroundContainerName_BareAndSlashed(t *testing.T) {
	name := BuildContainerName(uuid.New(), uuid.New())
	assert.True(t, IsPlaygroundContainerName(name))
	assert.True(t, IsPlaygroundContainerName("/"+name))
}

func TestIsPlaygroundContainerName_RejectsOther(t *testing.T) {
	assert.False(t, IsPlaygroundContainerName("/foobar"))
	assert.False(t, IsPlaygroundContainerName("playground"))
	assert.False(t, IsPlaygroundContainerName(""))
	assert.False(t, IsPlaygroundContainerName("other-playground-xxx"))
}

func TestParseContainerName_TolerantOfLeadingSlash(t *testing.T) {
	u1 := uuid.New()
	u2 := uuid.New()
	name := "/" + BuildContainerName(u1, u2)
	gotU1, gotU2, err := ParseContainerName(name)
	require.NoError(t, err)
	assert.Equal(t, u1, gotU1)
	assert.Equal(t, u2, gotU2)
}
