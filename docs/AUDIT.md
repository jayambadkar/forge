# Policy audit

The hidden-test score follows the written standards. These notes are an analyst read of the development books against those standards, plus the engine changes that came out of the disagreements. They are not hidden-test labels.

## How the sample was chosen

The first pass was the model’s high-confidence out-of-fold disagreements with the policy, almost all `ESC_PASS_THROUGH` where the model wanted RFI. After that, about ten cases per firm were read across verdicts and reason codes, with the evidence file open next to the firm’s standard.

## Cases read

| Case | Engine before the pass-through change | Analyst read |
| --- | --- | --- |
| EM-CS478666 Val Cranton | Escalate, pass-through | Two consultancy credits, then three payouts to named people, and only a company register. That is a pass-through. Escalate stands. |
| EM-CS388800 Quinn Wenhurst | Escalate, pass-through | Rent in, almost all of it straight out to Coinvale Exchange. Crypto desk. Escalate stands. |
| IV-CS647261 Cameron Lockby | Was about to become an RFI | Two consultancy receipts, nothing invested, £76,484.23 on to Casey Ashgate. Most of what arrived went to another person. Escalate, not a document request. |
| PX-CS251758 Fernhurst Apparel | Escalate, pass-through | Commission file explains the small payees. The £180,704.08 to Thornhurst Industries Co does not. Ask for that invoice. Do not close, and do not treat a missing supplier invoice as suspicion. |
| PX-CS981914 Aldridge Apparel | Escalate, pass-through | Same pattern: the large manufacturer payment is undocumented. RFI for that invoice. |
| PX-CS292464 Whitholt Wine Merchants | Escalate, pass-through | Group chart names Draybrook Holdings and the supplier invoice matches £37,539.66 to Drayton Export Co. Both legs are explained. Close as a group company. |
| BK-CS106820 Elliot Langhurst | Escalate, mule | Two fraud reports from Northgate Bank, plus third-party credits the earlier HMRC review does not cover. Escalate. Do not ask the customer. |

A wider read of closes (own account under five times declared income, returning customer with a reverification record, collection sheets that name the cash amounts, gift letters, invoices that name the corridor) agreed with the engine. List matches with the same birth year stay escalated even when the register says the person resigned. A prior review was not used to close a larger or different payment.

## What was wrong in the engine

Pass-through was the costly bias. Any rapid in-and-out with no single document became `ESC_PASS_THROUGH`, including a business payment to a company that only lacked an invoice. That is an RFI under the standards: suspicion escalates, a missing document does not.

The other miss was the opposite. A payment file, a group chart, or a supplier invoice can explain a leg even when it is not the single largest transaction. Those closes were being thrown away, and then the whole case escalated.

Earlier reviews, the five-times own-account rule, refunds, returning customers and documented third parties were already in the engine for the alert they belong to. The audit checked that a review only covers the party and the amount it states. None of the pass-throughs in the sample met that test, so none were closed on an old bonus or a smaller fee.

## What changed

- A case closes when documents, a group chart or a review name the parties and cover at least three quarters of the value.
- A company payment with no invoice is `RFI_PURPOSE_DOCUMENTS`, and the reason names the payee and the amount to ask for.
- Paying most of what arrived on to a person, splitting at least half of it across three people, or sending it to a crypto desk, stays `ESC_PASS_THROUGH`.
- Fraud reports, structuring without a record of every deposit, an undocumented higher-risk corridor, a confirmed list match and an early redemption with no reason still escalate.
- Reasons name the customer, the document and the amount. An RFI states the question. A second alert adds its own sentence instead of “every alert is covered”.

## Linked cases and the model

Link counts (other cases sharing a counterparty or a device, the share of those cases the policy escalated, and the busiest shared counterparty) were scored with the same 5-fold grouped cross-validation. Each validation fold only saw links from the other training folds. Out-of-fold expected cost was 0.0416 without the links and 0.0422 with them, so they were not kept. They are not loaded into `system/run` either way: the policy still matches its own labels at cost 0, and the hold-out model cost was 0.0325.

## Distribution after the change

| Firm | Close | RFI | Escalate |
| --- | ---: | ---: | ---: |
| Retail bank | 270 | 402 | 328 |
| E-money | 243 | 425 | 332 |
| Investment | 319 | 406 | 275 |
| Payments & FX | 314 | 410 | 276 |

