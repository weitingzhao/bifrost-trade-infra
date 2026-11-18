# Hard-coded facts in Ops source (law 30, Owner 2026-11-17): a string literal,
# or JSX text, carrying a date, a state word, or a written-down ratio or count.
# Prints "<file>:<line>: [<kind>] <text>"; scan.sh counts the lines.
# A proxy: it catches some honest text and misses a hand-kept list. Only the
# trend is read. Runs under BSD awk and busybox awk (the CI image), so no gawk.
function emit(text, kind) {
  print FILENAME ":" FNR ": [" kind "] " text
}
function classify(text,   t) {
  gsub(/\$\{[^}]*\}/, "X", text)
  t = " " text " "
  gsub(/2006-01-02/, "", t)
  if (t ~ /20[0-9][0-9]-[01][0-9]-[0-3][0-9]/) { emit(text, "date"); return }
  if (text ~ /^[ ]*[A-Za-z]+( [a-z]+)?[ ]*$/ && text !~ / /) return
  if (t ~ /[^A-Za-z](CLOSED|Closed|SIGNED|Signed|BLOCKED|Blocked|PLANNED|Planned|planned|[Nn]ot yet|LIVE|Live|READY|Ready|DONE|Done|LANDED|Landed|SHIPPED|Shipped)[^A-Za-z]/) {
    if (text ~ / /) { emit(text, "state"); return }
  }
  if (t ~ /[^A-Za-z0-9\/._:-][0-9]+\/[0-9]+[^A-Za-z0-9\/._:-]/) { emit(text, "count"); return }
  if (t ~ /[^A-Za-z0-9.\[-][0-9]+ (of [0-9]+|moved|left|remaining|passed|failed|landed|fixed|green|red|repos?|items?|lanes?|seats?|cards?)[^A-Za-z-]/) { emit(text, "count"); return }
}
FNR == 1 { inblock = 0 }
{
  line = $0
  if (inblock) { if (line ~ /\*\//) { sub(/^.*\*\//, "", line); inblock = 0 } else next }
  if (line ~ /^[ \t]*(\/\/|\*)/) next
  if (line ~ /^[ \t]*\/\*/) { if (line !~ /\*\//) { inblock = 1 }; next }
  rest = line
  while (match(rest, /"([^"\\]|\\.)*"|'([^'\\]|\\.)*'|`[^`]*`/)) {
    lit = substr(rest, RSTART + 1, RLENGTH - 2)
    classify(lit)
    rest = substr(rest, 1, RSTART - 1) " " substr(rest, RSTART + RLENGTH)
  }
  if (FILENAME ~ /\.tsx$/) {
    gsub(/=>|->|>=|<=/, " ", rest)
    sub(/\/\/.*$/, "", rest)
    while (match(rest, />[^<>{}]*[A-Za-z][^<>{}]*</)) {
      lit = substr(rest, RSTART + 1, RLENGTH - 2)
      classify(lit)
      rest = substr(rest, RSTART + RLENGTH - 1)
    }
  }
}
