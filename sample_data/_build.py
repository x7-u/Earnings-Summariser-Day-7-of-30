"""Day 7. Generate the bundled synthetic earnings call transcripts.

Three samples that exercise different patterns:
  1. sample_tsla_q1_2026.txt    - Tesla, beat on revenue, Cybertruck ramp commentary
  2. sample_aapl_q4_2025.txt    - Apple, services strong, iPhone soft in China
  3. sample_jpm_q1_2026.txt     - JPMorgan, NII guidance up, IB recovering

Each ~1,500-2,500 words, hand-curated to include:
  - clear speaker tags (Name -- Role: text)
  - guidance phrases ('we expect', 'we are raising', etc.)
  - hedge phrases for the rule detector
  - quantitative claims ($ and %)
  - 4-6 analyst Q&A exchanges with named firms
  - at least one 'we don't break that out' deflection

Round-trips through parse_transcript() and asserts speaker count + word
count before saving.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAY_ROOT = HERE.parent
PROJECT_ROOT = DAY_ROOT.parent
for p in (str(DAY_ROOT), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from transcript_schema import parse_transcript


# ----------------------------------------------------------------------
# Sample 1: TSLA Q1 2026 -- beat on revenue, Cybertruck ramp
# ----------------------------------------------------------------------

TSLA = """\
Company: Tesla, Inc.
Ticker: TSLA
Fiscal Period: Q1 FY2026
Call Date: 2026-04-23

Operator: Good afternoon and welcome to Tesla's first quarter 2026 financial results conference call. As a reminder this call is being recorded. I would now like to turn the call over to Martin Viecha, Vice President of Investor Relations.

Martin Viecha -- Vice President, Investor Relations: Thank you operator. Welcome to Tesla's first quarter 2026 earnings call. Joining us today is Elon Musk, our CEO, and Vaibhav Taneja, our CFO. Before we begin, I would like to remind you that this call may include forward-looking statements. Actual results may differ. With that, I will hand it over to Elon.

Elon Musk -- CEO: Thanks Martin. Q1 was a record quarter for the company on multiple fronts. We delivered 484,000 vehicles, up 4 percent year over year and ahead of consensus. Revenue came in at $24.8 billion, up 7 percent year over year. Automotive gross margin excluding regulatory credits was 18.2 percent, up 90 basis points sequentially. Free cash flow was $1.4 billion. We exceeded our own internal expectations on Cybertruck deliveries, hitting around 18,000 units in the quarter, and we are committed to ramping production further in Q2. Energy storage deployments hit 12.4 gigawatt-hours, an all-time high, up 78 percent year over year. We are confident this is a multi-decade story. On Optimus, we have moved from prototype to limited production in our Fremont line and we will deliver the first units to internal Tesla factory use cases later this year. We expect to begin external customer deliveries in 2027.

Vaibhav Taneja -- CFO: Thank you Elon. A few financial details. Operating income was $1.9 billion, an operating margin of 7.7 percent. Cash and investments at quarter end were $32.4 billion. We expect capex for the full year to be in the range of $11 billion to $13 billion, broadly in line with our previous guidance. We anticipate gross margin improvement in Q2 driven by Cybertruck ramp and operating leverage. On the regulatory credit revenue line, we recognised $445 million, broadly flat sequentially. Operating expenses were $1.6 billion, up 4 percent year over year reflecting our investments in AI compute and Optimus. We are confident we can hold OpEx growth below revenue growth for the balance of the year.

Operator: Thank you. We will now begin the question and answer session. The first question is from Adam Jonas of Morgan Stanley.

Adam Jonas -- Morgan Stanley: Thanks. Elon, on Cybertruck, you mentioned 18,000 units delivered. What is the right run rate to think about exiting Q4? And where does the gross margin on Cybertruck land relative to Model Y by year end?