Escalate is 1,211 of 4,000 (30%), down from the 35–44% band. The cases that left escalation are undocumented company payments, which are now requests for the invoice. The mule, crypto, fraud, structuring, corridor and confirmed-list cases above stayed escalated. No previously closed case was reopened by this pass.

## Second sample: RFI against close, e-money and investment

Forty cases, weighted to the boundary between a request and a close, and to the investment rules for early redemption and third-party money. E-money has no early-redemption rule and no third-party funding rule. The reads below are the analyst’s, against the firm’s standard.

Agreed, and left as they were:

| Case | Verdict | Why it stands |
| --- | --- | --- |
| IV-CS793411 Rowan Brommore | Escalate, early redemption | Sold and bought back inside 90 days. The file is only due diligence. No cancellation, redundancy, or completion letter. |
| IV-CS877545 Cameron Everridge | Escalate, early redemption | Same pattern, with a third-party alert as well. Nothing explains the round trip. |
| IV-CS106041, IV-CS147225, IV-CS151648, IV-CS205547, IV-CS206712, IV-CS210761 | Escalate, early redemption | Same document gap on a TM10 alert. Asking the customer would be the wrong step once the units have already been sold with no recorded reason. |
| IV-CS134100 Jordan Brackford | Close, documented event | Email EML-9257 says the holding is being sold because of redundancy. Letter RED on the same file confirms the role ended. The reason now cites the redundancy letter rather than the email. |
| IV-CS143794 Remy Whitholt, IV-CS172933 Frankie Corfield, IV-CS184377 Bailey Margate, IV-CS200003 Sam Oakcote, IV-CS251264 Reese Wencombe | Close, documented event | Each has both the customer’s email and the employer’s redundancy letter. Close is right. |
| IV-CS705905 Morgan Kingsmere | Close, third party documented | Gift letter GFT-1185 names Oakley Kingsmere and £36,167.26. The amount is on the alert. |
| IV-CS809395 Riley Elmhurst | Close, third party documented | Gift letter names Bailey Elmhurst and the amount. |
| IV-CS103503, IV-CS143252, IV-CS145203, IV-CS158538 | Close, third party documented | Gift letter on the customer’s file matches the payer and the figure. |
| IV-CS680956 Riley Garwick | Close, own account | £18,631.68 against a declared £6,050 a month. Under five times, and statement STM-1323 is in their name. The dormant alert is covered by a reverification. |
| IV-CS991674 Jamie Fernden | Close, own account | £10,747.95 against £4,350 a month, statement on file. |
| IV-CS101670, IV-CS104989, IV-CS123071, IV-CS147762 | Close, own account | Same five-times test, statement present, amount underneath it. |
| IV-CS440049 Harper Millgate | RFI, updated profile | £34,584.00 against £4,800 a month. Over five times. The statement shows the account is theirs, which is why this is a profile update and not a source-of-funds request. |
| IV-CS338457 Oakley Thornworth | RFI, updated profile | £37,431.50 against £5,050 a month. |
| EM-CS882268 Jules Norwell | RFI, updated profile | £15,924.05 against £2,150 a month. |
| EM-CS664011 Elliot Wilmere | RFI, updated profile | £22,593.27 against £3,600 a month. |
| EM-CS853626 Bailey Talwick | Close, own account | £3,440.00 against £2,150 a month, statement STM-4090. |
| EM-CS155159 Jamie Elmden | Close, own account | £4,426.50 against £1,950 a month. |
| IV-CS837202 Sam Falcombe | RFI, source of funds | £176,635.14 from Selholt Conveyancing with no completion statement. The question names the firm and the amount. |
| EM-CS226988 Avery Dunwick | RFI, source of funds | £9,718.50 from Falcote Ventures, 11.9 times declared income, register only. |
| EM-CS612586, EM-CS433608 | RFI, counterparty | List match on a name alone. The question asks for a date of birth or a company role. Not a close, and not an escalation. |
| IV-CS309453 Marley Alddale | RFI, counterparty | A gift letter is on file, but the list match on Drew Hollby is still only a name. The case cannot close while that alert is open. |
| EM-CS966997, EM-CS133980 | RFI, purpose | Small unexplained payments (£295 and £320) to a named person, no invoice. A request, not a pass-through. |
| IV-CS700440 Sidney Bramcote | Close, documented event | Insurer letter matches £28,693.15 from Wilbrook Life Assurance. |
| IV-CS684882 | Close, documented event | Completion statement CMP-9802 matches £124,696.36 from Penley Conveyancing. |

