# CP-86 reader fixtures

`manifest.json` records SHA256 and expected citation facts for unmodified,
real archived bodies: three CP-81 stranger captures and CP-82's fresh
capture. These contain the demo's fictional case/decision material; all
four were accepted when captured. Tests check bytes and show/export/census.

| capture | known result |
| --- | --- |
| CP-81 `b4422728` | 2 section hits, 1 ungrounded `dec:GREV000082013:rn:7` |
| CP-81 `8c56edb3` | 5 hits, no dec: tokens (silent with hits available) |
| CP-81 `9978ad7c` | 5 hits, no dec: tokens (silent with hits available) |
| CP-82 `fd3217b4` | 5 hits, no dec: tokens (silent with hits available) |

**Missing proof:** CP-81's two rehearsal bodies (`dd62726f…`, `c2aeed8a…`)
were not found in local repositories or preserved scratch directories at
CP-86. CP-81 reports five hits and no dec: tokens in each. That historical
report is not a new corrected-reader execution, and no synthetic replacement
is represented as a real capture. The five-CP-81-body obligation is incomplete.
`waiting-on: recovery of both original rehearsal bodies with provenance, then
byte-frozen fixtures and corrected show/export/census readings for each`.

`synthetic-reordered.json` and `synthetic-failed-write.json` preserve CP-82's
executed synthetic fixtures derived from its fresh capture. The first has
read/read1 and decisions/dec1 calls with reversed result order and a known
valid citation. The second has write/write1 followed by EACCES and known
attempted content. `synthetic-missing-result.json` removes dec1's result and
adds a labelled orphan result before the assistant. Their token arrays still
belong to the source capture: these test consumer projection, never capture
fidelity or gate acceptance. Further test-local mutations cover duplicate
IDs, delayed results, missing/unknown writes and explicit error flags.
