"""Seed content for BizReady.

Eight business components, a 24-question diagnostic, and one fully built
learning module (Business Strategy & Model) with lessons, quiz, scenario
test, practical assignment and downloadable templates.
"""

COMPONENTS = [
    {
        "id": "strategy",
        "name": "Business Strategy & Model",
        "short": "Strategy",
        "description": "Know who you serve, why they choose you, and how the money works.",
        "topics": ["Customer segments", "Value proposition", "Revenue & cost model", "Break-even", "Priorities & KPIs"],
        "available": True,
    },
    {
        "id": "marketing",
        "name": "Marketing & Sales",
        "short": "Marketing",
        "description": "Reach the right customers, make a clear offer, and sell consistently.",
        "topics": ["Customer research", "Offer & pricing", "Channels that fit", "Follow-up & repeat sales", "Social proof"],
        "available": False,
    },
    {
        "id": "operations",
        "name": "Operations & Quality",
        "short": "Operations",
        "description": "Deliver the same good result every time, without chaos.",
        "topics": ["Process mapping", "Quality checks", "Capacity & scheduling", "Suppliers", "Waste & rework"],
        "available": False,
    },
    {
        "id": "finance",
        "name": "Financial Management",
        "short": "Finance",
        "description": "Read your numbers, protect cash, and price for profit.",
        "topics": ["Bookkeeping basics", "Cash-flow forecasting", "Margins", "Pricing for profit", "Tax readiness"],
        "available": False,
    },
    {
        "id": "people",
        "name": "People & Leadership",
        "short": "People",
        "description": "Build a small team that knows what good looks like.",
        "topics": ["Roles & expectations", "Hiring & onboarding", "Training", "Feedback", "Rosters & fairness"],
        "available": False,
    },
    {
        "id": "systems",
        "name": "Systems & SOP",
        "short": "Systems",
        "description": "Write down how work gets done so quality does not depend on you.",
        "topics": ["SOP writing", "Checklists", "Handover", "Simple tools", "Review cycles"],
        "available": False,
    },
    {
        "id": "legal",
        "name": "Legal & Risk",
        "short": "Legal",
        "description": "Cover the basics: licences, contracts, insurance and records.",
        "topics": ["Licences & permits", "Customer terms", "Supplier contracts", "Insurance", "Record keeping"],
        "available": False,
    },
    {
        "id": "digital",
        "name": "Digitalisation & Growth",
        "short": "Digital",
        "description": "Use simple digital tools to sell, track and grow without adding chaos.",
        "topics": ["Online presence", "Selling online", "Payments", "Simple automation", "Metrics that matter"],
        "available": False,
    },
]

COMPONENT_BY_ID = {c["id"]: c for c in COMPONENTS}

DIAGNOSTIC_RECOMMENDATIONS = {
    "strategy": "Start with the Business Strategy & Model module: define one primary customer, write your value proposition, and calculate contribution per sale.",
    "marketing": "Write down your single best customer group and the one offer you want them to buy. Then track where enquiries come from for two weeks.",
    "operations": "Map your busiest process on one page, mark the two points where mistakes happen, and add a simple check at each point.",
    "finance": "Separate fixed and variable costs, then calculate your break-even sales. Review cash in and cash out weekly.",
    "people": "Clarify each role in one page: what good looks like, what decisions they can make, and who checks quality.",
    "systems": "Turn your most repeated task into a one-page checklist and test it with someone else doing the task.",
    "legal": "List the licences, contracts and insurance your business depends on, and note the renewal dates in one place.",
    "digital": "Choose one digital channel, measure cost per order and repeat orders for 30 days, and drop anything you cannot measure.",
}


def q(qid, component, kind, topic, prompt, options, correct, explanation):
    return {
        "id": qid, "component": component, "kind": kind, "topic": topic,
        "prompt": prompt, "options": options, "correct": correct,
        "explanation": explanation,
    }


