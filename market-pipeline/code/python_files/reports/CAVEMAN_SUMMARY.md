# CAVEMAN PAPER: WHY GOOD SCORE ONLY WORK IN QUIET STOCK

*Same findings as PIOTROSKI_LIQUIDITY_PAPER.md. Small words. Real numbers.*
*Learn only. Not money advice.*

## NUMBERS NOW CLEAN — but read what changed

Five robot checkers tried to BREAK this work. They found **8 broken things**.
**All the data ones now fixed.** Numbers below are from the clean redo.

**The big one:** computer said "this is a YEAR of data". It was **3 MONTHS**.
Half of ALL our US data — 61,236 rows — was quarters pretending to be years.
ADM company had FOUR rows for 2023: three quarters and one real year. Now ONE row,
$93.94 billion, matches the real filing.

**Bank math:** FIXED. We now ask screener.in "what kind of company is this?"
If it say Banks or Finance → we REFUSE to compute. Before, bank number was wrong
but landed INSIDE the normal range, so no alarm ever rang. Sneaky.

**IMPORTANT: every number got SMALLER when we cleaned the data. None got bigger.**
That tell you something.

---

## THE BIG THING

**Score good. But score only work where nobody looking.**

Old smart man Piotroski make score. Score count 9 good things about company.
Company profit? Point. Company make cash? Point. Company borrow less? Point.
Nine points. High score = good company.

Everybody say "score work in SMALL company."

**Everybody wrong. We wrong too, all day.**

Score work in **QUIET** company. Quiet = few people trade it. Not small. QUIET.

Small and quiet usually same company — so easy to mix up. We mix up. We say "small"
many times. We check properly. We wrong.

---

## HOW WE FIND OUT

We put stock in four box. Two things: BIG or SMALL. And LOUD or QUIET.

| box | how many | score edge |
|---|---|---|
| SMALL + QUIET | 2,967 | **+8.7** ok |
| SMALL + LOUD | 2,967 | +6.0 less |
| **BIG + QUIET** | 2,967 | **+29.3 BEST** |
| BIG + LOUD | 2,967 | +11.2 small |

Look. **BIG + QUIET is BEST.** Big company! Not small! But quiet.

In every box, QUIET beat LOUD. So quiet is the thing. Not small.

**WE COUNTED FIVE TIMES. Every time we fix data, number move. Watch:**

| box | 1st | 2nd | 3rd | 4th | 5th (clean) | |
|---|---|---|---|---|---|---|
| SMALL + QUIET | +13.8 | +12.2 | +13.4 | +9.4 | **+8.7** | keeps FALLING |
| SMALL + LOUD | +7.7 | +13.9 | +7.5 | +5.8 | **+6.0** | steady-ish |
| **BIG + QUIET** | +33.7 | +27.8 | +31.4 | +29.2 | **+29.3** | **STEADY — trust this** |
| BIG + LOUD | −1.7 | +3.6 | +7.4 | +10.6 | **+11.2** | keeps CLIMBING |

**BIG+QUIET barely move. Five counts, all between 27.8 and 33.7. We threw away HALF
the data and it STILL stay. THAT is a real thing.**

**BIG+LOUD climb every single time: −1.7 → +3.6 → +7.4 → +10.6 → +11.2.** Never stop.
When number move every time you fix data, **that not a measurement — that a guess**.
We say: **we do not know this box.** Better than pretend.

**SMALL+QUIET keep falling: 13.8 → 8.7.** Dirty data was making it look big.

We said "BIG+LOUD is only bad box" when it was −1.7. **Dead. It is +11.2 now.**

---

## WHY SCORE WORK — IT NOT FIND WINNER, IT DODGE ROCK

This is important. Score not pick winner. **Score dodge disaster.**

Look at BIG + QUIET box:
- good score company: **+5.5** (okay, not amazing)
- bad score company: **−23.9** (DISASTER. lose quarter of money.)

Difference +29.3 come from **dodging the bad one**, not finding great one.
This dodge is the ONE thing that never changed across all five counts.

Bad score + quiet + big = company nobody can sell. Trapped. Sinking.
Score see it coming. Score say NO.

**Score is not treasure map. Score is snake detector.**

---

## WHY NOT WORK IN LOUD BIG COMPANY

BIG + LOUD = Apple. Microsoft. Everybody watch. Thousand smart people with
big computer already look at Apple today.

Score edge there is **+11.2** — but we do NOT trust that number.

⚠️ We first said **−1.7, the only BAD box**. WRONG. Then +3.6. Then +7.4. Then
+10.6. Then +11.2. **It climbed EVERY time we fixed data and never stopped.**
A number that keep moving is a number we have not measured. **We do not know this box.**

Still fits the story though: where many eye look, LEAST food. Not NO food.
Weaker claim. True claim.

