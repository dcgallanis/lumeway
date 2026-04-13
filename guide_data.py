# Guide content for each checklist item
# Maps item_text (exact) to guide details for the iOS app TaskDetailView

ITEM_GUIDES = {
    # ═══════════════════════════════
    # ESTATE — First 24 Hours
    # ═══════════════════════════════
    "Obtain the death certificate (request 10+ certified copies)": {
        "urgency": "Within 24 hours",
        "how_to": "Contact the funeral home or hospital where the death occurred. They typically handle ordering death certificates for you. Request at least 10 certified copies \u2014 you'll need them for insurance claims, bank accounts, property transfers, and legal proceedings. Each copy costs $10\u2013$25 depending on your state.",
        "steps": [
            "Ask the funeral home to order certified copies on your behalf",
            "Request at least 10 copies (insurance, banks, courts each need originals)",
            "If ordering yourself, contact your county's vital records office",
            "Keep copies in a secure location \u2014 you'll need them for months"
        ],
        "related_worksheet": "Death Certificate Request Checklist"
    },
    "Notify immediate family and close friends": {
        "urgency": "Within 24 hours",
        "how_to": "Start with the closest family members and work outward. Consider asking one trusted person to help make calls so you don't have to repeat the news dozens of times. A group text or email can work for extended circles, but close family deserves a personal call.",
        "steps": [
            "Call immediate family members first (spouse, children, parents, siblings)",
            "Ask one person to help spread the word to extended family",
            "Send a group message to close friends and colleagues",
            "Consider posting on social media only after close family has been notified"
        ]
    },
    "Contact the funeral home or cremation service": {
        "urgency": "Within 24 hours",
        "how_to": "If the death occurred at home, call 911 first, then the funeral home. If at a hospital or care facility, they can help coordinate. Compare at least two funeral homes on price \u2014 costs vary dramatically. You're not required to use the closest or first one you call.",
        "steps": [
            "Research at least two local funeral homes and compare prices",
            "Ask about their basic service fees and itemized pricing",
            "Decide between burial and cremation (if not pre-arranged)",
            "Ask about their timeline for services and viewings",
            "Check if the deceased had a pre-paid funeral plan"
        ],
        "related_worksheet": "Funeral Planning Checklist"
    },
    "Secure the deceased's home and property": {
        "urgency": "Within 24 hours",
        "how_to": "Change locks if others had keys, collect mail, and secure valuables. This protects against theft and ensures important documents aren't lost. If the deceased lived alone, check on pets, perishable food, and any running appliances.",
        "steps": [
            "Collect keys and secure all entry points",
            "Remove or secure valuables and important documents",
            "Check on pets, plants, and perishables",
            "Collect mail and stop newspaper delivery",
            "Set lights on timers if the home will be empty"
        ]
    },
    "Locate the will and any estate planning documents": {
        "urgency": "Within 24 hours",
        "how_to": "Check the deceased's home office, safe deposit box, filing cabinets, and with their attorney. Key documents include the will, trust documents, power of attorney, life insurance policies, and financial account information. Don't throw away any paperwork until the estate is settled.",
        "steps": [
            "Search the home for a will, trust, and financial documents",
            "Contact their attorney if they had one",
            "Check for a safe deposit box at their bank",
            "Look for digital documents on their computer or in email",
            "Gather insurance policies, deeds, and account statements"
        ],
        "related_worksheet": "Estate Document Locator"
    },

    # ESTATE — First Week
    "Notify the deceased's employer and request final paycheck": {
        "urgency": "Within 7 days",
        "how_to": "Contact HR at the deceased's employer to report the death and ask about final pay, accrued vacation payout, life insurance through work, and any retirement benefits. You may need the death certificate for some of these.",
        "steps": [
            "Call the employer's HR department",
            "Ask about the final paycheck and accrued PTO payout",
            "Inquire about employer-provided life insurance",
            "Ask about any retirement or pension benefits",
            "Request a copy of their benefits summary"
        ]
    },
    "Contact Social Security Administration (1-800-772-1213)": {
        "urgency": "Within 7 days",
        "how_to": "Call SSA to report the death and stop benefit payments. If the deceased was receiving Social Security, overpayments after death must be returned. Surviving spouses and dependents may be eligible for survivor benefits. The funeral home may report the death to SSA for you, but confirm.",
        "steps": [
            "Call SSA at 1-800-772-1213 (TTY: 1-800-325-0778)",
            "Have the deceased's Social Security number ready",
            "Ask about survivor benefits for spouse or dependents",
            "Return any benefit payments received after date of death",
            "Request a copy of the Social Security death notification"
        ]
    },
    "Notify banks and financial institutions": {
        "urgency": "Within 7 days",
        "how_to": "Contact each bank, credit union, and brokerage where the deceased had accounts. They'll freeze the accounts and guide you on accessing funds. Joint account holders can usually still access joint accounts. You'll need the death certificate.",
        "steps": [
            "Gather a list of all bank and investment accounts",
            "Call each institution and provide the death certificate",
            "Ask about joint account access and beneficiary payouts",
            "Request account balances as of the date of death",
            "Ask about any automatic payments that need to be stopped"
        ],
        "related_worksheet": "Financial Accounts Inventory"
    },
    "Contact life insurance companies to file claims": {
        "urgency": "Within 7 days",
        "how_to": "File claims with all life insurance companies as soon as possible. You'll need the policy number, death certificate, and beneficiary information. Most claims are paid within 30\u201360 days. Check for policies through employers, credit cards, and mortgage companies too.",
        "steps": [
            "Locate all life insurance policies",
            "Call each company to start the claims process",
            "Submit the death certificate and required forms",
            "Check for employer-provided group life insurance",
            "Look for accidental death or credit life insurance policies"
        ]
    },
    "Notify the post office to forward mail": {
        "urgency": "Within 7 days",
        "how_to": "Forward the deceased's mail to the executor or next of kin. This helps you catch bills, insurance notices, and financial statements you might not know about. You can do this online at usps.com or at your local post office.",
        "steps": [
            "Visit usps.com or your local post office",
            "Fill out a Change of Address form to forward mail",
            "Monitor forwarded mail for unknown accounts or bills",
            "Cancel junk mail subscriptions as they arrive"
        ]
    },
    "Contact utility companies about accounts": {
        "urgency": "Within 7 days",
        "how_to": "If the home will remain occupied, transfer utilities to the surviving occupant's name. If it will be vacant, keep essential services on (electricity, water) until the property is sold or transferred. Cancel non-essential services.",
        "steps": [
            "List all utility accounts (electric, gas, water, internet, phone)",
            "Transfer accounts to the surviving occupant if applicable",
            "Keep essential services on for occupied or for-sale properties",
            "Cancel cable, streaming, and other non-essential services"
        ]
    },

    # ESTATE — First Month
    "Meet with an estate attorney if needed": {
        "urgency": "Within 30 days",
        "how_to": "An estate attorney can guide you through probate, asset distribution, and tax obligations. Many offer free initial consultations. You likely need one if the estate has real estate, significant assets, debts, or if there's no will.",
        "steps": [
            "Ask for referrals from family, friends, or your local bar association",
            "Schedule consultations with 2\u20133 attorneys",
            "Bring the will, asset list, and death certificate",
            "Ask about their fees (flat rate vs. hourly)"
        ]
    },
    "File for probate if required": {
        "urgency": "Within 30 days",
        "how_to": "Probate is the legal process of validating the will and distributing assets. Not all estates require it \u2014 small estates and those with proper trusts may avoid it. File in the county where the deceased lived. Your estate attorney can handle this.",
        "steps": [
            "Determine if probate is required in your state",
            "File the will with the county probate court",
            "Get appointed as executor or personal representative",
            "Publish the required legal notice to creditors",
            "Inventory all estate assets for the court"
        ],
        "related_worksheet": "Probate Filing Checklist"
    },
    "Apply for survivor benefits (Social Security, VA, pension)": {
        "urgency": "Within 30 days",
        "how_to": "Surviving spouses, children, and dependents may be eligible for ongoing benefits. Apply for Social Security survivor benefits, VA benefits if the deceased was a veteran, and any pension survivor benefits from employers.",
        "steps": [
            "Apply for Social Security survivor benefits at ssa.gov or by phone",
            "Contact the VA if the deceased was a veteran (1-800-827-1000)",
            "Check for pension survivor benefits from employers",
            "Apply for the $255 Social Security lump-sum death benefit"
        ]
    },
    "Transfer vehicle titles": {
        "urgency": "Within 30 days",
        "how_to": "Visit your state's DMV to transfer vehicle titles. You'll need the death certificate, the vehicle title, and proof that you're the legal heir or executor. Some states allow transfer by affidavit for small estates.",
        "steps": [
            "Gather the vehicle title, death certificate, and executor documents",
            "Visit your local DMV or check their website for forms",
            "Pay any transfer fees and update the registration",
            "Update the vehicle insurance policy"
        ]
    },
    "Update property deeds if applicable": {
        "urgency": "Within 30 days",
        "how_to": "Real property needs to be transferred through the county recorder's office. The process depends on how the property was titled \u2014 joint tenancy, community property, or solely owned. An attorney can prepare the deed transfer documents.",
        "steps": [
            "Determine how the property is currently titled",
            "Work with an attorney to prepare transfer documents",
            "File the new deed with the county recorder's office",
            "Update property insurance and tax records"
        ]
    },
    "Notify credit agencies (Equifax, Experian, TransUnion)": {
        "urgency": "Within 30 days",
        "how_to": "Send a death certificate to each credit bureau to place a deceased alert on the credit report. This helps prevent identity theft. You can also request a copy of the credit report to identify unknown accounts.",
        "steps": [
            "Send a death certificate to Equifax, Experian, and TransUnion",
            "Request a deceased alert be placed on the credit file",
            "Request a copy of the deceased's credit report",
            "Review for unknown accounts or suspicious activity"
        ]
    },
    "Cancel subscriptions and memberships": {
        "urgency": "Within 30 days",
        "how_to": "Review bank and credit card statements for recurring charges. Cancel streaming services, gym memberships, magazine subscriptions, and any auto-renewing services. Some may offer refunds for unused portions.",
        "steps": [
            "Review bank and credit card statements for recurring charges",
            "Cancel streaming, gym, and subscription services",
            "Cancel memberships (AAA, clubs, professional associations)",
            "Request refunds for any prepaid unused services"
        ]
    },

    # ESTATE — Ongoing
    "File the deceased's final tax return": {
        "urgency": "Ongoing",
        "how_to": "A final federal and state tax return must be filed for the year of death. This covers income from January 1 through the date of death. The estate may also need to file a separate estate tax return if it exceeds the federal exemption ($12.92 million in 2023). Consider hiring a CPA.",
        "steps": [
            "Gather all income documents (W-2s, 1099s, investment statements)",
            "File a final Form 1040 for the year of death",
            "File a state tax return if required",
            "Determine if an estate tax return (Form 706) is needed",
            "Consider hiring a CPA experienced with estate taxes"
        ]
    },
    "Distribute assets according to the will": {
        "urgency": "Ongoing",
        "how_to": "After debts and taxes are paid, distribute remaining assets to beneficiaries as specified in the will. If there's no will, state intestacy laws determine distribution. Keep detailed records of every distribution.",
        "steps": [
            "Pay all outstanding debts and taxes first",
            "Follow the will's instructions for asset distribution",
            "Get receipts from beneficiaries for assets received",
            "File a final accounting with the probate court if required"
        ]
    },
    "Close remaining accounts": {
        "urgency": "Ongoing",
        "how_to": "After all financial matters are settled, close the deceased's remaining bank accounts, credit cards, and other financial accounts. Transfer any remaining balances to the estate account for distribution.",
        "steps": [
            "Confirm all debts and claims have been satisfied",
            "Close bank accounts and transfer remaining balances",
            "Close credit card accounts and request final statements",
            "Cancel any remaining services or memberships"
        ]
    },
    "Keep records of all estate transactions": {
        "urgency": "Ongoing",
        "how_to": "Document every financial transaction, payment, and distribution made on behalf of the estate. Keep records for at least 7 years. Beneficiaries or the court may request an accounting at any time.",
        "steps": [
            "Maintain a detailed ledger of all estate income and expenses",
            "Keep copies of all receipts and payment records",
            "Document all asset distributions to beneficiaries",
            "Store records securely for at least 7 years"
        ]
    },

    # ═══════════════════════════════
    # DIVORCE — First 24 Hours
    # ═══════════════════════════════
    "Secure copies of all important financial documents": {
        "urgency": "Within 24 hours",
        "how_to": "Make copies of tax returns, bank statements, investment accounts, mortgage documents, credit card statements, and pay stubs before anything can be hidden or destroyed. Store copies somewhere your spouse cannot access \u2014 a trusted friend's house, a safe deposit box, or a secure cloud drive.",
        "steps": [
            "Copy the last 3 years of tax returns",
            "Copy all bank, investment, and retirement account statements",
            "Photograph or scan mortgage, loan, and insurance documents",
            "Store copies in a secure location outside the home",
            "Screenshot online account balances with dates"
        ],
        "related_worksheet": "Financial Document Checklist"
    },
    "Open individual bank account if you don't have one": {
        "urgency": "Within 24 hours",
        "how_to": "Open a checking and savings account in your name only at a bank where you don't have joint accounts. Deposit enough to cover 2\u20133 months of basic expenses. Do not drain joint accounts \u2014 courts look unfavorably on that.",
        "steps": [
            "Choose a bank where you have no joint accounts",
            "Open a checking and savings account in your name only",
            "Set up direct deposit for your paycheck if applicable",
            "Transfer a reasonable amount for basic expenses"
        ]
    },
    "Document all shared assets and debts": {
        "urgency": "Within 24 hours",
        "how_to": "Create a complete inventory of everything you and your spouse own and owe. Include real estate, vehicles, bank accounts, retirement accounts, investments, credit cards, loans, and personal property of significant value.",
        "steps": [
            "List all real estate, vehicles, and major assets",
            "Document all bank, investment, and retirement accounts",
            "List all debts: mortgage, credit cards, loans, medical bills",
            "Note the approximate value and whose name each is in",
            "Photograph valuable personal property"
        ],
        "related_worksheet": "Marital Asset & Debt Inventory"
    },
    "Change passwords on personal accounts": {
        "urgency": "Within 24 hours",
        "how_to": "Update passwords on your personal email, social media, and any accounts your spouse may have access to. Enable two-factor authentication. Don't change passwords on joint accounts yet \u2014 that could look bad in court.",
        "steps": [
            "Change passwords on personal email accounts",
            "Update social media passwords and privacy settings",
            "Enable two-factor authentication where possible",
            "Do NOT change passwords on joint financial accounts"
        ]
    },
    "Consult with a family law attorney": {
        "urgency": "Within 24 hours",
        "how_to": "Even if you're considering mediation, consult with an attorney to understand your rights and what to expect. Many offer free or low-cost initial consultations. They can advise on protecting yourself financially and preparing for custody arrangements.",
        "steps": [
            "Ask for referrals from trusted friends or your local bar association",
            "Schedule consultations with 2\u20133 attorneys",
            "Prepare a list of your key concerns and questions",
            "Ask about their fees, experience, and approach to divorce",
            "Don't sign anything until you've gotten legal advice"
        ]
    },

    # DIVORCE — First Week
    "Gather tax returns from the last 3 years": {
        "urgency": "Within 7 days",
        "how_to": "Your attorney will need recent tax returns to assess income, assets, and potential support obligations. If you filed jointly, you can get copies from the IRS (Form 4506-T) or from your tax preparer.",
        "steps": [
            "Locate your copies of the last 3 years of tax returns",
            "Request copies from your tax preparer if needed",
            "Order transcripts from the IRS if you can't find them",
            "Include all schedules and attachments"
        ]
    },
    "List all joint accounts (bank, credit cards, investments)": {
        "urgency": "Within 7 days",
        "how_to": "Document every joint financial account with account numbers, balances, and institution names. This becomes critical for equitable division. Check credit reports for accounts you may have forgotten about.",
        "steps": [
            "List all joint bank accounts with current balances",
            "List all joint credit cards with balances and limits",
            "Document joint investment and brokerage accounts",
            "Pull your credit report to find forgotten joint accounts"
        ]
    },
    "Review and understand your household budget": {
        "urgency": "Within 7 days",
        "how_to": "Calculate what it actually costs to run your household each month. You'll need this for support negotiations and to plan your post-divorce finances. Include housing, utilities, food, insurance, transportation, childcare, and everything else.",
        "steps": [
            "Review bank and credit card statements for the past 3 months",
            "Categorize all expenses (housing, food, transport, etc.)",
            "Calculate your monthly total cost of living",
            "Identify which expenses will change after divorce"
        ],
        "related_worksheet": "Monthly Budget Worksheet"
    },
    "Research local family law attorneys (consultations are often free)": {
        "urgency": "Within 7 days",
        "how_to": "Interview multiple attorneys before choosing one. Ask about their experience with cases similar to yours, their communication style, and their fee structure. A good fit matters \u2014 you'll be working closely with this person for months.",
        "steps": [
            "Research attorneys online and ask for personal referrals",
            "Schedule 2\u20133 free consultations",
            "Ask about retainer fees and hourly rates",
            "Ask about their approach: collaborative, mediation, or litigation"
        ]
    },
    "Understand your state's divorce filing requirements": {
        "urgency": "Within 7 days",
        "how_to": "Each state has different residency requirements, waiting periods, and grounds for divorce. Some require separation periods before filing. Your attorney can explain the specifics, but knowing the basics helps you plan.",
        "steps": [
            "Research your state's residency requirement for filing",
            "Check if there's a mandatory waiting or separation period",
            "Understand the difference between no-fault and fault divorce",
            "Learn about your state's property division rules (community vs. equitable)"
        ]
    },

    # DIVORCE — First Month
    "File for divorce or respond to petition if served": {
        "urgency": "Within 30 days",
        "how_to": "If you're initiating, your attorney will file a petition with the court. If you've been served, you typically have 20\u201330 days to respond (varies by state). Don't ignore a petition \u2014 failure to respond can result in a default judgment against you.",
        "steps": [
            "Work with your attorney to prepare and file the petition, or",
            "Respond to the petition within your state's deadline",
            "Request temporary orders if needed for custody or support",
            "File any required financial disclosure documents"
        ]
    },
    "Request temporary orders if needed (custody, support, exclusive use)": {
        "urgency": "Within 30 days",
        "how_to": "Temporary orders set the rules while the divorce is pending \u2014 who stays in the house, custody schedule, and temporary support. These are especially important if there are children or if one spouse controls all the finances.",
        "steps": [
            "Discuss temporary order options with your attorney",
            "Request temporary custody arrangements if you have children",
            "Request temporary spousal or child support if needed",
            "Request exclusive use of the marital home if applicable"
        ]
    },
    "Begin the asset and property inventory": {
        "urgency": "Within 30 days",
        "how_to": "Work with your attorney to create a complete inventory of all marital property. This includes real estate, vehicles, bank accounts, retirement accounts, businesses, personal property, and debts. Accurate valuations are critical for fair division.",
        "steps": [
            "List all real estate with current market values",
            "Get appraisals for valuable items (jewelry, art, collectibles)",
            "Document retirement account balances",
            "List all vehicles with current values",
            "Inventory household items of significant value"
        ],
        "related_worksheet": "Marital Property Inventory"
    },
    "Understand how retirement accounts will be divided (QDRO)": {
        "urgency": "Within 30 days",
        "how_to": "Retirement accounts earned during marriage are typically marital property. A QDRO (Qualified Domestic Relations Order) is required to divide 401(k)s and pensions without tax penalties. Your attorney should handle this, but understand the basics.",
        "steps": [
            "Identify all retirement accounts subject to division",
            "Understand that a QDRO is needed for 401(k) and pension division",
            "Get current statements for all retirement accounts",
            "Ask your attorney about the timeline for QDRO preparation"
        ]
    },
    "Set up mail forwarding if moving out": {
        "urgency": "Within 30 days",
        "how_to": "If you're moving out of the marital home, set up mail forwarding through USPS. This ensures you receive important legal documents, financial statements, and correspondence. You can do this online at usps.com.",
        "steps": [
            "Forward mail to your new address through usps.com",
            "Update your address with banks and financial institutions",
            "Update your address with your employer",
            "Notify your attorney of your new address"
        ]
    },
    "Update beneficiaries on insurance policies": {
        "urgency": "Within 30 days",
        "how_to": "Review and update beneficiaries on life insurance, retirement accounts, and bank accounts. Note: some changes may be restricted by court orders during divorce proceedings. Check with your attorney before making changes.",
        "steps": [
            "Review beneficiaries on all life insurance policies",
            "Check beneficiaries on retirement accounts (401k, IRA)",
            "Review bank account beneficiaries (POD/TOD)",
            "Consult your attorney before making any changes during proceedings"
        ]
    },

    # DIVORCE — Ongoing
    "Attend all court dates and mediation sessions": {
        "urgency": "Ongoing",
        "how_to": "Missing court dates can result in default judgments or sanctions. Mediation is often required before trial and can save significant money. Come prepared with documents and a clear understanding of your priorities.",
        "steps": [
            "Put all court dates on your calendar immediately",
            "Prepare for mediation by listing your priorities and deal-breakers",
            "Bring all requested documents to every session",
            "Dress professionally and remain calm in all proceedings"
        ]
    },
    "Keep detailed records of all expenses": {
        "urgency": "Ongoing",
        "how_to": "Document all expenses related to children, household, and the divorce process. This evidence supports your position in support negotiations. Keep receipts and use a spreadsheet or app to track spending.",
        "steps": [
            "Track all child-related expenses with receipts",
            "Document household expenses and who pays what",
            "Keep records of all attorney fees and court costs",
            "Save all receipts and organize by category"
        ]
    },
    "Update your estate plan (will, power of attorney)": {
        "urgency": "Ongoing",
        "how_to": "Update your will, power of attorney, and healthcare directive to remove your spouse and name new beneficiaries. Some states automatically revoke spousal designations upon divorce, but don't rely on that.",
        "steps": [
            "Update your will to remove your spouse",
            "Name new power of attorney and healthcare proxy",
            "Update beneficiaries on all accounts and policies",
            "Create or update your advance healthcare directive"
        ]
    },
    "Establish credit in your own name": {
        "urgency": "Ongoing",
        "how_to": "If most accounts were joint or in your spouse's name, you need to build individual credit. Open a credit card in your name, pay it on time, and keep balances low. Good credit is essential for renting, buying a home, and getting loans.",
        "steps": [
            "Check your individual credit score and report",
            "Apply for a credit card in your name only",
            "Pay all bills on time and keep balances below 30% of limits",
            "Consider a secured credit card if your credit is limited"
        ]
    },
    "Update your name on documents if applicable": {
        "urgency": "Ongoing",
        "how_to": "If changing your name, update it on your Social Security card first, then driver's license, passport, bank accounts, and all other documents. You'll need a certified copy of the divorce decree showing the name change.",
        "steps": [
            "Update your Social Security card first (form SS-5)",
            "Update your driver's license at the DMV",
            "Update your passport",
            "Update bank accounts, credit cards, and insurance"
        ]
    },

    # ═══════════════════════════════
    # JOB LOSS — First 24 Hours
    # ═══════════════════════════════
    "Review your severance agreement (don't sign immediately)": {
        "urgency": "Within 24 hours",
        "how_to": "Don't sign anything the day you're let go. You typically have 21 days (45 if over 40) to review a severance agreement. Read every clause carefully, especially non-compete, non-disparagement, and release of claims provisions. Consider having an employment attorney review it.",
        "steps": [
            "Take the agreement home \u2014 don't sign on the spot",
            "Read every clause, especially non-compete and release sections",
            "Note the deadline to sign (usually 21\u201345 days)",
            "Consider having an employment attorney review it",
            "Negotiate if the terms are unfavorable"
        ],
        "related_worksheet": "Severance Agreement Review Checklist"
    },
    "File for unemployment benefits": {
        "urgency": "Within 24 hours",
        "how_to": "Visit your state's unemployment office website and file as soon as possible. There's often a one-week waiting period before benefits start, so filing sooner means getting paid sooner. You'll need your employer's name, address, and your work history.",
        "steps": [
            "Find your state's unemployment website (search '[state] unemployment')",
            "File your claim online \u2014 it takes 30\u201360 minutes",
            "Have your Social Security number and employer info ready",
            "Set up direct deposit for faster payments",
            "Respond promptly to any requests for additional information"
        ],
        "related_worksheet": "Unemployment Benefits Checklist"
    },
    "Understand your COBRA health insurance options": {
        "urgency": "Within 24 hours",
        "how_to": "You have 60 days to elect COBRA continuation coverage after losing employer insurance. COBRA is expensive (you pay the full premium plus 2% admin), but it keeps your exact same coverage. Compare COBRA with marketplace plans and a spouse's employer plan before deciding.",
        "steps": [
            "Wait for your COBRA election notice (arrives within 14 days)",
            "Calculate the monthly COBRA premium (typically $600\u2013$2,200)",
            "Compare with marketplace plans at healthcare.gov",
            "Check if you can join a spouse's employer plan",
            "You have 60 days to decide \u2014 don't rush"
        ],
        "related_worksheet": "COBRA vs. Marketplace Comparison"
    },
    "Secure copies of important work documents and contacts": {
        "urgency": "Within 24 hours",
        "how_to": "Save copies of your performance reviews, work samples (that aren't proprietary), contact information for colleagues, and any documentation of your accomplishments. Do NOT take confidential company information \u2014 focus on your personal records.",
        "steps": [
            "Save your performance reviews and award letters",
            "Copy your professional contact list",
            "Save work samples that showcase your skills (non-proprietary only)",
            "Download your pay stubs and benefits information",
            "Screenshot your LinkedIn recommendations"
        ]
    },
    "Review your last paycheck for accuracy": {
        "urgency": "Within 24 hours",
        "how_to": "Verify your final paycheck includes all owed compensation: regular pay through your last day, accrued but unused vacation/PTO, any commissions or bonuses owed, and expense reimbursements. State laws vary on payout timelines.",
        "steps": [
            "Check that pay covers through your last working day",
            "Verify accrued PTO or vacation payout",
            "Confirm any owed commissions or bonuses",
            "Submit any outstanding expense reports",
            "Check your state's law on final paycheck timing"
        ]
    },

    # JOB LOSS — First Week
    "Create a detailed budget based on reduced income": {
        "urgency": "Within 7 days",
        "how_to": "Calculate your total liquid savings and monthly expenses. Identify what you can cut immediately (dining out, subscriptions, gym). Divide your savings by your monthly burn rate to know how many months you can sustain. This number drives all your decisions.",
        "steps": [
            "Calculate total liquid savings (checking + savings + accessible investments)",
            "List all monthly fixed expenses (rent, utilities, insurance, minimums)",
            "Identify expenses to cut or pause immediately",
            "Calculate monthly burn rate (minimum to survive)",
            "Divide savings by burn rate = months of runway"
        ],
        "related_worksheet": "Emergency Budget Worksheet"
    },
    "Review your 401(k) options (leave it, roll over, or cash out)": {
        "urgency": "Within 7 days",
        "how_to": "You have four options: leave the 401(k) with your former employer, roll it to a new employer's plan, roll it to an IRA, or cash it out. Never cash out unless absolutely desperate \u2014 you'll lose 10% penalty plus income taxes. A direct rollover to an IRA is usually the best move.",
        "steps": [
            "Get your 401(k) balance and check your vesting status",
            "Check for any outstanding 401(k) loans (usually due within 60 days)",
            "Compare fees between leaving it and rolling to an IRA",
            "If rolling over, request a DIRECT rollover (trustee-to-trustee)",
            "Never cash out unless there is no other option"
        ]
    },
    "Update your resume and LinkedIn profile": {
        "urgency": "Within 7 days",
        "how_to": "Update your resume with quantified accomplishments from your most recent role. Refresh your LinkedIn profile, turn on 'Open to Work' (visible to recruiters only), and start engaging with your network. A strong digital presence is critical for job searching.",
        "steps": [
            "Update your resume with recent accomplishments and metrics",
            "Refresh your LinkedIn headline and summary",
            "Turn on 'Open to Work' in LinkedIn settings",
            "Ask former colleagues for LinkedIn recommendations",
            "Prepare a brief explanation for why you left"
        ]
    },
    "Apply for any applicable state or local assistance programs": {
        "urgency": "Within 7 days",
        "how_to": "You may qualify for SNAP (food assistance), utility assistance (LIHEAP), reduced-cost healthcare, and other programs. Visit benefits.gov to check eligibility. Call 211 for local resources. These programs exist for exactly this situation.",
        "steps": [
            "Check eligibility at benefits.gov",
            "Apply for SNAP if you qualify",
            "Check LIHEAP for utility assistance",
            "Call 211 for local emergency assistance resources",
            "If you have children, check for free/reduced school meals"
        ]
    },
    "Contact creditors if you anticipate payment difficulties": {
        "urgency": "Within 7 days",
        "how_to": "Call credit card companies, your mortgage servicer, and other lenders before you miss payments. Most offer hardship programs with reduced payments, lower interest rates, or forbearance. Being proactive shows good faith and protects your credit score.",
        "steps": [
            "Make a list of all creditors and minimum payments",
            "Call each creditor and ask about hardship programs",
            "Request temporary payment reductions or forbearance",
            "Get any agreements in writing",
            "Prioritize: housing, utilities, and food before credit cards"
        ]
    },

    # JOB LOSS — First Month
    "Decide on COBRA vs. marketplace health insurance": {
        "urgency": "Within 30 days",
        "how_to": "Compare the total annual cost of COBRA vs. marketplace plans. Factor in premiums, deductibles, copays, and whether your doctors and medications are covered. Marketplace subsidies can make plans much cheaper than COBRA, especially with reduced income.",
        "steps": [
            "Calculate your estimated annual income for subsidy eligibility",
            "Compare plans at healthcare.gov with your COBRA option",
            "Check that your doctors and prescriptions are covered",
            "Factor in deductibles and out-of-pocket maximums, not just premiums",
            "Enroll before your 60-day COBRA deadline or marketplace special enrollment period"
        ]
    },
    "Begin active job searching": {
        "urgency": "Within 30 days",
        "how_to": "Set a daily job search routine. Apply to 5\u201310 positions per week, customize each application, and follow up. Networking accounts for 70\u201380% of hires, so don't rely solely on online applications. Reach out to your professional contacts directly.",
        "steps": [
            "Set up job alerts on LinkedIn, Indeed, and industry-specific sites",
            "Apply to 5\u201310 positions per week with customized cover letters",
            "Reach out to former colleagues and mentors about opportunities",
            "Attend networking events and industry meetups",
            "Consider working with a recruiter in your field"
        ]
    },
    "Consider whether to roll over your 401(k) to an IRA": {
        "urgency": "Within 30 days",
        "how_to": "An IRA rollover gives you more investment options and often lower fees than an employer plan. Open an IRA at a major brokerage (Fidelity, Schwab, Vanguard), then request a direct rollover. This avoids the 20% mandatory withholding of an indirect rollover.",
        "steps": [
            "Open an IRA at a low-cost brokerage",
            "Contact your 401(k) plan administrator to initiate a direct rollover",
            "Choose your IRA investments (target-date funds are a simple option)",
            "Confirm the rollover completed successfully"
        ]
    },
    "Cut non-essential expenses": {
        "urgency": "Within 30 days",
        "how_to": "Review every recurring expense and eliminate anything that isn't essential. Cancel streaming services, pause gym memberships, cook at home, and downgrade your phone plan. Every dollar saved extends your financial runway.",
        "steps": [
            "Cancel unused subscriptions and streaming services",
            "Pause or cancel gym membership",
            "Reduce dining out and meal prep at home",
            "Downgrade phone and internet plans",
            "Postpone any large purchases"
        ]
    },
    "File for any applicable tax credits or deductions": {
        "urgency": "Within 30 days",
        "how_to": "Job loss may qualify you for several tax benefits. Job search expenses may be deductible, and your reduced income may make you eligible for the Earned Income Tax Credit. Adjust your W-4 withholding if you start a new job mid-year.",
        "steps": [
            "Track all job search expenses (travel, resume services, etc.)",
            "Check if you qualify for the Earned Income Tax Credit",
            "Consider adjusting estimated tax payments for reduced income",
            "Keep records of all unemployment benefits received (they're taxable)"
        ]
    },

    # JOB LOSS — Ongoing
    "Maintain a record of all job applications": {
        "urgency": "Ongoing",
        "how_to": "Track every application with the company, position, date applied, and follow-up status. This is required for unemployment benefits in many states and helps you stay organized. Use a spreadsheet or job tracking app.",
        "steps": [
            "Create a spreadsheet with company, position, date, and status",
            "Note follow-up dates and interview schedules",
            "Keep copies of confirmation emails",
            "Update weekly \u2014 many states require proof of job search activity"
        ],
        "related_worksheet": "Job Application Tracker"
    },
    "Network actively \u2014 attend events, reach out to contacts": {
        "urgency": "Ongoing",
        "how_to": "Most jobs are filled through networking, not job boards. Reach out to former colleagues, attend industry events, join professional groups, and let people know you're looking. Be specific about what you're looking for \u2014 it makes it easier for people to help.",
        "steps": [
            "Contact 5 people in your network each week",
            "Attend local networking events and professional meetups",
            "Join online communities in your industry",
            "Offer to help others \u2014 networking is a two-way street"
        ]
    },
    "Consider skills training or certifications": {
        "urgency": "Ongoing",
        "how_to": "Use this time to invest in yourself. Many states offer free or subsidized training through workforce development programs. Online courses, certifications, and bootcamps can make you more competitive. Focus on skills in demand in your target industry.",
        "steps": [
            "Check your state's workforce development programs for free training",
            "Identify certifications valued in your industry",
            "Explore free online learning (Coursera, edX, LinkedIn Learning)",
            "Consider a career pivot if your industry is declining"
        ]
    },
    "Monitor your unemployment benefits and renew if needed": {
        "urgency": "Ongoing",
        "how_to": "Unemployment benefits require regular certification \u2014 usually weekly or biweekly. You must report any income earned and job search activities. Missing a certification can delay or stop your benefits. Set a recurring reminder.",
        "steps": [
            "Set a weekly reminder to certify for benefits",
            "Report any part-time or freelance income honestly",
            "Document your job search activities as required",
            "Check your state's maximum benefit duration and plan accordingly"
        ]
    },

    # ═══════════════════════════════
    # RELOCATION — First 24 Hours
    # ═══════════════════════════════
    "Research your new state's requirements (license, registration, voting)": {
        "urgency": "Within 24 hours",
        "how_to": "Every state has different deadlines for updating your driver's license, vehicle registration, and voter registration after moving. Some require updates within 10 days, others within 90. Research your specific state's requirements early so you don't get caught off guard.",
        "steps": [
            "Search '[new state] new resident requirements'",
            "Note the deadline for getting a new driver's license",
            "Check vehicle registration transfer requirements and timeline",
            "Look up voter registration deadlines and process"
        ]
    },
    "Create a moving timeline and checklist": {
        "urgency": "Within 24 hours",
        "how_to": "Work backwards from your move date. Book movers 4\u20136 weeks ahead, start packing non-essentials 3 weeks out, and handle address changes 2 weeks before. A timeline keeps the dozens of moving tasks from overwhelming you.",
        "steps": [
            "Set your move date and work backwards",
            "List all tasks by timeframe (6 weeks, 4 weeks, 2 weeks, 1 week, day of)",
            "Assign responsibilities if others are helping",
            "Build in buffer time for unexpected delays"
        ],
        "related_worksheet": "Moving Timeline Planner"
    },
    "Get quotes from moving companies or plan a DIY move": {
        "urgency": "Within 24 hours",
        "how_to": "Get at least three in-home estimates from licensed movers for an accurate quote. Be wary of unusually low estimates \u2014 they often result in surprise charges. For DIY moves, compare truck rental costs and factor in gas, tolls, and insurance.",
        "steps": [
            "Get in-home estimates from at least 3 licensed movers",
            "Check company reviews and verify their DOT registration",
            "Get quotes in writing with itemized costs",
            "For DIY: compare rental truck companies and factor in all costs",
            "Book early for peak season (May\u2013September)"
        ]
    },
    "Notify your landlord or list your home for sale": {
        "urgency": "Within 24 hours",
        "how_to": "Check your lease for the required notice period (usually 30\u201360 days). Give written notice to your landlord. If selling your home, contact a real estate agent to discuss timing and pricing. The sooner you start, the more options you have.",
        "steps": [
            "Review your lease for the notice requirement and early termination clause",
            "Give written notice to your landlord (keep a copy)",
            "If selling, interview 2\u20133 real estate agents",
            "Start decluttering and preparing the home for showing"
        ]
    },
    "Research schools in the new area if applicable": {
        "urgency": "Within 24 hours",
        "how_to": "Research school districts, ratings, and enrollment procedures in your new area. Some schools have enrollment deadlines or waiting lists. Contact the new school to understand what records you'll need to transfer.",
        "steps": [
            "Research school ratings on GreatSchools.org or Niche.com",
            "Contact the new school about enrollment requirements",
            "Request records transfer from the current school",
            "Ask about any registration deadlines or waiting lists"
        ]
    },

    # RELOCATION — First Week
    "Set up mail forwarding through USPS": {
        "urgency": "Within 7 days",
        "how_to": "Forward your mail online at usps.com (costs $1.10 for identity verification). Forwarding lasts 12 months for first-class mail. Start it a week before your move so nothing falls through the cracks.",
        "steps": [
            "Go to usps.com and set up mail forwarding",
            "Set the start date for 1 week before your move",
            "Forward mail for all household members",
            "Monitor forwarded mail for accounts you forgot to update"
        ]
    },
    "Transfer or set up utilities at new address": {
        "urgency": "Within 7 days",
        "how_to": "Contact utility companies at your new address to set up service before you arrive. Schedule disconnection of utilities at your old address for the day after your move. Keep utilities on at the old address through move-out to avoid issues with your security deposit.",
        "steps": [
            "Set up electricity, gas, water, and trash at the new address",
            "Set up internet and phone service",
            "Schedule disconnection at the old address for move-out day",
            "Pay any outstanding utility balances at the old address"
        ]
    },
    "Notify your employer and update payroll address": {
        "urgency": "Within 7 days",
        "how_to": "Inform your employer of your new address for payroll, tax, and benefits purposes. If moving to a different state, your tax withholdings will change. HR needs to update your state tax withholding and you may need to adjust your W-4.",
        "steps": [
            "Notify HR of your new address",
            "Update your W-4 for the new state's tax requirements",
            "Update your address in the payroll system",
            "Check if your benefits change when you move to a new state"
        ]
    },
    "Transfer medical records and find new healthcare providers": {
        "urgency": "Within 7 days",
        "how_to": "Request copies of your medical records before you move. Find new doctors, dentists, and specialists in your new area. Check your insurance network for covered providers. Get refills on prescriptions before you go.",
        "steps": [
            "Request medical and dental records from current providers",
            "Get prescription refills to last through the transition",
            "Search for in-network providers in your new area",
            "Transfer pharmacy records to a location near your new home"
        ]
    },
    "Update address with banks and financial institutions": {
        "urgency": "Within 7 days",
        "how_to": "Update your address with all banks, credit cards, investment accounts, and insurance companies. Most can be done online. This ensures you receive important statements and correspondence at your new address.",
        "steps": [
            "Update all bank and credit card accounts online",
            "Update investment and retirement account addresses",
            "Update auto, home/renters, and health insurance addresses",
            "Update any loan servicers (student loans, mortgage, etc.)"
        ]
    },

    # RELOCATION — First Month
    "Get a new driver's license in your new state": {
        "urgency": "Within 30 days",
        "how_to": "Most states require a new driver's license within 30\u201390 days of moving. Visit your new state's DMV website to check requirements. You'll typically need your old license, proof of new address, Social Security card, and possibly a birth certificate or passport.",
        "steps": [
            "Check your new state's deadline for license transfer",
            "Gather required documents (old license, proof of address, SSN, etc.)",
            "Schedule a DMV appointment if possible to reduce wait times",
            "Take a new license photo and pay the fee ($20\u2013$50)"
        ]
    },
    "Register your vehicle in the new state": {
        "urgency": "Within 30 days",
        "how_to": "You'll need to register your vehicle in your new state and may need a new state inspection or emissions test. Bring your title, old registration, proof of insurance, and new driver's license. Some states also require a VIN inspection.",
        "steps": [
            "Check your new state's vehicle registration requirements",
            "Get a state inspection or emissions test if required",
            "Visit the DMV with title, registration, insurance, and license",
            "Pay registration fees and get new plates"
        ]
    },
    "Register to vote at your new address": {
        "urgency": "Within 30 days",
        "how_to": "Register to vote at your new address through vote.gov or at your local DMV. Some states offer same-day registration. Deadlines vary \u2014 register well before any upcoming election to avoid being turned away.",
        "steps": [
            "Register online at vote.gov",
            "Or register at the DMV when you get your new license",
            "Note any upcoming election registration deadlines",
            "Cancel your registration in your old state if required"
        ]
    },
    "Update your address with the IRS": {
        "urgency": "Within 30 days",
        "how_to": "File Form 8822 with the IRS to update your address. This ensures you receive any tax correspondence or refund checks at your new address. You can also update your address when you file your next tax return.",
        "steps": [
            "File Form 8822 (Change of Address) with the IRS",
            "Or update your address when filing your next tax return",
            "Update your address with your state's tax authority too"
        ]
    },
    "Find new local services (doctor, dentist, vet, etc.)": {
        "urgency": "Within 30 days",
        "how_to": "Use your insurance provider's directory to find in-network doctors, dentists, and specialists. Ask neighbors and local community groups for recommendations. Schedule new patient appointments early \u2014 popular providers may have 4\u20136 week wait times.",
        "steps": [
            "Find in-network primary care and dental providers",
            "Schedule new patient appointments",
            "Find a vet if you have pets",
            "Locate the nearest pharmacy, urgent care, and hospital"
        ]
    },

    # RELOCATION — Ongoing
    "Update all remaining subscriptions and accounts": {
        "urgency": "Ongoing",
        "how_to": "Go through your email and bank statements to catch every subscription and account that needs an address update. This includes online shopping accounts, loyalty programs, magazine subscriptions, and professional memberships.",
        "steps": [
            "Review bank and credit card statements for recurring charges",
            "Update online shopping accounts (Amazon, etc.)",
            "Update professional memberships and subscriptions",
            "Update your address with the post office for any forwarding issues"
        ]
    },
    "File taxes correctly for the year you moved (may need to file in both states)": {
        "urgency": "Ongoing",
        "how_to": "If you moved between states during the tax year, you'll likely need to file part-year resident returns in both states. Allocate income based on when it was earned in each state. Tax software handles this well, or consult a CPA.",
        "steps": [
            "Determine your residency dates in each state",
            "File part-year resident returns in both states if required",
            "Allocate income to each state based on dates worked",
            "Use tax software or a CPA familiar with multi-state filings"
        ]
    },
    "Explore your new community \u2014 join local groups": {
        "urgency": "Ongoing",
        "how_to": "Building a social network in your new location takes effort but makes all the difference. Join local groups, volunteer, attend community events, and visit neighborhood spots. It takes about 3\u20136 months to start feeling at home.",
        "steps": [
            "Search Meetup.com for local interest groups",
            "Attend community events and neighborhood gatherings",
            "Volunteer with local organizations",
            "Introduce yourself to neighbors"
        ]
    },

    # ═══════════════════════════════
    # DISABILITY — First 24 Hours
    # ═══════════════════════════════
    "Request FMLA leave from your employer if applicable": {
        "urgency": "Within 24 hours",
        "how_to": "FMLA provides up to 12 weeks of unpaid, job-protected leave for a serious health condition. You must work for a company with 50+ employees and have worked there 12+ months. Notify HR as soon as possible \u2014 your employer can require 30 days' notice for foreseeable leave.",
        "steps": [
            "Notify your HR department of your need for FMLA leave",
            "Request the required FMLA paperwork from HR",
            "Have your doctor complete the medical certification form",
            "Submit paperwork promptly \u2014 you have 15 days after the employer's request",
            "Understand whether your leave is paid or unpaid"
        ]
    },
    "Gather all medical records and documentation": {
        "urgency": "Within 24 hours",
        "how_to": "Collect all medical records, test results, doctor's notes, and treatment histories related to your condition. This documentation is critical for disability applications, insurance claims, and employer accommodations. Start a dedicated folder or binder.",
        "steps": [
            "Request copies of all medical records from your providers",
            "Collect test results, imaging reports, and specialist notes",
            "Create a timeline of your condition (onset, diagnosis, treatments)",
            "Keep a copy of every document \u2014 never send originals"
        ]
    },
    "Understand the difference between SSDI and SSI": {
        "urgency": "Within 24 hours",
        "how_to": "SSDI (Social Security Disability Insurance) is for people who've worked and paid into Social Security. SSI (Supplemental Security Income) is needs-based for people with limited income and resources. You might qualify for both. The application process is similar but eligibility differs.",
        "steps": [
            "Check if you have enough work credits for SSDI (usually 40 credits)",
            "Determine if your income and assets qualify you for SSI",
            "Understand that SSDI has a 5-month waiting period for benefits",
            "SSI may provide benefits sooner but amounts are lower"
        ]
    },
    "Contact your employer about short-term disability benefits": {
        "urgency": "Within 24 hours",
        "how_to": "Check if your employer offers short-term disability (STD) insurance. This can replace 50\u201370% of your income for 3\u20136 months while you recover or wait for SSDI approval. Contact HR to find out your coverage and how to file a claim.",
        "steps": [
            "Ask HR if you have short-term disability coverage",
            "Find out the benefit amount and duration",
            "File a claim with the disability insurance provider",
            "Have your doctor provide required medical documentation"
        ]
    },
    "Begin documenting your condition and limitations daily": {
        "urgency": "Within 24 hours",
        "how_to": "Keep a daily journal of your symptoms, pain levels, limitations, and how your condition affects daily activities. This documentation becomes powerful evidence for disability applications and appeals. Be specific: 'couldn't stand for more than 10 minutes' is better than 'had a bad day.'",
        "steps": [
            "Start a daily symptom journal (physical notebook or app)",
            "Note pain levels on a 1\u201310 scale",
            "Document specific limitations (can't lift, stand, concentrate, etc.)",
            "Record how your condition affects work, sleep, and daily tasks",
            "Note all medications taken and their side effects"
        ]
    },

    # DISABILITY — First Week
    "Apply for Social Security disability benefits (online or by phone)": {
        "urgency": "Within 7 days",
        "how_to": "Apply at ssa.gov or call 1-800-772-1213. The process takes 3\u20136 months for an initial decision (and 60\u201370% of initial claims are denied). Apply as early as possible. Have your medical records, work history, and doctor's contact information ready.",
        "steps": [
            "Apply online at ssa.gov or call 1-800-772-1213",
            "List all medical conditions and how they limit your ability to work",
            "Provide complete medical treatment history and doctor contact info",
            "List your work history for the past 15 years",
            "Keep copies of everything you submit"
        ]
    },
    "Review your employer's disability insurance policy": {
        "urgency": "Within 7 days",
        "how_to": "Check both short-term and long-term disability policies through your employer. Understand the elimination period (waiting time before benefits start), benefit duration, and what percentage of income they replace. Some policies require you to also apply for SSDI.",
        "steps": [
            "Request a copy of your disability insurance policy from HR",
            "Note the elimination period and benefit duration",
            "Understand the benefit amount (usually 50\u201370% of salary)",
            "Check if the policy requires you to apply for SSDI",
            "File claims for both STD and LTD if applicable"
        ]
    },
    "Contact your health insurance to understand coverage": {
        "urgency": "Within 7 days",
        "how_to": "Understand what your health insurance covers for your condition. Check referral requirements, prior authorization needs, and out-of-pocket maximums. If you're leaving your job, understand your COBRA options or marketplace eligibility.",
        "steps": [
            "Call your insurance company to verify coverage for your treatments",
            "Ask about prior authorization requirements",
            "Check your out-of-pocket maximum and deductible status",
            "Ask about coverage for specialists, therapy, and medications",
            "Plan for coverage continuation if you leave your job"
        ]
    },
    "Gather work history for the past 15 years": {
        "urgency": "Within 7 days",
        "how_to": "SSA needs your detailed work history for the past 15 years to evaluate your disability claim. Include job titles, duties, physical requirements, and dates of employment. This helps them determine if you can do any of your past work.",
        "steps": [
            "List every job you've held in the past 15 years",
            "Include employer names, dates, and job duties",
            "Describe the physical demands of each job",
            "Note your highest level of education and any training"
        ]
    },
    "Identify all sources of income and benefits available to you": {
        "urgency": "Within 7 days",
        "how_to": "Map out every possible source of income and benefits: employer disability, SSDI/SSI, state disability, workers' comp (if work-related), VA benefits, and private disability insurance. Understanding all your options helps you avoid gaps in coverage.",
        "steps": [
            "List employer-provided disability benefits",
            "Check eligibility for SSDI and/or SSI",
            "Research your state's disability insurance program",
            "Check if workers' compensation applies",
            "Review any private disability insurance you may have"
        ]
    },

    # DISABILITY — First Month
    "Follow up on your SSDI/SSI application status": {
        "urgency": "Within 30 days",
        "how_to": "Check your application status online at ssa.gov or by calling SSA. Make sure they've received all your medical records. If they request additional information, respond promptly \u2014 delays can add months to the process.",
        "steps": [
            "Check status online at ssa.gov or call 1-800-772-1213",
            "Confirm SSA has received your medical records",
            "Respond to any information requests within the deadline",
            "Keep a log of all communications with SSA"
        ]
    },
    "Apply for any state disability programs": {
        "urgency": "Within 30 days",
        "how_to": "Five states (CA, HI, NJ, NY, RI) and Puerto Rico have state disability insurance programs that provide temporary benefits. Even in other states, there may be assistance programs available. Check your state's labor department website.",
        "steps": [
            "Check if your state has a disability insurance program",
            "Apply through your state's labor department",
            "Research additional state assistance programs",
            "Check local nonprofit organizations for support"
        ]
    },
    "Create a budget based on reduced income": {
        "urgency": "Within 30 days",
        "how_to": "Disability benefits typically replace only 50\u201370% of your previous income. Create a realistic budget based on what you'll actually receive. Prioritize necessities and look for ways to reduce expenses. Contact creditors about hardship programs.",
        "steps": [
            "Calculate your expected monthly disability income",
            "List all essential expenses (housing, food, medicine, utilities)",
            "Identify expenses to cut or reduce",
            "Contact creditors about hardship programs",
            "Look into prescription assistance programs for medications"
        ]
    },
    "Look into Medicaid eligibility if applicable": {
        "urgency": "Within 30 days",
        "how_to": "If your income drops significantly, you may qualify for Medicaid. SSI recipients automatically qualify in most states. SSDI recipients become eligible for Medicare after a 24-month waiting period. Medicaid can cover healthcare costs in the meantime.",
        "steps": [
            "Check Medicaid eligibility at your state's Medicaid office or healthcare.gov",
            "Apply if your income falls below the threshold",
            "Understand that SSI recipients usually get automatic Medicaid",
            "Plan for the 24-month Medicare waiting period if on SSDI"
        ]
    },
    "Keep all medical appointments and document everything": {
        "urgency": "Within 30 days",
        "how_to": "Consistent medical treatment strengthens your disability claim. Missing appointments can be used as evidence that your condition isn't severe. Keep attending all appointments and document your symptoms and limitations at each visit.",
        "steps": [
            "Attend all scheduled medical appointments",
            "Ask doctors to document your functional limitations in their notes",
            "Keep copies of all medical records and visit summaries",
            "Report any new symptoms or worsening conditions to your doctor"
        ]
    },

    # DISABILITY — Ongoing
    "Continue medical treatment and keep records": {
        "urgency": "Ongoing",
        "how_to": "Ongoing treatment shows SSA that your condition is serious and you're doing everything you can. Keep all appointments, follow treatment plans, and maintain detailed records. Gaps in treatment can weaken your claim or trigger a review.",
        "steps": [
            "Follow your treatment plan consistently",
            "Keep all medical appointments",
            "Maintain a file of all medical records and receipts",
            "Update your symptom journal regularly"
        ]
    },
    "Prepare for a potential denial and appeal process": {
        "urgency": "Ongoing",
        "how_to": "About 60\u201370% of initial SSDI claims are denied. Don't give up \u2014 many are approved on appeal. You have 60 days to appeal after a denial. The appeal goes through reconsideration, then a hearing before an administrative law judge (where approval rates are higher).",
        "steps": [
            "If denied, file an appeal within 60 days",
            "Request reconsideration first",
            "If denied again, request a hearing before an ALJ",
            "Gather additional medical evidence for the hearing",
            "Consider hiring a disability attorney (they work on contingency)"
        ]
    },
    "Consider working with a disability attorney if denied": {
        "urgency": "Ongoing",
        "how_to": "Disability attorneys work on contingency \u2014 they only get paid if you win (typically 25% of back pay, capped at $7,200). They significantly improve your chances at the hearing level. Most offer free consultations.",
        "steps": [
            "Research disability attorneys in your area",
            "Schedule free consultations with 2\u20133 attorneys",
            "Understand the contingency fee structure",
            "Provide your attorney with all medical records and correspondence"
        ]
    },
    "Monitor your benefits and report any changes": {
        "urgency": "Ongoing",
        "how_to": "If you're receiving disability benefits, you must report changes in income, living arrangements, medical condition, and ability to work. Failure to report can result in overpayments you'll have to repay. SSA also conducts periodic medical reviews.",
        "steps": [
            "Report any income changes to SSA promptly",
            "Report changes in living arrangements",
            "Notify SSA of any medical improvement",
            "Keep records of all communications with SSA"
        ]
    },

    # ═══════════════════════════════
    # RETIREMENT — First 24 Hours
    # ═══════════════════════════════
    "Create a retirement income plan (Social Security + pension + savings)": {
        "urgency": "Within 24 hours",
        "how_to": "Map out all your income sources: Social Security, pension, 401(k)/IRA withdrawals, and any other savings. Your goal is to know your monthly income and compare it to your expected expenses. The 4% rule suggests withdrawing 4% of savings annually as a starting point.",
        "steps": [
            "Estimate your Social Security benefit at ssa.gov/myaccount",
            "Calculate expected pension payments if applicable",
            "Total all retirement account balances (401k, IRA, etc.)",
            "Apply the 4% rule to savings for estimated annual withdrawal",
            "Compare total monthly income to expected monthly expenses"
        ],
        "related_worksheet": "Retirement Income Planner"
    },
    "Understand your Medicare enrollment timeline": {
        "urgency": "Within 24 hours",
        "how_to": "Your Initial Enrollment Period (IEP) starts 3 months before you turn 65 and ends 3 months after. Missing this window can result in permanent premium penalties. If you have employer coverage through a large employer (20+), you can delay enrollment.",
        "steps": [
            "Note your Initial Enrollment Period (3 months before to 3 months after turning 65)",
            "Determine if you need to enroll now or can delay due to employer coverage",
            "Research Medicare Parts A, B, C, and D",
            "Understand the late enrollment penalty for Part B (10% per year missed)"
        ]
    },
    "Review all retirement account balances (401k, IRA, pension)": {
        "urgency": "Within 24 hours",
        "how_to": "Get current statements for all retirement accounts. Know the difference between traditional (tax-deferred) and Roth (tax-free) accounts. Understand your pension options and any employer match you haven't fully vested.",
        "steps": [
            "Log into all retirement accounts and note current balances",
            "Identify which are traditional vs. Roth",
            "Check your pension vesting status",
            "Note any employer match you may forfeit if leaving early"
        ]
    },
    "Decide when to start Social Security benefits": {
        "urgency": "Within 24 hours",
        "how_to": "You can claim Social Security as early as 62, at full retirement age (66\u201367), or as late as 70. Each year you delay past full retirement age increases your benefit by 8%. Claiming early permanently reduces it. The right choice depends on your health, finances, and other income.",
        "steps": [
            "Check your full retirement age at ssa.gov",
            "Compare benefit amounts at ages 62, full retirement, and 70",
            "Consider your health and family longevity",
            "Factor in spousal benefits and survivor benefit implications",
            "Use the SSA's benefit calculator at ssa.gov/benefits/retirement/estimator.html"
        ]
    },
    "Review your employer's retirement benefits package": {
        "urgency": "Within 24 hours",
        "how_to": "Meet with HR to understand all your retirement benefits: pension details, retiree health insurance, life insurance continuation, and any phased retirement options. Get everything in writing before your last day.",
        "steps": [
            "Schedule a meeting with your HR or benefits department",
            "Ask about retiree health insurance options",
            "Understand your pension payout options",
            "Ask about life insurance and other benefits continuation",
            "Get all benefit details in writing"
        ]
    },

    # RETIREMENT — First Week
    "Enroll in Medicare if you're 65+ (Parts A, B, D)": {
        "urgency": "Within 7 days",
        "how_to": "Enroll online at ssa.gov, by phone, or at your local Social Security office. Part A (hospital) is usually free. Part B (medical) costs about $165/month. Part D (prescription) varies by plan. You need all three for comprehensive coverage.",
        "steps": [
            "Enroll in Medicare Part A and B at ssa.gov or Social Security office",
            "Choose a Part D prescription drug plan at medicare.gov",
            "Consider whether you need a Medigap (Supplement) or Advantage plan",
            "Keep your enrollment confirmation documents"
        ]
    },
    "Compare Medicare Supplement vs. Medicare Advantage plans": {
        "urgency": "Within 7 days",
        "how_to": "Medigap (Supplement) plans fill the gaps in original Medicare and let you see any doctor who accepts Medicare. Medicare Advantage (Part C) is an all-in-one alternative, often with lower premiums but restricted networks. Your health needs and preferred doctors should drive this decision.",
        "steps": [
            "Compare plans at medicare.gov/plan-compare",
            "Check if your current doctors accept Medicare",
            "Compare premiums, deductibles, and out-of-pocket maximums",
            "Consider your prescription drug needs",
            "Look at plan ratings and customer satisfaction"
        ]
    },
    "Begin consolidating retirement accounts if needed": {
        "urgency": "Within 7 days",
        "how_to": "If you have multiple 401(k)s from different employers, consider consolidating them into a single IRA. This simplifies management, may reduce fees, and makes Required Minimum Distributions easier to calculate. Use a direct rollover to avoid tax consequences.",
        "steps": [
            "List all retirement accounts and their locations",
            "Open a rollover IRA at a low-cost brokerage if needed",
            "Request direct rollovers from old 401(k) plans",
            "Choose an appropriate asset allocation for retirement"
        ]
    },
    "Create a detailed retirement budget": {
        "urgency": "Within 7 days",
        "how_to": "Your spending patterns will change in retirement. Some expenses decrease (commuting, work clothes) while others increase (healthcare, travel, hobbies). Create a realistic monthly budget that accounts for these changes.",
        "steps": [
            "List all expected monthly expenses in retirement",
            "Factor in increased healthcare costs",
            "Include planned travel and hobby expenses",
            "Don't forget taxes on retirement account withdrawals",
            "Build in an emergency fund of 6\u201312 months' expenses"
        ],
        "related_worksheet": "Retirement Budget Worksheet"
    },
    "Review your estate plan and update beneficiaries": {
        "urgency": "Within 7 days",
        "how_to": "Make sure your will, trust, power of attorney, and healthcare directive are current. Update beneficiaries on all retirement accounts, life insurance, and bank accounts. Beneficiary designations override your will, so they must be correct.",
        "steps": [
            "Review and update your will",
            "Update beneficiaries on retirement accounts and insurance",
            "Review your power of attorney and healthcare directive",
            "Consider establishing or updating a trust",
            "Discuss your estate plan with your family"
        ]
    },

    # RETIREMENT — First Month
    "Apply for Social Security benefits (3 months before desired start)": {
        "urgency": "Within 30 days",
        "how_to": "Apply online at ssa.gov, by phone, or at your local office 3 months before you want benefits to start. Have your birth certificate, tax returns, and bank information for direct deposit. The process usually takes 1\u20132 weeks for approval.",
        "steps": [
            "Apply at ssa.gov or call 1-800-772-1213",
            "Have your birth certificate and recent tax return ready",
            "Set up direct deposit for your benefit payments",
            "Review your benefit amount estimate before confirming"
        ]
    },
    "Decide on pension payout options (lump sum vs. annuity)": {
        "urgency": "Within 30 days",
        "how_to": "A lump sum gives you control of the money but requires investment discipline. An annuity provides guaranteed monthly income for life but can't be changed. Consider your health, other income, and risk tolerance. This is one of the biggest financial decisions of retirement.",
        "steps": [
            "Get the lump sum amount and monthly annuity options in writing",
            "Calculate which provides more value based on your life expectancy",
            "Consider inflation protection options for annuities",
            "Consult a fee-only financial advisor before deciding",
            "If taking a lump sum, roll it directly to an IRA to avoid taxes"
        ]
    },
    "Set up Required Minimum Distributions if 73+": {
        "urgency": "Within 30 days",
        "how_to": "If you're 73 or older (born 1951 or later), you must take RMDs from traditional retirement accounts annually. The amount is based on your account balance and life expectancy. Failure to take RMDs results in a 25% penalty on the amount not withdrawn.",
        "steps": [
            "Calculate your RMD using the IRS Uniform Lifetime Table",
            "Set up automatic RMD distributions with your account custodian",
            "Take your first RMD by April 1 of the year after you turn 73",
            "Subsequent RMDs are due by December 31 each year"
        ]
    },
    "Plan for healthcare costs in retirement": {
        "urgency": "Within 30 days",
        "how_to": "Healthcare is typically the largest expense in retirement. Medicare doesn't cover everything \u2014 you'll still pay premiums, deductibles, copays, dental, vision, and potentially long-term care. Plan for an average of $300\u2013$600/month per person.",
        "steps": [
            "Estimate monthly Medicare premiums and out-of-pocket costs",
            "Budget for dental and vision coverage (not covered by original Medicare)",
            "Consider a Health Savings Account (HSA) if you have one",
            "Research long-term care insurance or self-funding options"
        ]
    },
    "Consider long-term care insurance": {
        "urgency": "Within 30 days",
        "how_to": "70% of people over 65 will need some form of long-term care. Medicare doesn't cover extended nursing home or home care. Long-term care insurance is most affordable if purchased between ages 55\u201365. Premiums increase significantly with age.",
        "steps": [
            "Research long-term care insurance options and costs",
            "Compare traditional LTC, hybrid life/LTC, and self-funding",
            "Get quotes from multiple insurers",
            "Consider your family health history and risk factors"
        ]
    },

    # RETIREMENT — Ongoing
    "Monitor your withdrawal rate and adjust as needed": {
        "urgency": "Ongoing",
        "how_to": "Track how much you're withdrawing from savings relative to your total balance. If the market drops or you're spending more than planned, you may need to reduce withdrawals to avoid running out. The 4% rule is a guideline, not a guarantee.",
        "steps": [
            "Review your withdrawal rate quarterly",
            "Adjust spending if your portfolio drops significantly",
            "Consider a variable withdrawal strategy based on market performance",
            "Rebalance your investment portfolio annually"
        ]
    },
    "Take Required Minimum Distributions on time": {
        "urgency": "Ongoing",
        "how_to": "RMDs must be taken by December 31 each year (April 1 for your first year). Set up automatic distributions so you don't forget. The penalty for missing an RMD is 25% of the amount you should have withdrawn.",
        "steps": [
            "Set up automatic RMD distributions with your custodian",
            "Verify the correct amount is distributed each year",
            "Consider donating RMDs to charity via Qualified Charitable Distribution",
            "Track RMDs for tax planning purposes"
        ]
    },
    "Review Medicare coverage during annual enrollment": {
        "urgency": "Ongoing",
        "how_to": "Medicare Annual Enrollment Period runs October 15\u2013December 7 each year. Review your current plan's costs, coverage, and formulary changes for the coming year. Switch plans if a better option is available \u2014 your needs may change over time.",
        "steps": [
            "Review your current plan's Annual Notice of Changes",
            "Compare plans at medicare.gov during open enrollment (Oct 15\u2013Dec 7)",
            "Check if your prescriptions are still covered at the same tier",
            "Switch plans if you find better coverage or lower costs"
        ]
    },
    "Update your estate plan annually": {
        "urgency": "Ongoing",
        "how_to": "Review your will, beneficiaries, and healthcare directives at least once a year or after major life events. Make sure your documents reflect your current wishes and that your named agents and beneficiaries are still appropriate.",
        "steps": [
            "Review your will and trust annually",
            "Verify all beneficiary designations are current",
            "Update your healthcare directive and power of attorney as needed",
            "Discuss any changes with your family"
        ]
    },
    "Stay active in your community \u2014 retirement is a transition too": {
        "urgency": "Ongoing",
        "how_to": "Retirement is a major life transition that affects identity and social connections. Stay engaged through volunteering, hobbies, part-time work, or community involvement. Social connection is strongly linked to health and happiness in retirement.",
        "steps": [
            "Join clubs, classes, or volunteer organizations",
            "Consider part-time work or consulting in your field",
            "Maintain and build social connections",
            "Pursue hobbies and interests you didn't have time for before",
            "Consider mentoring younger professionals in your field"
        ]
    },
}