DIAGNOSTIC_QUESTIONS = [
    # Strategy
    q("d-str-1", "strategy", "diagnostic", "Value proposition",
      "A customer asks why they should buy from you rather than the shop next door. Which is the strongest answer?",
      ["We are always the cheapest.",
       "We solve a specific need for a specific customer, better than the alternatives they have.",
       "We have been open for many years.",
       "We post regularly on social media."],
      1, "A clear reason tied to a defined customer and their alternatives is a value proposition. Price alone is easy to copy and often destroys margin."),
    q("d-str-2", "strategy", "diagnostic", "Profit & break-even",
      "Monthly sales are RM30,000, variable costs RM18,000 and fixed costs RM9,000. What is your profit?",
      ["RM12,000", "RM3,000", "RM9,000", "RM21,000"],
      1, "Profit = sales − variable costs − fixed costs = 30,000 − 18,000 − 9,000 = RM3,000. Many owners stop at gross profit and miss fixed costs."),
    q("d-str-3", "strategy", "diagnostic", "Priorities & KPIs",
      "Which goal can actually be managed week by week?",
      ["Increase sales.",
       "Grow revenue 15% in 90 days by adding two corporate lunch accounts, reviewed every Friday.",
       "Become the best food business in town.",
       "Work harder on marketing."],
      1, "A manageable goal names a measure, a target, a time frame and a weekly review. The others cannot tell you whether you are on track."),
    # Marketing
    q("d-mkt-1", "marketing", "diagnostic", "Channels",
      "Your food stall is busy at lunch but empty at 3pm. What is the best first step?",
      ["Cut prices across the whole menu.",
       "Design a small afternoon offer for nearby office workers and measure uptake for two weeks.",
       "Open a second stall.",
       "Buy more equipment."],
      1, "Test one specific offer with one specific group and measure it. That gives you evidence before you spend more."),
    q("d-mkt-2", "marketing", "diagnostic", "Customer focus",
      "Which customer group should your marketing focus on?",
      ["Everyone in the city.",
       "A defined group with a shared need you can serve profitably.",
       "Whoever is cheapest to reach.",
       "Friends and family."],
      1, "A defined group lets you choose a message, a channel and an offer that actually fits. 'Everyone' means no one in particular."),
    q("d-mkt-3", "marketing", "diagnostic", "Communication",
      "A regular customer says: 'I didn't know you delivered.' What does this most likely show?",
      ["Your product is poor.",
       "A gap in how you communicate what you offer.",
       "You need a new logo.",
       "You should lower your prices."],
      1, "Customers cannot buy what they do not know about. It is a communication gap, not necessarily a product problem."),
    # Operations
    q("d-ops-1", "operations", "diagnostic", "Process",
      "Orders get mixed up during the lunch rush. What is the most reliable fix?",
      ["Document the order flow and add one simple checking step at handover.",
       "Hire more staff immediately.",
       "Ask customers to be patient.",
       "Stop taking phone orders."],
      0, "A clear flow with a check at the point where errors happen fixes the cause. More staff can simply add more confusion."),
    q("d-ops-2", "operations", "diagnostic", "Quality",
      "What is the main purpose of a quality check at the point of handover?",
      ["Catch problems before the customer sees them.",
       "Impress inspectors.",
       "Slow the team down.",
       "Create paperwork."],
      0, "Checks exist to protect the customer experience and reduce costly rework, not to satisfy paperwork."),
    q("d-ops-3", "operations", "diagnostic", "Control",
      "Which is the best sign that operations are under control?",
      ["The owner is present every hour.",
       "A simple daily checklist is completed and exceptions are logged.",
       "Staff work overtime every week.",
       "Nothing ever goes wrong."],
      1, "A completed checklist plus logged exceptions shows the process is working and gives you something to improve. Constant firefighting is not control."),
    # Finance
    q("d-fin-1", "finance", "diagnostic", "Profit",
      "Revenue is RM20,000, variable costs RM11,000 and fixed costs RM6,000. What is your profit?",
      ["RM9,000", "RM3,000", "RM14,000", "RM2,000"],
      1, "20,000 − 11,000 − 6,000 = RM3,000. Gross profit was RM9,000, but fixed costs still had to be paid."),
    q("d-fin-2", "finance", "diagnostic", "Break-even",
      "Which number tells you how much sales you need before you start making a profit?",
      ["Break-even sales.", "Total revenue.", "Gross profit.", "Average order value."],
      0, "Break-even sales is where contribution covers fixed costs. Below it you make a loss; above it you make profit."),
    q("d-fin-3", "finance", "diagnostic", "Cash flow",
      "You have RM5,000 cash but owe suppliers RM7,000 next week. What is the honest position?",
      ["You are profitable.",
       "You have a RM2,000 cash shortfall to solve now.",
       "It is fine because sales are coming.",
       "You need a bigger logo."],
      1, "Cash timing is separate from profit. A RM2,000 gap next week needs a concrete plan: collect receivables, negotiate terms, or reduce spending."),
    # People
    q("d-ppl-1", "people", "diagnostic", "Coaching",
      "A reliable staff member keeps making the same mistake. What is the best first action?",
      ["Clarify the standard and train once with a check.",
       "Ignore it because they are reliable.",
       "Cut their hours.",
       "Do the task yourself forever."],
      0, "Repeated mistakes usually mean the standard was never made explicit. Clarify, train, then check."),
    q("d-ppl-2", "people", "diagnostic", "Fairness",
      "Which is the strongest sign of fair people management?",
      ["Rules are applied consistently, explained, and written down.",
       "Long-serving staff get special treatment.",
       "Feedback is avoided to keep the peace.",
       "Everyone is paid the same regardless of role."],
      0, "Consistency and explanation build trust. Unwritten exceptions create resentment and confusion."),
    q("d-ppl-3", "people", "diagnostic", "Workload",
      "A team member is overwhelmed. What is the most useful response?",
      ["Add more tasks to build resilience.",
       "Review workload priorities together and agree what stops or waits.",
       "Tell them to work faster.",
       "Replace them."],
      1, "Overload is usually a priority or capacity problem. Agreeing what to stop is a management decision, not a motivation speech."),
    # Systems
    q("d-sys-1", "systems", "diagnostic", "SOP quality",
      "What makes an SOP actually useful?",
      ["It is short, step by step, and used in training and daily work.",
       "It is at least forty pages long.",
       "It lives in the owner's head.",
       "It is written only after a crisis."],
      0, "An SOP earns its place by being usable. Long documents nobody opens do not create consistency."),
    q("d-sys-2", "systems", "diagnostic", "Continuity",
      "A key task depends on one person who is on leave. What is missing?",
      ["A documented process someone else can follow.",
       "Motivation.",
       "A new software subscription.",
       "A bigger team."],
      0, "If only one person can do it, the process is undocumented. Write it down and have someone else test it."),
    q("d-sys-3", "systems", "diagnostic", "Review",
      "How often should SOPs be reviewed?",
      ["Once and never again.",
       "When something changes or a problem repeats.",
       "Every single day.",
       "Only when staff complain."],
      1, "Review triggers should include changes in tools, suppliers, staff or repeated errors. Calendar reviews alone miss the real signal."),
    # Legal
    q("d-leg-1", "legal", "diagnostic", "Licensing",
      "You want to sell food from home for the first time. What should you check first?",
      ["Local licensing and food-handling requirements.",
       "Competitor prices.",
       "A new logo.",
       "Influencer rates."],
      0, "Licensing and food safety come before marketing. Getting this wrong can close the business."),
    q("d-leg-2", "legal", "diagnostic", "Records",
      "Which record best protects you in a customer dispute?",
      ["A written order or terms record showing what was agreed.",
       "A verbal promise.",
       "A social media post.",
       "Your memory of the conversation."],
      0, "A written record of scope, price and terms is the difference between a discussion and a dispute you can resolve."),
    q("d-leg-3", "legal", "diagnostic", "Contracts",
      "A supplier contract has a 60-day payment term you cannot meet. What is the right move?",
      ["Sign it and hope for the best.",
       "Negotiate the term before signing.",
       "Ignore the contract.",
       "Pay late without telling anyone."],
      1, "Negotiate before you commit. Silent late payment damages the relationship and your reputation."),
    # Digital
    q("d-dig-1", "digital", "diagnostic", "Online selling",
      "You want to start selling online. What is the smallest sensible first step?",
      ["List on one channel and track orders and costs for 30 days.",
       "Build a custom mobile app.",
       "Hire an agency for a full rebrand.",
       "Buy ads on every platform."],
      0, "One channel with real numbers teaches you whether online selling works for your product before you spend heavily."),
    q("d-dig-2", "digital", "diagnostic", "Metrics",
      "Which metric best shows whether your online effort is working?",
      ["Repeat orders and cost per order.",
       "Number of likes only.",
       "Website visits only.",
       "Hours spent posting."],
      0, "Revenue quality matters. Repeat orders and cost per order connect effort to money; likes and visits alone do not."),
    q("d-dig-3", "digital", "diagnostic", "Simple tools",
      "What is a sensible use of a simple spreadsheet in a small business?",
      ["Tracking daily sales, costs and stock in one place.",
       "Replacing all staff.",
       "Storing customer passwords.",
       "Avoiding records entirely."],
      0, "A simple, consistent record beats a complicated system you do not use. Never store passwords in a spreadsheet."),
]