Elon Musk -- CEO: We expect to be running at around 8,000 to 10,000 units a week by Q4, give or take. So roughly 100,000 a quarter exit run rate. On margin we expect to be at parity with Model Y by mid-2027, possibly earlier if commodity prices stay where they are.

Adam Jonas -- Morgan Stanley: And the Mexico facility?

Elon Musk -- CEO: We are working to break ground in the second half. We are not in a position to give a more specific timeline yet.

Operator: Next question is from Pierre Ferragu of New Street Research.

Pierre Ferragu -- New Street Research: On Optimus, can you size the addressable market in your view, and the unit economics at scale?

Elon Musk -- CEO: I think Optimus will eventually be the most valuable part of Tesla. We are talking about a product that addresses essentially every form of human labour. The unit economics at maturity should give us around 50 percent gross margin. But that is a 5 to 10 year story, not a 1 year story. Near term we are focused on getting to a few thousand units of internal production this year.

Operator: Next question is from Toni Sacconaghi of Bernstein.

Toni Sacconaghi -- Bernstein: Vaibhav, on auto gross margin ex credits, you said 18.2 percent. That is up but still below what some peers print. How should we think about the path back to 25 percent plus?

Vaibhav Taneja -- CFO: We expect ongoing improvement quarter by quarter as Cybertruck scales and as we benefit from the cost reductions on the new factory line in Berlin. We are not going to commit to a quarterly path, but we expect to be back above 22 percent on a quarterly basis by the end of 2026, all else equal.

Toni Sacconaghi -- Bernstein: And the regulatory credit number, can you guide on that for the balance of the year?

Vaibhav Taneja -- CFO: We don't break that out forward looking, but we expect it to be broadly stable.

Operator: Next question is from Dan Levy of Barclays.

Dan Levy -- Barclays: Question on demand. China was strong this quarter. How are you thinking about the second half given the macro and the new domestic competition?

Elon Musk -- CEO: We are seeing some softness in China in April, partly seasonal and partly the macro. We do not see any structural issue with Tesla demand in China. We are confident our refreshed Model Y is well positioned. There is real competition from BYD and others, but that is healthy.

Operator: Next question is from Colin Langan of Wells Fargo.

Colin Langan -- Wells Fargo: On the autonomy roadmap, when do you think you can move from supervised to unsupervised FSD in any market?

Elon Musk -- CEO: Without question we will achieve unsupervised FSD in California and Texas this calendar year. We are running internal trials right now with safety drivers, and the data shows a meaningful improvement quarter over quarter. We are committed to the unsupervised milestone. The robotaxi launch is on track for August.

Operator: Last question is from Mark Delaney of Goldman Sachs.

Mark Delaney -- Goldman Sachs: A two part on capex. The $11 to $13 billion range is wide. What is the swing factor? And does it include anything for the Mexico facility or the next gigafactory?

Vaibhav Taneja -- CFO: The swing is mostly Cybertruck tooling phasing and the AI training compute build-out at Cortex. Mexico is included at a placeholder level. The next gigafactory is not included in this range.

Operator: Thank you. That concludes today's question and answer session. I would now like to turn the call back to Mr Musk.

Elon Musk -- CEO: Thanks everyone. To wrap up, Q1 was a record on multiple metrics, Cybertruck is ramping, energy storage hit a new high, and we are confident in the path to unsupervised autonomy this year. Thanks for joining and we look forward to talking to you on the Q2 call.

Operator: This concludes today's call. You may now disconnect.
"""


# ----------------------------------------------------------------------
# Sample 2: AAPL Q4 FY2025 -- services strong, iPhone soft in China
# ----------------------------------------------------------------------

AAPL = """\
Company: Apple Inc.
Ticker: AAPL
Fiscal Period: Q4 FY2025
Call Date: 2025-10-30

Operator: Good day everyone and welcome to the Apple Q4 fiscal 2025 earnings conference call. Today's call is being recorded.

Suhasini Chandramouli -- Director of Investor Relations: Good afternoon and thanks for joining us. Speaking first today is Apple's CEO Tim Cook, and he will be followed by CFO Luca Maestri. After that we will open the call to questions from analysts.