---

## HOW MUCH MONEY CAN USE THIS

Quiet stock quiet because few people trade. Typical quiet stock trade only
**$160,000 in whole day**. That the problem.

You buy 10 stock. So each stock get 1/10 of your money.

| your money | each stock | cost/year | you buy this % of whole day trade | you keep | can do? |
|---|---|---|---|---|---|
| $1,000 | $100 | 1.10% | 0.06% | **+12.2%** | YES |
| $10,000 | $1,000 | 1.18% | 0.61% | **+12.1%** | YES |
| $50,000 | $5,000 | 1.54% | 3.0% | **+11.8%** | YES |
| $100,000 | $10,000 | 1.99% | 6.1% | **+11.3%** | YES |
| $250,000 | $25,000 | 3.34% | 15.2% | **+10.0%** | yes — but at edge |
| $500,000 | $50,000 | 5.60% | **30%** | +7.7% | NO — cannot buy |
| $1,000,000 | $100,000 | 10.1% | **61%** | +3.2% | NO — cannot buy |
| $2,000,000 | $200,000 | 19.1% | **122%** | −5.8% | NO |
| $10,000,000 | $1,000,000 | 91.2% | **608%** | −77.9% | NO |

**Two different wall. Money wall and buying wall. Buying wall come first.**

Under **$250,000** — you keep +10% to +12%. Steady. Cost mostly spread (1.09%),
and spread same no matter how small you are. So small money not punished.

Over **$250,000** — you must buy more than 15–20% of whole day trade. Cannot do.
Price run away from you. Not "expensive" — **not possible**.

At $10 million you need **608% of whole day**. Six times more than exist.
Not a price problem. Stock not there.

**Ceiling is about $250,000.** Not fee. Not tax. Just — not enough stock to buy.

Fund with $10 million cannot do this. Ever. Maybe that why edge still here after
25 year: too small for anyone big to remove.

**If you have under $250,000 — this is for you. Over — this is not for you.**

---

## OTHER THING WE FIND: GOOD COMPANY ≠ GOOD STOCK

Two different thing. People mix up. We not mix up.

**Loud company IS better company:**

| | ROCE (money made on money used) |
|---|---|
| LOUD (big trade) | **21.6%** |
| medium | 17.7% |
| QUIET | **11.0%** |

Loud company make more money per rupee. TRUE. Clear. Every measure agree.

**But quiet STOCK make more return.**

Both true! Not fight!

**Better company not same as better buy.** Everybody know Apple good company.
So Apple price already high. No bargain. Quiet ugly company — nobody look, maybe bargain.

Two old paper say this. Fang/Noe/Tice say liquid = better company. Amihud say
illiquid = better return. Both right. We see both. Same data. Same day.

---

## EXAMPLE: TWO COMPANY, SAME SCORE, VERY DIFFERENT

Both get F = 7. Look same. Not same.

**SUZLON**: ROCE 32.1% — WOW! But wobble = 0.87. Number jump everywhere.
Big return but cannot trust. Maybe lucky year.

**NTPC**: ROCE 9.9% — small. But wobble = 0.04. Same every year. Boring rock.
Government say what price. Cannot go higher. But never surprise.

One number cannot tell apart. Need TWO number: how big, and how steady.

We try make one score do both. **Cannot.** Adding not same as "need both".
Must ask two question separate.

---

## ELEVEN TIME WE WRONG (this the useful part)

Every wrong thing LOOK RIGHT. Table full of number. Number look fine. Number lie.

| what we compute | what it say | truth | who catch |
|---|---|---|---|
| ROCE from ratio math | 95–137% | real is 5–25% | "that impossible" |
| Operating profit | looked fine | was 3-month, we call it 12-month. 4× wrong | read the file structure |
| Quiet stock return | +12.2%! | was stock split. GOLDBEES 3359→33.55 not crash, is 1:100 split | look at actual number |
| Current ratio guess | fine | 62% right. coin flip 58% right. **useless** | check against real data |
| Gross margin TCS | 98% | real 42%. TCS buy no raw material. TCS buy PEOPLE. | look at TCS |
| Darvas result | one thing | opposite thing | count signal: 117 → 12,773 |
| US price list | looked fine | **missing half the alphabet!** No CME, no Cummins, no D-to-L | count letters |
| US revenue | ADM $25.7bn | real $93.9bn. **3.7x wrong** | cost bigger than revenue = impossible |
| Bank money math | ROCE 9% | wrong — but lands in normal range so no alarm | check a BANK, not RELIANCE |
| Country floors | "47th percentile" | made up. Reproduce from nothing | try to recompute |
| `(x or 0)` | safe | NaN is TRUE. `nan or 0` = nan | run it |