# ---------------------------------------------------------------------------
# Module 1: Business Strategy & Model
# ---------------------------------------------------------------------------

MODULE = {
    "id": "strategy",
    "component": "strategy",
    "title": "Business Strategy & Model",
    "tagline": "Turn experience into a clear, profitable model you can manage every week.",
    "level": "Foundation",
    "hours": "45–60 min",
    "outcome": "By the end, you will have a one-page business model, a break-even number, and two measurable 30-day priorities.",
    "intro": [
        "You already know how to run the work. This module gives you the structure behind it: who you serve, why they choose you, how each sale contributes, and what to focus on next.",
        "Use your own business as the case study. Every lesson ends with a short exercise, and the templates turn your answers into a one-page model you can keep using.",
    ],
    "lessons": [
        {
            "id": "l1",
            "number": 1,
            "title": "What a business model really is",
            "minutes": 8,
            "summary": "A business model is the logic of how you create value for a specific customer and get paid more than it costs to deliver.",
            "explanation": [
                "A business model is not a pitch deck or a logo. It is the answer to four connected questions: Who do you serve? What do you promise them? How do you deliver it? And does the money left over cover everything else?",
                "Most small businesses have a model already — it is just implicit. The owner knows which customers are good, which products sell, and roughly what things cost. Writing it down turns that experience into something you can test, teach and improve.",
                "The useful test is contribution: what is left from one sale after the direct cost of delivering it? That number pays for rent, wages, your time and profit. If you do not know it, you cannot make good decisions about price, discounts or which product to push.",
            ],
            "example": {
                "title": "Aina's Kitchen — a lunch set, measured",
                "text": "Aina sells a RM12 rice set. Ingredients cost RM4.50, packaging RM0.80 and delivery RM1.20, so each set contributes RM5.50. Her rent, utilities and wages come to RM1,650 a month. That means she needs 300 sets a month just to break even — about 14 working days of 22 sets. On a good day she sells 35 sets, which contributes RM192.50. That single number now tells her whether a discount, a new menu item or a delivery deal is worth doing.",
            },
            "do": [
                "Write your model on one page: customer, promise, channels, revenue, direct costs, fixed costs.",
                "Calculate contribution per sale for your main product or service.",
                "Check that your price covers direct costs with enough left to pay overheads.",
            ],
            "dont": [
                "Do not describe your business as 'we sell food' — that is a category, not a model.",
                "Do not count revenue as success before direct and fixed costs are paid.",
                "Do not copy a competitor's model without checking whether their costs and customers are like yours.",
            ],
            "why": "When the model is explicit, everyday decisions get easier. You can say no to an unprofitable order, choose which customer group to chase, and explain to staff why a change matters.",
            "mistakes": [
                "Confusing gross profit with profit: forgetting rent, wages and your own time.",
                "Adding products without knowing whether they add contribution or just complexity.",
                "Pricing by copying the market instead of by knowing your break-even point.",
            ],
            "exercise": {
                "prompt": "Map your business model in six boxes and calculate contribution for your main offer.",
                "steps": [
                    "Name your primary customer group in one sentence.",
                    "Write the promise you make them in one sentence.",
                    "List your revenue streams and put a rough monthly figure next to each.",
                    "List direct costs per sale, then calculate contribution.",
                    "List fixed monthly costs and calculate your break-even sales.",
                    "Keep the page — you will use it again in the practical assignment.",
                ],
            },
        },
        {
            "id": "l2",
            "number": 2,
            "title": "Choose who you serve",
            "minutes": 10,
            "summary": "A clear customer and a sharp promise beat a wide audience with a vague offer.",
            "explanation": [
                "Small businesses often try to serve everyone because every sale feels valuable. The result is a message that fits no one and a mix of customers who demand different things at different prices.",
                "Choosing a primary customer does not mean refusing others. It means deciding whose problem you optimise for when you make decisions about menu, opening hours, packaging, response time and price.",
                "A useful value proposition names the customer, the problem, the outcome and the alternative. 'For busy office workers nearby who need a reliable lunch, we provide a hot set meal ready in five minutes at a fixed price — unlike waiting at a café or guessing from a delivery app.' That sentence can be tested.",
            ],
            "example": {
                "title": "Norli's online skincare shop",
                "text": "Norli sold 40 different products to 'anyone with skin'. Her best repeat customers were mothers aged 30–45 who wanted a simple routine, not a shelf of options. She cut her front-page range to three bundles, wrote the routine in plain language, and added a WhatsApp follow-up after seven days. Repeat orders rose because the offer matched a real routine problem — not because she discounted more.",
            },
            "do": [
                "Pick one primary customer group and describe their day, budget and constraints.",
                "Write your promise in the customer's words, not industry language.",
                "Name the two alternatives they would use if you did not exist.",
            ],
            "dont": [
                "Do not define your customer as 'everyone' or 'people who like good food'.",
                "Do not list features without saying what changes for the customer.",
                "Do not change your target every month because one enquiry came from elsewhere.",
            ],
            "why": "A defined customer makes marketing cheaper, service more consistent and pricing easier to defend. It also gives you a filter for opportunities that look good but pull you off course.",
            "mistakes": [
                "Targeting a group you cannot actually reach or serve well.",
                "Writing a promise that any competitor could copy word for word.",
                "Confusing a one-off big order with a viable customer segment.",
            ],
            "exercise": {
                "prompt": "Write a one-sentence value proposition and test it against two alternatives.",
                "steps": [
                    "Complete: 'For [customer] who [need], we provide [offer] that [outcome], unlike [alternative].'",
                    "Ask three real customers whether the sentence sounds like their problem.",
                    "Note the words they use that you did not — those belong in your marketing.",
                    "Check: could a competitor say the same sentence? If yes, sharpen it.",
                ],
            },
        },
        {
            "id": "l3",
            "number": 3,
            "title": "Make the numbers work",
            "minutes": 12,
            "summary": "Know your contribution, your break-even point and the difference between profit and cash.",
            "explanation": [
                "Three numbers make strategy practical: contribution per sale, break-even sales, and cash timing. Contribution is price minus direct costs. Break-even is fixed costs divided by contribution. Cash timing is when money actually arrives and leaves.",
                "A business can be profitable on paper and still fail because a large customer pays in 60 days while suppliers need paying in 14. Strategy has to include how cash moves, not only how much margin exists.",
                "Use simple worksheets rather than complicated accounting. The goal is not to become an accountant; it is to know which lever to pull when sales dip or costs rise.",
            ],
            "example": {
                "title": "Raj's air-conditioner servicing",
                "text": "Raj charges RM120 per service. Parts average RM35 and travel RM25, leaving RM60 contribution. His fixed costs — workshop rent, insurance, phone and one helper's base wage — are RM4,800 a month, so break-even is 80 services. At 95 services he makes RM900. When a competitor cut prices to RM95, Raj calculated that he would need 160 services to stand still. Instead of matching the price, he sold a RM180 deep-clean package to existing customers and protected his margin.",
            },
            "do": [
                "Separate direct costs (per sale) from fixed costs (monthly).",
                "Calculate contribution and break-even for your main offer.",
                "Forecast cash weekly for the next 13 weeks, including known large payments.",
            ],
            "dont": [
                "Do not include your own drawings as a business cost without labelling them clearly.",
                "Do not treat a deposit as profit before the work is delivered.",
                "Do not discount without recalculating how many extra units you must sell.",
            ],
            "why": "These numbers turn opinion into a decision. They show whether a discount is affordable, whether a new hire pays for itself, and how much buffer you need before a slow month.",
            "mistakes": [
                "Mixing personal and business money, which hides the true cost of the business.",
                "Forgetting delivery fees, payment fees and packaging when calculating contribution.",
                "Assuming a profitable month means there is enough cash to pay next month's bills.",
            ],
            "exercise": {
                "prompt": "Calculate your break-even and one 'what if' scenario.",
                "steps": [
                    "List fixed monthly costs, including a fair wage for your own time.",
                    "Calculate contribution for your main offer.",
                    "Divide fixed costs by contribution — that is your break-even volume.",
                    "Test a 10% price cut: how many extra sales are needed to keep the same profit?",
                    "Write down which lever you would pull first if sales fell 20%.",
                ],
            },
        },
        {
            "id": "l4",
            "number": 4,
            "title": "Turn strategy into weekly priorities",
            "minutes": 9,
            "summary": "A strategy only works if it changes what you do this week and what you stop doing.",
            "explanation": [
                "Most plans fail not because the idea is wrong but because the business is already full. New priorities must replace old work, not pile on top of it.",
                "Choose at most three priorities for the next 30 days. Each needs a measurable target, one owner, and a weekly check. Leading indicators — enquiries, repeat orders, booked jobs — tell you early whether the priority is working; lagging indicators such as monthly profit tell you later.",
                "A weekly review of 20 minutes is enough: what moved, what did not, what will you stop, and what is the one decision for next week. Write it down so the pattern becomes visible.",
            ],
            "example": {
                "title": "Aina's 30-day priority",
                "text": "Aina's profit was inconsistent. Instead of 'market more', she chose one priority: add two corporate lunch accounts in 30 days. Weekly leading indicators were: five office visits, three tasting samples, two quotes. She stopped spending on weekend market stalls for a month to protect the time. After four weeks she had one account for 18 sets a day and a clear reason to continue — or stop — based on evidence.",
            },
            "do": [
                "Limit yourself to three priorities, each with a number and a date.",
                "Track one leading indicator per priority every week.",
                "Decide explicitly what you will stop or delay to make room.",
            ],
            "dont": [
                "Do not write a list of ten goals and call it a strategy.",
                "Do not measure only monthly revenue — it arrives too late to change course.",
                "Do not start a new priority before deciding what happens to the old one.",
            ],
            "why": "Weekly priorities connect the model to real behaviour. They make progress visible, reduce busywork, and give you evidence for the next decision instead of another year of guessing.",
            "mistakes": [
                "Priorities that are actually tasks ('make a poster') rather than outcomes ('ten enquiries').",
                "No owner, so everyone assumes someone else is doing it.",
                "Reviewing only when something goes wrong, so the plan quietly disappears.",
            ],
            "exercise": {
                "prompt": "Write your 30-day one-page plan.",
                "steps": [
                    "Choose two priorities that would most improve contribution or cash.",
                    "Give each a target number and a deadline.",
                    "Name the leading indicator you will check each Friday.",
                    "Write what you will stop or delay to protect the time.",
                    "Book a 20-minute weekly review in your calendar now.",
                ],
            },
        },
    ],
    "templates": [
        {
            "slug": "business-model-canvas",
            "title": "One-page business model canvas",
            "description": "Nine prompts to capture customers, promise, channels, costs and revenue on a single page.",
            "format": "Markdown",
            "filename": "bizready-business-model-canvas.md",
        },
        {
            "slug": "break-even-worksheet",
            "title": "Break-even worksheet",
            "description": "A simple CSV you can open in Excel or Sheets: fixed costs, contribution and break-even volume.",
            "format": "CSV",
            "filename": "bizready-break-even-worksheet.csv",
        },
        {
            "slug": "weekly-priority-planner",
            "title": "30-day priority planner",
            "description": "Choose three priorities, set leading indicators, and record what you will stop.",
            "format": "Markdown",
            "filename": "bizready-30-day-priority-planner.md",
        },
        {
            "slug": "strategy-checklist",
            "title": "Strategy health checklist",
            "description": "Twelve checks to see whether your model is clear enough to manage.",
            "format": "Markdown",
            "filename": "bizready-strategy-checklist.md",
        },
    ],
    "practical": {
        "title": "Practical assignment: your one-page business model",
        "intro": "Use your own business. Write short, specific answers. A reviewer scores each criterion from 0 to 4; the module passes at an average of 3 or more, with no criterion below 2.",
        "criteria": [
            {"id": "customer_clarity", "label": "Customer clarity", "hint": "One primary customer group, described specifically enough to act on."},
            {"id": "differentiation", "label": "Differentiation", "hint": "A promise that is distinct from named alternatives and matters to the customer."},
            {"id": "numbers", "label": "Numbers", "hint": "Contribution and break-even calculated correctly for the main offer."},
            {"id": "execution", "label": "Execution", "hint": "Two measurable 30-day priorities with a weekly check and something stopped."},
        ],
        "prompts": [
            {"id": "p1", "criterion": "customer_clarity",
             "label": "Who is your primary customer, and what problem are they trying to solve?",
             "placeholder": "Be specific: who they are, what their day looks like, what they need and what they use instead today."},
            {"id": "p2", "criterion": "differentiation",
             "label": "Write your value proposition in one sentence and name two alternatives customers have.",
             "placeholder": "For [customer] who [need], we provide [offer] that [outcome], unlike [alternative]."},
            {"id": "p3", "criterion": "numbers",
             "label": "Show contribution per sale and your break-even point for your main offer.",
             "placeholder": "Price, direct costs, contribution, fixed monthly costs, break-even volume. Show the arithmetic."},
            {"id": "p4", "criterion": "execution",
             "label": "Choose two priorities for the next 30 days, with a target, a weekly indicator and what you will stop.",
             "placeholder": "Priority, target number, deadline, Friday indicator, and what you will delay or drop."},
        ],
    },
}