Tim Cook -- Chief Executive Officer: Thank you Suhasini. Good afternoon everyone. We are pleased to report record Q4 revenue of $94.9 billion, up 6 percent year over year. We delivered an all-time record for services at $25.0 billion, up 14 percent. iPhone revenue was $46.2 billion, up 6 percent year over year, in line with our expectations. Mac revenue grew 1 percent to $7.7 billion, iPad declined 1 percent to $7.0 billion, and Wearables, Home and Accessories was up 2 percent at $9.0 billion. Greater China revenue was $15.3 billion, down 2 percent year over year, reflecting some softness in the consumer electronics market. Apple Intelligence has now rolled out in 25 countries and we are pleased with early engagement. We exited the quarter with around 2.4 billion active devices, an all-time high.

Luca Maestri -- Chief Financial Officer: Thank you Tim. A few details. Gross margin was 46.2 percent, ahead of the high end of our guidance, driven by a richer services mix and favourable foreign exchange. Operating expenses were $14.4 billion. Operating income was $29.6 billion. Cash net of debt was $54 billion. Capex for the year came in at $9.5 billion, slightly below the prior year. Looking forward to Q1 fiscal 2026, we expect total revenue to grow low to mid single digits year over year. We expect services revenue growth to be around the same level as Q4. We expect gross margin to be in the range of 46 to 47 percent. Tax rate around 16.5 percent.

Operator: Thank you. The first question is from Erik Woodring of Morgan Stanley.

Erik Woodring -- Morgan Stanley: Tim, on China. Down 2 percent year over year is better than the market feared but still weak. Can you give us colour on the underlying iPhone trajectory in China and whether you see a path to growth in Q1?

Tim Cook -- Chief Executive Officer: Sure Erik. Greater China revenue was 2 percent down year over year. Excluding the foreign exchange headwind it was actually flat. iPhone in China grew slightly. The macro consumer is still cautious. We are confident in our position with iPhone 17 launches and we expect China to be flat to slightly positive in Q1 on a constant currency basis, all else equal.

Erik Woodring -- Morgan Stanley: And on services growth, 14 percent is great. Sustainable?

Tim Cook -- Chief Executive Officer: We are confident in the trajectory. We expect services to grow at a similar pace in Q1.

Operator: Next question is from Wamsi Mohan of Bank of America.

Wamsi Mohan -- Bank of America: On Apple Intelligence, can you frame the financial contribution? And does it shorten the iPhone replacement cycle?

Tim Cook -- Chief Executive Officer: We are not going to size the financial contribution discretely. What I can tell you is engagement with Apple Intelligence features is strong, and our iPhone 17 mix is skewed more toward Pro and Pro Max than the prior cycle, which is a good signal. We do believe AI will be a tailwind to iPhone over time, but we are not changing our framework on replacement cycles.

Operator: Next question is from Aaron Rakers of Wells Fargo.

Aaron Rakers -- Wells Fargo: Luca, gross margin guidance of 46 to 47 percent for Q1. What is the swing factor?

Luca Maestri -- Chief Financial Officer: We expect commodity costs to be roughly stable. Foreign exchange should be a slight headwind in Q1. The mix benefit from services should continue. We are confident in the 46 to 47 percent range.

Operator: Next question is from Krish Sankar of TD Cowen.

Krish Sankar -- TD Cowen: On Vision Pro, units are still small. What is the strategy from here?

Tim Cook -- Chief Executive Officer: Vision Pro remains an early product. We are committed to the spatial computing roadmap. Near term we are focused on enterprise and developer adoption, where we have seen strong traction. We don't disclose unit numbers for Vision Pro.

Operator: Next question is from Samik Chatterjee of JPMorgan.

Samik Chatterjee -- JPMorgan: On the AI capex required to support Apple Intelligence, you have been described as relatively capital-light versus peers. Will that change?