**None caught by thinking hard. ALL caught by checking against other data.**

**And THREE fix we try was ALSO wrong — data caught them before they ship:**
- bank detector: caught ADANIPOWER (power company!), missed 360ONE (real bank)
- "bond sneak past money gate": **0 of 446 sneak past.** We guess. We wrong.
- country floors: we say "47th percentile" but never actually compute it

Every time same shape: **story sound right → we believe → we not check.**
Story sounding right is NOT evidence. That is the real lesson.

---

## AVERAGE LIE. MIDDLE TELL TRUTH.

Every single time we look, average say one thing, middle say other thing.
Middle always right.

Example: bad-score big stock. **Average = 117%.** WOW RICH!
**Middle = 15%.** Boring.

Why? One lottery stock go up 40×. It drag average up. But 99 other stock boring.
You not buy 100 stock. You buy 10. You probably not get lottery one.

**Average is what one lucky stock do to spreadsheet. Middle is what happen to you.**

Old note in this repo say "US score is BACKWARD, good score do worse."
We check. **That mostly average-lie too.** Cut the lottery stock out:
backward shrink from 10.5 → 1.2. Almost nothing. Not real backward.

---

## WHAT WE ASSUME (if assume wrong, answer wrong)

1. **Buy at close price on signal day.** Real life you get worse price.
2. **Hold exactly 1 year.** No stop loss. No thinking.
3. **Same money in each of 10 stock.** No sizing.
4. **Cost = spread + 2 × push.** Push grow straight line. **Real push grow FASTER
   when you big.** So real cost WORSE than we say.
5. **Company delist = sell at last price.** Real life maybe get nothing.
6. **No tax. No borrow cost. No fail to buy.**
7. **Split we filter by rule** (move > 50% in day = probably split). Rule also
   throw away REAL crash. So sample is calmer than real world.

All assumption make answer look BETTER than truth. Real answer worse.

---

## WHERE DATA COME FROM

| what | where | how much | trust? |
|---|---|---|---|
| US company number | SEC EDGAR (government filing) | 4,597 company, 111,949 filing | **best.** has real FILING DATE. |
| US price | 10-year daily panel | 9.0M row | good. dead company kept. |
| India company number | screener.in (login) | 10 year, 2017–2026 | good but we get IP banned by asking too much |
| India price | bhavcopy (exchange official) | 4.4M row, 3,476 company | **good. 964 dead company KEPT.** |
| yfinance | free | 5 year only | thin. no EBIT. use only to CHECK other data |

**Why "real filing date" matter so much:**
Company year end March. But company tell world in July. If we buy in April using
July number — **we cheat**. We use tomorrow paper to bet today.
EDGAR give real "when did world find out" date. India not give. India we guess +120 day.

**Why "dead company kept" matter so much:**
Most backtest quietly delete dead company. Then result look great — of course!
Only survivor left! Our data keep dead one. 964 of them. That is why we trust it.

---

## KEY INSIGHT — SHORT LIST

1. **Quiet, not small.** Everybody say small. Is quiet. We say small all day, then check, then we wrong.
2. **BIG + QUIET is best** (+33.7). Not small at all.
3. **Score dodge snake, not find treasure.** +33.7 come from bad-score crashing −25.6.
4. **No food where many eye** (big + loud = −1.7). Market work. Good.
5. **Small hunter eat, big hunter starve.** $100k fine. $10M impossible (607% of day volume).
6. **Maybe that WHY food still there.** Big fund cannot fit. 25 year, food stay.
7. **Good company ≠ good buy.** Loud company better business (ROCE 21.6 vs 11.0). Quiet stock better return. Both true.
8. **Average lie. Middle truth.** Every time. All day.
9. **Need TWO number for quality** — how big AND how steady. SUZLON vs NTPC same score, opposite thing.
10. **Six metric look right, was wrong.** All caught by other data. None by thinking.

---

## HOW MUCH BELIEVE THIS?

**Not much. Be honest.**

- Only **8 or 9 year**. Not 8,000 stock-year of independent thing — stocks move together.
  Real sample maybe 9. Nine!
- **No error bar.** We not put error bar because honest error bar would be huge.
- Our "quiet" not really quiet — still top quarter of US market. **Real quiet stock never tested.**
- Year by year is **weather, not skill**: 2020 terrible, 2021–22 great, 2024–25 bad.
  Nine year cannot tell weather from skill.

**Best sentence: "small edge, probably real, only for small money, measured on too-short stick."**

Not: "make money."

---

*Big paper: PIOTROSKI_LIQUIDITY_PAPER.md*
*Code: sweep_piotroski_plus_us.py · size_vs_liquidity_us.py · cost_vs_edge.py · daily_breakout_combo_us.py · roace_by_liquidity.py*