QUIZ_QUESTIONS = [
    q("q-str-1", "strategy", "quiz", "Business model",
      "Which statement best describes a business model?",
      ["A description of the products you sell.",
       "How a business creates, delivers and captures value profitably.",
       "A marketing plan for social media.",
       "The legal structure of the company."],
      1, "A model connects customer, offer, delivery and economics. Product lists and marketing plans are only parts of it."),
    q("q-str-2", "strategy", "quiz", "Break-even",
      "Fixed costs are RM4,000. Price is RM10 and variable cost is RM6. What is break-even volume?",
      ["400 units", "1,000 units", "667 units", "4,000 units"],
      1, "Contribution is RM4 per unit. 4,000 ÷ 4 = 1,000 units."),
    q("q-str-3", "strategy", "quiz", "Value proposition",
      "A value proposition is best understood as:",
      ["The list of features your product has.",
       "The specific reason a defined customer chooses you over their alternatives.",
       "Your lowest price.",
       "Your company slogan."],
      1, "It is a choice made by a customer between alternatives, not a feature list or a slogan."),
    q("q-str-4", "strategy", "quiz", "Leading indicators",
      "Which is a leading indicator you can act on weekly?",
      ["Annual profit.",
       "Repeat orders from regular customers.",
       "Last year's total revenue.",
       "Total social media followers."],
      1, "Repeat orders move week to week and predict future revenue. Annual profit arrives too late to steer."),
    q("q-str-5", "strategy", "quiz", "Competitive response",
      "A competitor cuts prices. What is the best first response?",
      ["Match the price immediately.",
       "Check whether your target customer values price over what you offer, then test a targeted response.",
       "Cut costs by reducing quality.",
       "Ignore it completely."],
      1, "Diagnose before reacting. If your customer values reliability or speed, matching price may destroy margin for no gain."),
    q("q-str-6", "strategy", "quiz", "Costs",
      "Which of these is a fixed cost for a small food business?",
      ["Ingredients.", "Packaging.", "Monthly shop rent.", "Delivery fees per order."],
      2, "Rent is owed regardless of volume. The others vary directly with each sale."),
    q("q-str-7", "strategy", "quiz", "Margins",
      "Gross margin is calculated as:",
      ["Revenue minus all costs.",
       "(Revenue − variable costs) ÷ revenue.",
       "Revenue ÷ number of staff.",
       "Profit minus tax."],
      1, "Gross margin shows what is left after direct costs, as a share of revenue. Fixed costs come after that."),
    q("q-str-8", "strategy", "quiz", "Strategy choices",
      "A strategy is best described as:",
      ["A list of everything you could do.",
       "A set of choices about where to play, how to win, and what not to do.",
       "A budget.",
       "A mission statement."],
      1, "Strategy is selection under constraint. The 'what not to do' part is what makes it usable."),
    q("q-str-9", "strategy", "quiz", "Portfolio decisions",
      "You have three product lines: A (high volume, low margin), B (low volume, high margin) and C (new, untested). What is the best use of a weekly review?",
      ["Drop A immediately.",
       "Compare contribution per hour of effort and decide what to grow, fix or stop.",
       "Push all three equally.",
       "Raise every price by 10%."],
      1, "Contribution per unit of effort is the honest comparison for a small team. It turns a vague portfolio into decisions."),
    q("q-str-10", "strategy", "quiz", "Goal setting",
      "Which goal passes the specific-and-measurable test?",
      ["Improve customer service.",
       "Raise average order value from RM18 to RM22 within 8 weeks by bundling a drink.",
       "Grow the business.",
       "Be more consistent."],
      1, "It names a measure, a baseline, a target and a deadline, so progress can be checked."),
]