Luca Maestri -- Chief Financial Officer: We will spend what we need to. Our model relies on a hybrid of on-device intelligence and Private Cloud Compute, which is more efficient than pure cloud inference. We expect FY2026 capex to be modestly higher than FY2025 but not in the same magnitude as the hyperscalers.

Operator: Last question is from Atif Malik of Citi.

Atif Malik -- Citi: On capital return, you bought back $24 billion in Q4. Pace into Q1?

Luca Maestri -- Chief Financial Officer: We will continue to return capital aggressively. We expect to maintain a pace consistent with the run rate. We do not provide explicit quarterly guidance on buybacks.

Operator: Thank you. That concludes the question and answer session. I'll turn the call back to Tim Cook.

Tim Cook -- Chief Executive Officer: Thanks everyone. We are pleased with how FY2025 finished and confident about the year ahead. The combination of a record installed base, Apple Intelligence, and our services momentum gives us a powerful platform. Thanks for joining us today.

Operator: This concludes today's call.
"""


# ----------------------------------------------------------------------
# Sample 3: JPM Q1 FY2026 -- NII guidance up, IB recovering
# ----------------------------------------------------------------------

JPM = """\
Company: JPMorgan Chase & Co.
Ticker: JPM
Fiscal Period: Q1 FY2026
Call Date: 2026-04-12

Operator: Welcome to JPMorgan Chase's first quarter 2026 earnings call. The call is being recorded.

Mikael Grubb -- Head of Investor Relations: Good morning and welcome. With me on the call are Jamie Dimon, Chairman and CEO, and Jeremy Barnum, Chief Financial Officer. As always there are forward-looking statements. With that I will turn it over to Jeremy.

Jeremy Barnum -- Chief Financial Officer: Thanks Mikael. Good morning everyone. The firm reported $14.5 billion of net income, EPS of $5.04, and revenue of $43.6 billion. Return on tangible common equity was 21 percent, an excellent result. Net interest income excluding markets was $23.0 billion, up 2 percent sequentially, slightly above our prior outlook. Investment banking fees were $2.4 billion, up 31 percent year over year, reflecting a recovery in advisory and equity capital markets. Markets revenue was $8.3 billion, down 1 percent year over year. Credit costs were $1.9 billion, including $1.1 billion of net charge offs and an $800 million reserve build. Card net charge off rate was 3.55 percent, broadly in line with our expectations.

For the full year, we are now expecting NII excluding markets to be approximately $93 billion, up from our prior guidance of around $90 billion. The driver is higher cash deployment and the flatter yield curve, partly offset by deposit margin compression. We expect adjusted expense to be around $94 billion. We anticipate the card net charge off rate to be around 3.6 percent for the full year. CET1 ratio at quarter end was 15.4 percent.

Jamie Dimon -- Chairman and Chief Executive Officer: Thanks Jeremy. The firm had an outstanding quarter. Investment banking is showing real recovery, consumer credit is normalising, and our businesses are performing well across the board. I want to make a few comments on the macro and on capital. On the macro, we continue to see strong consumer spend, but lower income consumers are showing signs of fatigue. The labour market is softening at the margins. On geopolitics, the situation in the Middle East and the trade tensions remain a concern. On capital, our CET1 is at 15.4 percent which is well above our 12.5 percent target. We will continue to return capital aggressively. We are confident in our position. We are well capitalised, well reserved, and well positioned.

Operator: Thank you. The first question is from Mike Mayo of Wells Fargo.

Mike Mayo -- Wells Fargo: Jeremy on the NII raise to around $93 billion, that is a $3 billion lift. How much is the curve and how much is the cash deployment? And do you have headroom from here?

Jeremy Barnum -- Chief Financial Officer: Roughly half is the curve, half is the cash deployment. From here, headroom depends on the path of rates. We expect a relatively stable trajectory through the year, all else equal. We are not raising the run rate further at this point.

Operator: Next question is from Glenn Schorr of Evercore ISI.

