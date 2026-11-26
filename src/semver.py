"""Semantic versions and npm style version ranges.

Only a practical subset of the npm syntax is supported: exact versions,
partial versions such as ``1.2`` or ``1.x``, the wildcard ``*``, the
operators ``^``, ``~``, ``>=``, ``<=``, ``>``, ``<``, ``=`` and
alternatives separated by ``||``.  Git and file requirements are not
version ranges, so the caller reports them as unresolved dependencies.

A version is compared as the tuple ``(major, minor, patch, release)``
where ``release`` sorts a pre-release before the final release, exactly
as the semantic versioning specification requires."""

import re


VERSION_PATTERN = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")

COMPARATOR_SPACES = re.compile(r"(>=|<=|>|<|=|\^|~)\s+")

WILDCARDS = ("", "*", "x", "X")

ALTERNATIVE = "||"

CARET = "^"

TILDE = "~"

COMPARATORS = (">=", "<=", ">", "<", "=")

PART_DELIMITER = "."

PRERELEASE_DELIMITER = "-"

LATEST_WORD = "latest"

MAJOR_INDEX = 0

MINOR_INDEX = 1

PATCH_INDEX = 2

ONE_PART = 1

TWO_PARTS = 2

THREE_PARTS = 3

PRERELEASE_RANK = 0

RELEASE_RANK = 1

ZERO = 0

EMPTY_KEY = (ZERO, ZERO, ZERO, (PRERELEASE_RANK,))

def version_key(text):
    """Return a sortable key of a semantic version or None."""
    match = VERSION_PATTERN.match(text.strip())
    if not match:
        return None
    major, minor, patch = (int(match.group(index))
                           for index in (1, 2, 3))
    return (major, minor, patch, prerelease_key(match.group(4)))

def prerelease_key(text):
    """Build a key that puts a pre-release before the release."""
    if not text:
        return (RELEASE_RANK,)
    parts = []
    for chunk in text.split(PART_DELIMITER):
        if chunk.isdigit():
            parts.append((PRERELEASE_RANK, int(chunk), ""))
        else:
            parts.append((RELEASE_RANK, ZERO, chunk))
    return (PRERELEASE_RANK, tuple(parts))

def is_prerelease(key):
    """Tell whether a parsed version is a pre-release."""
    return key[3][0] == PRERELEASE_RANK

def satisfies(version, requirement):
    """Check whether a version satisfies an npm style requirement."""
    key = version_key(version)
    if key is None:
        return False
    normalized = COMPARATOR_SPACES.sub(r"\1", requirement)
    allow_prerelease = PRERELEASE_DELIMITER in normalized
    if is_prerelease(key) and not allow_prerelease:
        return False
    return any(matches_all(key, part.strip())
               for part in normalized.split(ALTERNATIVE))

def pick_version(versions, requirement, latest=None):
    """Return the highest version that satisfies the requirement."""
    names = list(versions)
    if not names:
        return None
    text = requirement.strip()
    if text in WILDCARDS or text == LATEST_WORD:
        if latest in versions:
            return latest
        return highest(names)
    if text in versions:
        return text
    matched = [name for name in names if satisfies(name, text)]
    if not matched:
        return None
    return highest(matched)

def highest(versions):
    """Return the highest version of the list."""
    return max(versions, key=lambda text: version_key(text) or EMPTY_KEY)

def matches_all(key, alternative):
    """Check all space separated comparators of one alternative."""
    tokens = alternative.split()
    if not tokens:
        return True
    return all(matches_one(key, token) for token in tokens)

def matches_one(key, token):
    """Check one comparator, caret, tilde or partial version."""
    if token in WILDCARDS:
        return True
    if token.startswith(CARET):
        return caret_matches(key, token[len(CARET):])
    if token.startswith(TILDE):
        return tilde_matches(key, token[len(TILDE):])
    for comparator in COMPARATORS:
        if token.startswith(comparator):
            return compare(key, comparator, token[len(comparator):])
    return partial_matches(key, token)

def caret_matches(key, text):
    """Check the caret range: compatible with the same major version."""
    base = loose_key(text)
    if base is None or key < base:
        return False
    if base[MAJOR_INDEX] > ZERO:
        return key[MAJOR_INDEX] == base[MAJOR_INDEX]
    if base[MINOR_INDEX] > ZERO:
        return (key[MAJOR_INDEX] == ZERO
                and key[MINOR_INDEX] == base[MINOR_INDEX])
    return (key[MAJOR_INDEX] == ZERO and key[MINOR_INDEX] == ZERO
            and key[PATCH_INDEX] == base[PATCH_INDEX])

def tilde_matches(key, text):
    """Check the tilde range: allows patch level changes only."""
    base = loose_key(text)
    if base is None or key < base:
        return False
    if specified_parts(text) == ONE_PART:
        return key[MAJOR_INDEX] == base[MAJOR_INDEX]
    return (key[MAJOR_INDEX] == base[MAJOR_INDEX]
            and key[MINOR_INDEX] == base[MINOR_INDEX])

def compare(key, comparator, text):
    """Compare a version key with a bound of a comparator."""
    bound = loose_key(text)
    if bound is None:
        return False
    if comparator == ">=":
        return key >= bound
    if comparator == "<=":
        return key <= bound
    if comparator == ">":
        return key > bound
    if comparator == "<":
        return key < bound
    return key == bound

def partial_matches(key, token):
    """Check a partial version such as 1, 1.2 or 1.2.x."""
    count = specified_parts(token)
    if count == ZERO:
        return False
    values = [int(part) for part in token.split(PART_DELIMITER)[:count]]
    if count == ONE_PART:
        return key[MAJOR_INDEX] == values[0]
    if count == TWO_PARTS:
        return (key[MAJOR_INDEX] == values[0]
                and key[MINOR_INDEX] == values[1])
    return compare(key, "=", token)

def specified_parts(text):
    """Count the numeric parts before the first wildcard."""
    count = 0
    for part in text.split(PART_DELIMITER):
        if not part.isdigit():
            break
        count += 1
    return count

def loose_key(text):
    """Parse a possibly partial version into a full version key."""
    if PRERELEASE_DELIMITER in text:
        return version_key(text)
    numbers = []
    for part in text.strip().split(PART_DELIMITER):
        if not part.isdigit():
            break
        numbers.append(int(part))
    if not numbers:
        return None
    while len(numbers) < THREE_PARTS:
        numbers.append(ZERO)
    return (numbers[MAJOR_INDEX], numbers[MINOR_INDEX],
            numbers[PATCH_INDEX], (RELEASE_RANK,))