Disagreed, and changed:

Forty-five investment cases had a cancellation confirmation for an ISA subscription paid in and returned, in the customer’s own name, inside the cancellation window. The engine treated the missing bank statement as the whole story and asked for source of funds. The letter is the explanation. Kit Selstead, IV-CS843735, is the pattern: CAN-1024 returns £22,439.18, and both the subscription and the refund are that amount. The same shape is IV-CS112234, IV-CS133528, IV-CS190128, IV-CS218629, IV-CS228470, IV-CS233333, and IV-CS249863, and the other 38 letters of the same type. They now close as `REFUND_OF_EARLIER_PAYMENT`. No other firm’s counts moved. Early-redemption cases with no letter stayed escalated. Gift-letter cases stayed closed. The five-times own-account line was already in the right place.

## Third sample: escalate against RFI, and e-money closes

Forty cases on the bank and payments books where the choice is escalate or ask, plus e-money cases on the line between a request and a close.

Agreed, and left as they were:

| Case | Verdict | Why it stands |
| --- | --- | --- |
| BK-CS573572 Quinn Corholt | Escalate, higher-risk corridor | £15,798.16 to or from Lebanon. The file is support chat and proof of address. No invoice names Lebanon or the amount. |
| BK-CS951041 Avery Draymore | Escalate, higher-risk corridor | £7,816.63 and Lebanon. A venue email does not mention the corridor. |
| BK-CS313193 Harper Cranmore | Escalate, higher-risk corridor | £7,601.97 and Lebanon. Same gap. |
| PX-CS700035 Stanley Timber Supplies | Escalate, higher-risk corridor | £8,676.82 and Lebanon. A credit note is on file and does not match that payment. |
| PX-CS930859 Halford Wine Merchants | Escalate, higher-risk corridor | £6,904.71 and Lebanon. No invoice. |
| PX-CS753154 Thornholt Apparel | Escalate, higher-risk corridor | £6,019.31 and Lebanon. No invoice. |
| PX-CS128520 Penley Engineering | Close, invoice matches | INV-4776 names Wenstead Dried Fruits and £29,091.82 on the Iraq payment. |
| PX-CS839636 Wenley Wine Merchants | Close, invoice matches | INV-9518 matches £19,798.34. |
| PX-CS273826 Thornford Furniture | Close, invoice matches | INV-8055 matches £22,282.79. |
| PX-CS333800 | Escalate, invoice mismatch | Payment of £72,774.06 to Normere Manufacturing. INV-3487 names that supplier and states £40,508.41. The invoice does not support the payment. |
| PX-CS411851 | Escalate, invoice mismatch | £33,629.29 to Lynstead Trading against an invoice for a different amount. |
| BK-CS866775 Noel Thornwell | Escalate, mule | Kestrel Mutual fraud report RPT-3935 asks for the funds to be frozen, next to rapid movement. Not a question to the customer. |
| BK-CS886842 Frankie Brackden | Escalate, mule | Wexmoor Bank fraud report RPT-3584. |
| BK-CS447607 Dale Selmere | Escalate, mule | Kestrel Mutual fraud report RPT-2727. |
| BK-CS835441 | Escalate, listed party | Peyton Marstead, birth year 1968 agrees with the register. A resignation date does not make this a different person. |
| BK-CS911030, BK-CS487446 | Escalate, listed party | Birth years 1973 and 1968 agree. |
| PX-CS819855, PX-CS784833, PX-CS276080 | Escalate, listed party | Same pattern: the register year matches the list entry. |
| BK-CS103088, BK-CS128915, BK-CS686131 | RFI, counterparty | List hit on a name only. The question asks for a date of birth or a company role. |
| PX-CS388903, PX-CS348882 | RFI, counterparty | Name-only list match. |
| PX-CS309156 Glenmore Electronics | RFI, counterparty | £81,382.99 from Whitmere Invoice Finance with no document of the relationship. Ask, rather than escalate: there is no fraud report and no pass-through. |
| BK-CS783731, BK-CS597823, BK-CS173234 | RFI, source of funds | Cash credits labelled CASH DEPOSIT, over the declared income, and no sale receipt or takings sheet. |
| PX-CS565846, PX-CS868311, PX-CS945417 | Escalate, structuring | Four cash amounts just under the line and no takings book or collection report at all. |
| EM-CS583181 Cameron Selley | RFI, source of funds | £725 in their own name and no statement. |
| EM-CS737181 Nico Aldholt | RFI, source of funds | £11,475 in their own name and no statement. |
| EM-CS405213 Hayden Lynmore | RFI, source of funds | £17,537 from Radwell Logistics, about five times income, no invoice. |
| EM-CS701722, EM-CS757033, EM-CS398270 | RFI, purpose | Unexplained payments of £295, £2,590 and £210. No invoice. Not enough to call it a mule. |
| EM-CS395098 Hayden Thorngate | Close, documented event | Bike sale receipt SAL-5537 matches the £1,100 cash. |
| EM-CS160860 Nico Wilridge | Close, documented event | Settlement letter SET-300 matches £11,300 from Drayhurst Logistics. |
| EM-CS838069 Elliot Hollwell | Close, documented event | SET-7062 matches £10,225.50 from Lynridge Logistics. |
| EM-CS200858 Sasha Thornley | Close, own account | £4,440 against £2,400 a month, statement STM-5671. |
| EM-CS355138 Val Talmere | Close, own account | £5,253 against £2,550 a month, statement STM-1056. |
| EM-CS426016 Kai Wildale | RFI, updated profile | £25,213.52 against £3,550 a month. Over five times, and the statement shows the account is theirs. |
| EM-CS842338 Sidney Hartholt | RFI, updated profile | £16,734.46 against £2,200 a month. |
| BK-CS308767 Falmere Parking | Close, collection documented | COL-9620 lists the same four cash amounts. The company is named on that report, so this one already closed. |