Glenn Schorr -- Evercore ISI: On investment banking, 31 percent year over year growth. Sustainable into Q2?

Jamie Dimon -- Chairman and CEO: The pipeline is strong. We don't break out the IB pipeline numerically, but I can tell you it is the strongest in 18 months. M&A is healthy and equity capital markets is strong. We expect Q2 to be solid, all else equal.

Operator: Next question is from Steven Chubak of Wolfe Research.

Steven Chubak -- Wolfe Research: On capital. CET1 at 15.4 percent versus your 12.5 percent target leaves a lot of room. Is there any update on capital return given the new Basel III endgame?

Jamie Dimon -- Chairman and CEO: We will continue to return capital aggressively. We are not going to give a specific number this quarter. We are not opposed to special dividends in the right circumstance. The board reviews these things every quarter.

Operator: Next question is from Jim Mitchell of Seaport Research.

Jim Mitchell -- Seaport Research: Credit card net charge off rate guide of around 3.6 percent for the full year. Where does this peak?

Jeremy Barnum -- Chief Financial Officer: We expect the charge off rate to be around 3.6 percent on a full year basis, with some seasonality. We are not comfortable saying we have peaked. We do see the trajectory normalising and we are confident in the underlying credit quality.

Operator: Next question is from Erika Najarian of UBS.

Erika Najarian -- UBS: On expenses. The $94 billion guide implies modest growth from FY2025. What buckets are you investing in?

Jeremy Barnum -- Chief Financial Officer: Volume related, which scales with the business. Tech and modernisation spend, which we are committed to. Marketing in card. And bankers in IB and middle market. We are confident in the operating leverage.

Operator: Last question is from Ebrahim Poonawala of Bank of America.

Ebrahim Poonawala -- Bank of America: On credit reserves. The $800 million build, can you talk about the macro view embedded?

Jeremy Barnum -- Chief Financial Officer: The build reflects volume growth and modest deterioration in our weighted economic scenarios. We are not making a big macro call. We assume a relatively benign baseline with downside scenarios appropriately weighted.

Operator: Thank you. That concludes the question and answer session.

Jamie Dimon -- Chairman and CEO: Thanks everyone. The franchise is performing well. We are confident in the year ahead. Thanks for joining.

Operator: This concludes today's call.
"""


# ----------------------------------------------------------------------
# Build & assertions
# ----------------------------------------------------------------------

def main() -> None:
    out_dir = HERE
    samples = {
        "sample_tsla_q1_2026.txt": (TSLA, "Tesla", "TSLA"),
        "sample_aapl_q4_2025.txt": (AAPL, "Apple", "AAPL"),
        "sample_jpm_q1_2026.txt":  (JPM, "JPMorgan", "JPM"),
    }
    for fname, (text, expected_company, expected_ticker) in samples.items():
        path = out_dir / fname
        path.write_text(text, encoding="utf-8")
        # Round-trip
        doc = parse_transcript(path=path, source_filename=fname)
        assert expected_company.lower() in doc.metadata.company.lower(), (
            f"{fname}: company '{doc.metadata.company}' missing '{expected_company}'"
        )
        assert doc.metadata.ticker == expected_ticker, (
            f"{fname}: ticker '{doc.metadata.ticker}' expected '{expected_ticker}'"
        )
        assert doc.metadata.word_count >= 500, f"{fname}: too short"
        # Expect at least 4 distinct ANALYST speakers
        analysts = {t.speaker for t in doc.turns if t.role == "ANALYST"}
        assert len(analysts) >= 4, f"{fname}: only {len(analysts)} analysts detected"
        # CEO and CFO should both speak
        roles = {t.role for t in doc.turns}
        assert "CEO" in roles, f"{fname}: no CEO turn"
        assert "CFO" in roles, f"{fname}: no CFO turn"
    print(f"Wrote {len(samples)} Day 7 sample transcripts.")


if __name__ == "__main__":
    main()
