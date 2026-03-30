# Issue Heuristics

## repetition
Detect repeated normalized token spans of length 1-8 within a short time window.

## false_start
Detect a short unmatched phrase immediately followed by a restarted phrase that overlaps the same anchor words.

## pickup_restart
Detect where the narrator backs up and rereads from an earlier anchor phrase.

## substitution
Detect stable spoken/manuscript mismatch where aligned neighbors match.

## missing_text
Detect expected manuscript span with no spoken counterpart.

## long_pause
Detect silence above threshold between spoken spans, excluding obvious paragraph/sentence pauses where possible.

## uncertain_alignment
Use when local alignment quality is poor or timestamps are weak.