SCENARIO_QUESTIONS = [
    q("s-str-1", "strategy", "scenario", "Diagnosis",
      "A food stall has a long lunch queue, customers leave, and profit is flat. What should the owner check first?",
      ["Raise all prices by 10%.",
       "Measure where time is lost and what each set contributes after direct costs.",
       "Hire two more staff immediately.",
       "Reduce portion sizes quietly."],
      1, "Two problems may be present: throughput and margin. Measure both before changing price or capacity; otherwise you may add cost without fixing either."),
    q("s-str-2", "strategy", "scenario", "Discounting",
      "An online seller with thin margins plans a 30% storewide discount to boost sales. What is the soundest response?",
      ["Run the 30% discount and hope volume covers it.",
       "Test a smaller bundle offer on one product and measure contribution after fees and delivery.",
       "Cut the discount to 5% and do nothing else.",
       "Stop selling online."],
      1, "A bounded test on one product protects cash and produces evidence. Storewide discounting on thin margins usually trades profit for revenue."),
    q("s-str-3", "strategy", "scenario", "Concentration risk",
      "A service provider gets 60% of revenue from one client. What is the priority?",
      ["Raise prices for that client immediately.",
       "Set a 90-day plan to add two smaller recurring clients while protecting service quality.",
       "Stop serving the large client.",
       "Hire more staff for the big client."],
      1, "Concentration is an existential risk. Grow the base carefully without destabilising the relationship that currently funds the business."),
    q("s-str-4", "strategy", "scenario", "Cost shock",
      "Rent rises 20% and the business is near break-even. Which sequence is most sensible?",
      ["Cut staff hours first, then tell no one.",
       "Recalculate break-even, then test price and product mix before cutting capacity.",
       "Absorb the increase and wait for sales to grow.",
       "Move premises immediately."],
      1, "Quantify the new break-even, then test the least destructive levers. Premature staff cuts damage quality and can reduce revenue further."),
    q("s-str-5", "strategy", "scenario", "New competitor",
      "A new competitor opens nearby with visibly lower prices. What is the best structured response?",
      ["Match every price that day.",
       "Confirm what your best customers value, protect it, and test one targeted response.",
       "Start a public price war on social media.",
       "Wait six months and see what happens."],
      1, "Know why customers stay before reacting. Protect the differentiator, then test one response with a measurable result."),
]

