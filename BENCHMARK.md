# Proofmark accuracy benchmark

<!-- offline:start -->
## Offline mode (exact checks + word lists)

30 drafts, 29 planted errors (standard), 3 hard errors, 5 clean drafts. Run on 29 Oct 2026.

| Measure | Result |
| --- | --- |
| Planted errors caught (recall) | 29/29 = 100% |
| Findings that were real (precision) | 29/29 = 100% |
| False alarms | 0 |
| Hard errors caught (need judgement) | 0/3 |

| Category | Caught |
| --- | --- |
| accessibility | 4/4 |
| claims | 9/9 |
| confidentiality | 1/1 |
| legal | 1/1 |
| terminology | 8/8 |
| tone | 6/6 |

Missed: none

False alarms: none
<!-- offline:end -->

<!-- ai:start -->
## AI mode (exact checks + Gemini `gemini-3.5-flash-lite`)

30 drafts, 29 planted errors (standard), 3 hard errors, 5 clean drafts. Run on 29 Oct 2026.
The AI layer actually ran on 30 of 30 drafts (2 drafts needed a retry after a 429 "too many requests" reply from the free tier).

| Measure | Result |
| --- | --- |
| Planted errors caught (recall) | 27/29 = 93% |
| Findings that were real (precision) | 27/30 = 90% |
| False alarms | 3 |
| Hard errors caught (need judgement) | 2/3 |

| Category | Caught |
| --- | --- |
| accessibility | 4/4 |
| claims | 9/9 |
| confidentiality | 1/1 |
| legal | 1/1 |
| terminology | 8/8 |
| tone | 4/6 |

Missed: #15 TONE-01 "last chance", #17 TONE-03 "bro"

False alarms: #14 TONE-01 "Weekend sale on Volta Buds Air.", #17 MSG-01 "This bass is insane, bro.", #28 MSG-01 "Thanks for choosing Volta Audio."
<!-- ai:end -->

### What the AI results show

Code-checked categories (claims, terminology, legal, accessibility, confidentiality) score the same with or without AI, because the AI never decides them. The AI catches 2 of the 3 hard cases that word lists cannot, but in this run it missed two tone phrases that the word lists catch, and raised three findings we judge to be false alarms. When the AI runs, the tone word lists are not used (`app/engine/scan.py`), which is why those two phrases were missed.

## Limits of this benchmark

The planted errors were written by the team alongside the rules, so this mainly proves the checks work as designed and that clean drafts raise no false alarms. Real drafts will score lower. The hard cases (pressure without listed words, slang not on the list, numbers written as words) show what offline mode cannot catch and why the AI layer exists. Next step: test on real club and agency posts written by people outside the team. AI results come from a single run; the model's answers vary between runs, so these numbers will move a little each time. Whether a finding counts as a false alarm was judged against our own expected list.