Disagreed, and changed:

Bank festival reconciliations and e-money takings books list every cash deposit to the penny, and they are filed on that customer, but they print the gate or the day rather than the legal name. The engine was escalating them as structuring. Stanwick Events, BK-CS350099, is the pattern: REC-2262 shows £9,670, £9,130, £9,680 and £9,785, which are the four deposits. The same shape is Bromworth Events BK-CS107843, Wilridge Events BK-CS113067, Nordale Events BK-CS115751, Everley Events BK-CS120040 and Garworth Events BK-CS128550. On e-money the daily takings book does the same job: EM-CS118938 Riley Aldstead, EM-CS120346 Riley Lyndale, EM-CS141407 Marley Aldton and EM-CS146899 Morgan Thornley. Thirty-eight bank cases and forty-six e-money cases moved from `ESC_STRUCTURING` to a close against the book. Payments and FX had no sheet that matched every deposit, so those 107 escalations stayed. A corridor with no invoice, a real invoice mismatch, a fraud report, and a list match with the same birth year were not moved.

## Close paths, and what is too weak

A wrong close costs ten. Each close path was counted on the development book and the weakest evidence it will accept was written down. Paths were then checked for a near-miss: figures that match, on a document that is not about this customer’s trade.

| Path | Cases | Weakest evidence that still closes |
| --- | ---: | --- |
| Documented event | 530 | A party named on the payment is named in the document, and the amount is within 2%. |
| Own account | 405 | The counterparty is the customer, a bank statement contains their name, and the amount is under five times the declared figure. |
| Invoice matches | 42 | The invoice names the payee and the amount, and for a corridor it also names the country. |
| Collection documented | 39 | Every cash amount is within 1% on a collection or ticket report that names the customer. |
| Business records | 84 | Every cash amount is on a sheet filed on this customer, and the sheet names them or shares a word with their occupation, business or employer. |
| Third party documented | 45 | A gift letter names the payer and the amount. |
| Refund of an earlier payment | 45 | A cancellation or credit note on the customer’s file matches the amount within 2%. |
| Returning customer | 55 | A reverification record is on the file for a dormant-account alert. |
| Group company | 30 | The group chart contains the counterparty’s name. |

The till-sheet path was the weak one. Matching figures on any sheet filed for the customer was enough, so a librarian with a festival reconciliation that happened to use the same amounts would have closed. The sheet now has to name the customer, or share a word with their occupation, business or employer. Generic sheet words (cash, takings, gate, report) do not count. All 84 development closes still meet that test: the festival sheets say “festival”, which is the customer’s business, and the market traders’ takings books say “market”. An unrelated sheet with the same amounts now escalates. No development verdict moved.

The engine source does not key on development case ids, customer names, or one-off amounts. A development brand that had been listed next to the generic words for a crypto desk was removed; the generic word “exchange” still covers that pattern, and rescoring changed nothing. Synthetic cases, not development rows, cover each close, request and escalation in `tests/test_sop_paths.py`.
