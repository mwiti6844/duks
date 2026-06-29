"""RAG knowledge base: CarDuka policies and public service information.

Each doc carries a citable source id + title in metadata. These docs are treated
as untrusted reference text — they never contain market prices (the price verdict
draws on sold-comparable DB rows instead). Service chunks derived from public
CarDuka pages include their source URL so the UI can link to the original page.
"""
from __future__ import annotations

KNOWLEDGE_DOCS = [
    {
        "id": "kb_auction_overview",
        "title": "How CarDuka auctions work",
        "category": "auctions",
        "text": (
            "CarDuka auctions are timed online sales backed by NCBA. Each auction "
            "lists a vehicle with a reserve price, the current highest bid, and a "
            "minimum bid increment. To place a bid you must be a verified buyer and "
            "your bid must be at least the current bid plus the minimum increment. "
            "When the countdown timer reaches zero the highest bid above the reserve "
            "wins. If no bid meets the reserve, the vehicle is not sold and may be "
            "relisted. Bids are binding commitments to purchase."
        ),
    },
    {
        "id": "kb_auction_reserve",
        "title": "Reserve prices and winning a CarDuka auction",
        "category": "auctions",
        "text": (
            "The reserve price is the minimum the seller will accept. It is hidden "
            "from buyers during bidding. A bid below the reserve keeps the auction "
            "live but will not win on its own. The winning bidder is notified "
            "immediately after the timer ends and must complete payment and NCBA "
            "financing or settlement within 48 hours. CarDuka holds a refundable "
            "deposit to confirm serious bidders."
        ),
    },
    {
        "id": "kb_financing_eligibility",
        "title": "CarDuka financing eligibility",
        "category": "financing",
        "text": (
            "NCBA-backed financing through CarDuka is available to Kenyan residents "
            "aged 21 and above with a valid national ID or passport, a KRA PIN, and "
            "three to six months of bank or M-Pesa statements showing regular income. "
            "A deposit of at least 20 percent of the vehicle price is typically "
            "required. Self-employed applicants may provide business records. Approval "
            "depends on affordability and credit history."
        ),
    },
    {
        "id": "kb_financing_process",
        "title": "CarDuka financing process and repayment",
        "category": "financing",
        "text": (
            "After choosing a vehicle, you submit a financing application with your ID, "
            "KRA PIN, and income documents. NCBA assesses affordability and issues an "
            "offer with a monthly repayment, term, and interest rate. Terms usually "
            "range from 12 to 60 months. Once you accept and pay the deposit, CarDuka "
            "releases the vehicle and repayments begin the following month. Early "
            "repayment is allowed and reduces total interest."
        ),
    },
    {
        "id": "kb_tradein_process",
        "title": "CarDuka trade-in process",
        "category": "trade-in",
        "source_url": "https://www.carduka.com/sell-a-car/trade-in-seller",
        "text": (
            "CarDuka's public trade-in flow starts when a user submits details of their "
            "current car and desired car. CarDuka quality-checks the listing and publishes "
            "it to its dealer network, and also publishes it in the used-cars section. "
            "Dealers and buyers can then make offers; the user can review offers, chat, "
            "arrange an inspection or test drive, and select a preferred offer. If a "
            "top-up is needed for the desired car, the user can apply for financing "
            "through CarDuka."
        ),
    },
    {
        "id": "kb_tradein_marketplace",
        "title": "CarDuka Trade-In Marketplace",
        "category": "trade-in",
        "source_url": "https://www.carduka.com/trade-in",
        "text": (
            "The CarDuka Trade-In Marketplace displays vehicles whose owners are looking "
            "to trade in and allows interested parties to make offers. Listings show the "
            "current vehicle and the owner's desired replacement vehicle. This is a "
            "marketplace workflow; an offer is not automatically an accepted valuation "
            "or completed vehicle exchange."
        ),
    },
    {
        "id": "kb_buyer_protection",
        "title": "CarDuka buyer protection and inspections",
        "category": "policies",
        "text": (
            "Every CarDuka vehicle undergoes a multi-point mechanical and history "
            "inspection before listing. Buyers receive an inspection report and a "
            "verified logbook history. CarDuka offers a 5-day return window on direct "
            "purchases if the vehicle materially differs from its listing. Auction "
            "purchases are final once the timer ends but still include the inspection "
            "guarantee."
        ),
    },
    {
        "id": "kb_payments",
        "title": "CarDuka payments and fees",
        "category": "policies",
        "text": (
            "Payments are made through NCBA bank transfer or M-Pesa to CarDuka escrow. "
            "Funds are released to the seller only after the buyer confirms handover. "
            "CarDuka charges a transparent service fee shown before checkout. There are "
            "no hidden charges. Logbook transfer is handled by CarDuka on the buyer's "
            "behalf."
        ),
    },
    {
        "id": "kb_insurance",
        "title": "CarDuka vehicle insurance",
        "category": "insurance",
        "source_url": "https://www.carduka.com/documents/terms-and-conditions",
        "text": (
            "CarDuka provides integrated access to comprehensive and third-party motor "
            "vehicle insurance through NCBA Bancassurance, with policies underwritten by "
            "approved insurers. CarDuka acts as an access point; the relevant insurance "
            "provider decides cover and terms. Users should review the insurer's policy "
            "wording, exclusions, premium, and approval before accepting cover."
        ),
    },
    {
        "id": "kb_insurance_premium_finance",
        "title": "Insurance premium financing on CarDuka",
        "category": "insurance",
        "source_url": "https://www.carduka.com/documents/terms-and-conditions",
        "text": (
            "CarDuka also integrates access to NCBA insurance premium financing: a "
            "short-term credit facility for paying motor-insurance premiums in monthly "
            "instalments. It is distinct from the underlying insurance policy, and credit "
            "approval is decided by the relevant NCBA entity."
        ),
    },
    {
        "id": "kb_dealer_finance",
        "title": "CarDuka dealership financing",
        "category": "dealer-finance",
        "source_url": "https://www.carduka.com/financial-services/finance-my-car-dealership",
        "text": (
            "CarDuka provides licensed motor dealers with integrated access to working "
            "capital and stock-financing facilities through NCBA Bank Kenya. This is a "
            "dealership product, distinct from an individual user's vehicle purchase loan. "
            "Credit approval and facility terms are determined by NCBA, not by the CarDuka "
            "marketplace or its AI assistant."
        ),
    },
    {
        "id": "kb_dealer_finance_application",
        "title": "Applying for CarDuka dealership financing",
        "category": "dealer-finance",
        "source_url": "https://www.carduka.com/financial-services/finance-my-car-dealership",
        "text": (
            "The public CarDuka dealership-financing application asks for the dealership "
            "name, certificate of incorporation, a description of the financing required, "
            "the applicant's name, phone number, and email address, plus acceptance of "
            "CarDuka's terms and privacy policy. Submitting the form is an application, "
            "not an approval or promise of funding."
        ),
    },
]