TEMPLATE_FILES = {
    "business-model-canvas": """# One-page business model canvas

Business: ______________________   Date: ____________

## 1. Primary customer
Who exactly? What does their day look like?

## 2. Their problem
What are they trying to get done? What goes wrong today?

## 3. Your promise
For [customer] who [need], we provide [offer] that [outcome], unlike [alternative].

## 4. Channels
How do they find you and buy from you?

## 5. Revenue streams
What do they pay for, and how often?

## 6. Direct costs per sale
Ingredients / stock / delivery / payment fees / packaging:

## 7. Contribution per sale
Price − direct costs = ____________

## 8. Fixed monthly costs
Rent, wages, utilities, insurance, your own wage:

## 9. Break-even
Fixed costs ÷ contribution = ____________ sales per month

## 10. The one number you will review weekly
______________________

## Notes
- Test one change at a time.
- Write the date on every version so you can see what changed.
""",
    "break-even-worksheet": """Section,Item,Amount (RM),Notes
Fixed costs,Rent,,
Fixed costs,Wages (excluding per-job pay),,
Fixed costs,Utilities,,
Fixed costs,Insurance,,
Fixed costs,Phone and internet,,
Fixed costs,Software and subscriptions,,
Fixed costs,Loan or hire-purchase payments,,
Fixed costs,Owner's fair wage,,
Fixed costs,Other fixed costs,,
Fixed costs,TOTAL FIXED COSTS,,
Offer,Price per sale,,
Offer,Direct materials or stock,,
Offer,Packaging,,
Offer,Delivery or transport per sale,,
Offer,Payment platform fees,,
Offer,TOTAL VARIABLE COST PER SALE,,
Result,Contribution per sale,,
Result,Break-even units per month,,
Result,Break-even sales value,,
What if,Price change (%),,
What if,New contribution,,
What if,New break-even units,,
What if,Extra units needed to hold profit,,
""",
    "weekly-priority-planner": """# 30-day priority planner

Business: ______________________   Start date: ____________   Review day: ____________

## Priority 1
- Outcome (not a task):
- Target number and deadline:
- Leading indicator checked weekly:
- Owner:
- First action this week:

## Priority 2
- Outcome (not a task):
- Target number and deadline:
- Leading indicator checked weekly:
- Owner:
- First action this week:

## What I will stop or delay
1.
2.

## Weekly review (20 minutes)
| Week | Indicator 1 | Indicator 2 | What moved | What did not | Decision |
|------|-------------|-------------|------------|--------------|----------|
| 1    |             |             |            |              |          |
| 2    |             |             |            |              |          |
| 3    |             |             |            |              |          |
| 4    |             |             |            |              |          |

## End-of-month decision
- Continue, change or stop priority 1:
- Continue, change or stop priority 2:
- One thing learned about the business:
""",
    "strategy-checklist": """# Strategy health checklist

Score each item: 0 = not true, 1 = partly true, 2 = true and written down.

- [ ] I can name my primary customer group in one sentence.
- [ ] I know the two alternatives they would use without me.
- [ ] My promise names an outcome, not just a feature.
- [ ] I know contribution per sale for my main offer.
- [ ] I know my monthly fixed costs, including a fair wage for my time.
- [ ] I know my break-even sales volume.
- [ ] I review cash weekly, not only profit monthly.
- [ ] I have at most three priorities for the next 30 days.
- [ ] Each priority has a number, a deadline and one owner.
- [ ] I track a leading indicator every week.
- [ ] I have decided what to stop or delay to protect the priorities.
- [ ] I have a 20-minute weekly review in my calendar.

Total: ____ / 24

0–8: Build the basics first — start with contribution and break-even.
9–16: You have a model; make the priorities measurable.
17–24: Use the model to test growth options, one change at a time.
""",
}
